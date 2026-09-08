"""Policy-governed (B4): T08 / issue #7.

B4 retains everything B3 -- Task-aware already has -- the same deterministic
task analyzer, the same reversible pseudonymization/vault/reconstruction
mechanism, the same shared "apply" machinery
(``transformations/decision_application.py``), the same provider boundary --
and adds exactly one new variable: an explicit, contextual organizational
policy resolved through ``PolicyRepository.decide()`` *before* task
relevance is allowed to influence anything.

Flow, per detected category:

1. resolve the category's policy decision via ``PolicyRepository.decide()``
   -- domain/version/rule/override resolution, fully delegated to
   ``policies.py``, never reimplemented here;
2. a **hard** action (``PRESERVE``/``PSEUDONYMIZE``/``GENERALIZE``/
   ``REMOVE``/``BLOCK_REQUEST``) is applied as-is -- task relevance never
   changes it, exactly like B1/B2's static mapping;
3. a **``TASK_DEPENDENT``** decision instead hands over an
   ``allowed_actions`` space; that space is canonically ordered
   (``transformations.relevance_selection.order_action_space``) and then
   minimized using the *same* relevance-selection rule B3 uses
   (``transformations.relevance_selection.select_action_for_relevance``),
   over that policy-permitted space and nothing wider;
4. task-awareness can never add an action outside the policy-permitted
   space, promote above its ceiling, turn a hard ``BLOCK_REQUEST`` into a
   permitted action, or substitute a policy failure with a permissive
   fallback -- structurally guaranteed by (2)/(3) only ever handing
   ``select_action_for_relevance`` a subset of what policy already allowed;
5. an ambiguous, missing, or structurally invalid policy resolution --
   including a ``TASK_DEPENDENT`` decision whose resolved space is empty or
   contains a non-disclosure-level action -- fails the whole request closed,
   the same posture ``policies.decide()`` and B3's own analyzer-failure path
   already take.

``PolicyRepository.decide()`` is used **only** in this module -- B2, B3 and
``decision_application.py`` remain forbidden from calling it
(``tests/test_treatment_isolation.py``, unmodified), and
``tests/test_policy_governed_isolation.py`` pins ``policy_governed.py`` as
the sole, explicitly named exception across the entire codebase.

Impossible-under-policy (docs/experimental-design.md's metrics section):
when the task genuinely needs the exact original value
(``TaskRelevance.RELEVANT_WITH_EXACT_VALUE``) but the policy-permitted space
does not include ``PRESERVE``, the resulting ``PolicyDecision`` for that
category carries ``impossible_under_policy=True`` -- distinct from an
ordinary utility failure, an ``AMBIGUOUS`` analyzer read, a hard
``BLOCK_REQUEST``, or a provider failure. ``policy_restricted`` is set
whenever policy forced a *different* (necessarily less disclosing) choice
than the same relevance would have received from the full, unconstrained
canonical action space -- the general "did policy actually bind the
outcome" signal T10 needs alongside the narrower impossible-under-policy
one. Both fields are booleans only -- see ``domain.PolicyDecision``'s own
docstring.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from adaptive_disclosure_gateway.detection.overlap import resolve_overlaps
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    DisclosureResult,
    GovernanceContext,
    SensitiveSpan,
    Treatment,
)
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.task_analysis import DeterministicTaskAnalyzer, TaskAnalyzer
from adaptive_disclosure_gateway.task_analysis.base import TaskRelevance
from adaptive_disclosure_gateway.transformations.relevance_selection import (
    CANONICAL_DISCLOSURE_ORDER,
    order_action_space,
    select_action_for_relevance,
)
from adaptive_disclosure_gateway.transformations.span_validation import spans_are_valid
from adaptive_disclosure_gateway.vault import Vault

from . import decision_application
from .decision_application import ActionDecision, TreatmentReasons

_REASONS = TreatmentReasons(
    invalid_spans=(
        "B4 policy-governed blocks: span offsets are missing, out of bounds, or do "
        "not match the source text"
    ),
    missing_scope_identifier=(
        "B4 policy-governed blocks: the resolved pseudonym scope requires a "
        "lifecycle identifier the governance context does not provide"
    ),
)

_ANALYZER_FAILURE_REASON = (
    "B4 policy-governed blocks: the task analyzer raised an exception or reported an "
    "unrecognized relevance level for a detected category, so the whole request "
    "fails closed rather than trusting any of its per-category decisions"
)
_INVALID_ACTION_SPACE_REASON = (
    "B4 policy-governed blocks: the policy-resolved action space for this "
    "task-dependent category is empty or contains an action that is not a valid "
    "disclosure level"
)


class PolicyGovernedDiscloser:
    """Policy-governed (B4): policy-constrained, task-analyzer-driven action
    selection, applied through the same shared vault/scope/reconstruction
    machinery B2 -- Reversible Pseudonymization and B3 -- Task-aware use (see
    module docstring).
    """

    treatment = Treatment.POLICY_GOVERNED

    def __init__(
        self,
        vault: Vault,
        policy_repository: PolicyRepository,
        task_analyzer: TaskAnalyzer | None = None,
    ) -> None:
        self._vault = vault
        self._policies = policy_repository
        self._task_analyzer = task_analyzer or DeterministicTaskAnalyzer()

    def sanitize(self, request: DisclosureRequest, spans: list[SensitiveSpan]) -> DisclosureResult:
        tracer = get_tracer()
        with tracer.start_as_current_span("policy_governed.sanitize") as otel_span:
            started = time.perf_counter()
            spans = list(spans)
            otel_span.set_attribute("treatment", self.treatment.value)
            otel_span.set_attribute(
                "policy_governed.policy_version", request.context.policy_version
            )

            if not spans_are_valid(spans, request.text):
                otel_span.set_attribute("policy_governed.span_count", len(spans))
                otel_span.set_attribute("policy_governed.blocked", True)
                otel_span.set_attribute("policy_governed.block_reason_class", "invalid_spans")
                otel_span.set_attribute(
                    "policy_governed.categories", sorted({s.category for s in spans})
                )
                return decision_application.invalid_span_result(spans, _REASONS)

            ordered = resolve_overlaps(spans)
            categories = sorted({span.category for span in ordered})

            relevance_by_category: dict[str, TaskRelevance] = {}
            analysis_failed = False
            try:
                analysis = self._task_analyzer.analyze(request.task, categories)
                for category in categories:
                    level = analysis.relevance_by_category.get(category)
                    if not isinstance(level, TaskRelevance):
                        analysis_failed = True
                        break
                    relevance_by_category[category] = level
            except Exception:  # noqa: BLE001 -- fail-closed by design, kind-only
                # Mirrors task_aware.py's own analyzer-failure handling: the
                # exception's message is never inspected or recorded, only
                # the fact that analysis failed.
                analysis_failed = True

            ambiguous_categories: set[str] = set()
            policy_restricted_categories: set[str] = set()
            impossible_categories: set[str] = set()
            matrix_cells: set[str] = set()
            block_reason_classes: set[str] = set()

            decide = self._make_decider(
                request.context,
                relevance_by_category,
                analysis_failed,
                ambiguous_categories,
                policy_restricted_categories,
                impossible_categories,
                matrix_cells,
                block_reason_classes,
            )

            outcome = decision_application.apply(
                text=request.text,
                ordered=ordered,
                decide=decide,
                policy_repository=self._policies,
                vault=self._vault,
                context=request.context,
                reasons=_REASONS,
            )

            # Metadata only: categories, counts, policy/relevance flags and
            # timing -- never the detected value, the raw text, the task,
            # the payload, or any pseudonym/vault content. policy_version,
            # matrix cell identifiers and category names are all safe,
            # non-sensitive labels (see docs/hr-policy-matrix.md).
            otel_span.set_attribute("policy_governed.span_count", len(ordered))
            otel_span.set_attribute("policy_governed.blocked", outcome.blocked)
            otel_span.set_attribute("policy_governed.categories", categories)
            otel_span.set_attribute("policy_governed.analysis_failed", analysis_failed)
            otel_span.set_attribute(
                "policy_governed.ambiguous_categories", sorted(ambiguous_categories)
            )
            otel_span.set_attribute(
                "policy_governed.policy_restricted_categories", sorted(policy_restricted_categories)
            )
            otel_span.set_attribute(
                "policy_governed.impossible_under_policy_categories", sorted(impossible_categories)
            )
            otel_span.set_attribute("policy_governed.matrix_cells", sorted(matrix_cells))
            if outcome.blocked and not block_reason_classes:
                block_reason_classes.add("invalid_spans_or_missing_scope")
            otel_span.set_attribute(
                "policy_governed.block_reason_classes", sorted(block_reason_classes)
            )
            if outcome.pseudonym_scope is not None:
                otel_span.set_attribute(
                    "policy_governed.pseudonym_scope", outcome.pseudonym_scope.value
                )
            otel_span.set_attribute("policy_governed.duration_ms", elapsed_ms_since(started))
            return outcome.result

    def _make_decider(
        self,
        context: GovernanceContext,
        relevance_by_category: dict[str, TaskRelevance],
        analysis_failed: bool,
        ambiguous_categories: set[str],
        policy_restricted_categories: set[str],
        impossible_categories: set[str],
        matrix_cells: set[str],
        block_reason_classes: set[str],
    ) -> Callable[[SensitiveSpan], ActionDecision]:
        policies = self._policies

        def decide(span: SensitiveSpan) -> ActionDecision:
            category = span.category

            if analysis_failed:
                block_reason_classes.add("analysis_failed")
                return ActionDecision(
                    action=DisclosureAction.BLOCK_REQUEST, reason=_ANALYZER_FAILURE_REASON
                )

            policy_decision = policies.decide(context, category)
            matrix_cells.add(
                f"{policy_decision.policy_version or context.policy_version}:{category}"
            )

            if policy_decision.action is DisclosureAction.BLOCK_REQUEST:
                block_reason_classes.add("policy_block")
                return ActionDecision(
                    action=DisclosureAction.BLOCK_REQUEST,
                    reason=f"B4 policy-governed blocks: {policy_decision.reason}",
                    policy_version=policy_decision.policy_version,
                )

            if policy_decision.action is not DisclosureAction.TASK_DEPENDENT:
                # Hard action: task relevance never changes it -- applied
                # exactly as policy resolved it, mirroring B1/B2's static
                # per-category mapping.
                return ActionDecision(
                    action=policy_decision.action,
                    reason=f"B4 policy-governed: hard policy action -- {policy_decision.reason}",
                    task_required=None,
                    allowed_actions=[policy_decision.action],
                    policy_version=policy_decision.policy_version,
                )

            ordered_space = order_action_space(policy_decision.allowed_actions)
            if not ordered_space or len(ordered_space) != len(set(policy_decision.allowed_actions)):
                block_reason_classes.add("invalid_action_space")
                return ActionDecision(
                    action=DisclosureAction.BLOCK_REQUEST, reason=_INVALID_ACTION_SPACE_REASON
                )

            level = relevance_by_category.get(category)
            if level is None:
                # The analyzer was asked about this category (it is in
                # `categories`) but did not report on it -- same fail-closed
                # rule as an unrecognized relevance value.
                block_reason_classes.add("analysis_failed")
                return ActionDecision(
                    action=DisclosureAction.BLOCK_REQUEST, reason=_ANALYZER_FAILURE_REASON
                )

            if level is TaskRelevance.AMBIGUOUS:
                ambiguous_categories.add(category)
                chosen = ordered_space[0]
                return ActionDecision(
                    action=chosen,
                    reason=(
                        "B4 policy-governed: task analyzer reported an ambiguous relevance "
                        "for this category; the least-disclosing policy-permitted action "
                        "was chosen"
                    ),
                    task_required=None,
                    allowed_actions=list(ordered_space),
                    policy_version=policy_decision.policy_version,
                )

            chosen = select_action_for_relevance(level, ordered_space)
            unconstrained = select_action_for_relevance(level, CANONICAL_DISCLOSURE_ORDER)
            restricted = chosen is not unconstrained
            impossible = (
                level is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
                and DisclosureAction.PRESERVE not in ordered_space
            )
            if restricted:
                policy_restricted_categories.add(category)
            if impossible:
                impossible_categories.add(category)

            return ActionDecision(
                action=chosen,
                reason=(
                    f"B4 policy-governed: task relevance resolved to {level.value}, "
                    "minimized within the policy-permitted action space"
                ),
                task_required=level is not TaskRelevance.NOT_RELEVANT,
                allowed_actions=list(ordered_space),
                policy_version=policy_decision.policy_version,
                policy_restricted=restricted,
                impossible_under_policy=impossible,
            )

        return decide

    def reconstruct(
        self, response_text: str, result: DisclosureResult, context: GovernanceContext
    ) -> str:
        """Authorized local reconstruction, identical in mechanism to B2's
        and B3's (see ``transformations.decision_application.reconstruct``):
        scopes, vault mechanism and reconstruction authorization are all
        unchanged -- only the policy-constrained action decision that
        produced ``result`` differs.
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("policy_governed.reconstruct") as otel_span:
            otel_span.set_attribute("treatment", self.treatment.value)

            outcome = decision_application.reconstruct(
                response_text,
                result,
                context,
                policy_repository=self._policies,
                vault=self._vault,
            )
            otel_span.set_attribute("policy_governed.pseudonym_count", outcome.pseudonym_count)
            otel_span.set_attribute("policy_governed.reconstruction_authorized", outcome.authorized)
            return outcome.text
