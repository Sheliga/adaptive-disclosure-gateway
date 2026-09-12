"""Task-aware (B3): T07 / issue #6.

B3 retains B2 -- Reversible Pseudonymization's entire mechanism (vault,
pseudonym scope, reconstruction, provider boundary, audit shape) unchanged
-- see ``transformations/decision_application.py``, which both treatments
share -- and changes exactly one thing over B2: *how* the action for a
detected category is decided. B2 looks it up in a static, task-independent
map (``reversible_pseudonymization.ACTIONS``). B3 asks a
``task_analysis.TaskAnalyzer`` how relevant the category is to
``request.task``, then picks the least-disclosing action inside a generic,
fixed, per-category action space (``TASK_AWARE_ACTION_SPACES`` below) that
still serves that relevance level.

``PolicyRepository`` is used here -- exactly like in B2 -- only to resolve
pseudonym scope and to authorize reconstruction, *never* to choose a
category's action. ``TASK_AWARE_ACTION_SPACES`` is a plain module-level
dict, not derived from ``PolicyRepository.decide()``; the task analyzer never
receives a ``PolicyRepository``, ``PolicyDecision`` or any contextual policy
input at all. B4 -- Policy-governed later replaces this generic space with
the action space policy resolves; B3 must not anticipate that (see
docs/experimental-design.md's B3->B4 comparison and
tests/test_treatment_isolation.py's B3 rules).

Fail-closed behavior (issue #6's acceptance criteria):

- a detected category absent from ``TASK_AWARE_ACTION_SPACES`` blocks (same
  rule as B1/B2's ``_resolve_action`` defaulting to BLOCK_REQUEST);
- the task analyzer raising, or reporting a relevance value this module does
  not recognize for a category it was asked about, blocks the *whole*
  request -- not just that category -- because at that point nothing here
  can be trusted to pick a safe action for *any* detected category;
- an explicit ``TaskRelevance.AMBIGUOUS`` for an otherwise-known category is
  not a whole-request failure: it resolves to that category's own
  least-disclosing action, recorded in the audit trail as an
  ambiguity-driven decision;
- none of these paths ever falls back to PRESERVE.
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
    select_action_for_relevance,
)
from adaptive_disclosure_gateway.transformations.span_validation import spans_are_valid
from adaptive_disclosure_gateway.vault import Vault

from . import decision_application
from .decision_application import ActionDecision, TreatmentReasons

# Generic, fixed, per-category action space for B3 -- the analogue of B1/B2's
# single-action ACTIONS map, except each category maps to an ORDERED tuple of
# candidate actions, least to most disclosing:
#
#     REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE
#
# (PSEUDONYMIZE ranks below GENERALIZE because a pseudonym discloses nothing
# about the original value -- only a stable reference to it -- while a
# generalized numeric band discloses the value's magnitude.)
#
# employee_name/cpf/cnpj/email/phone: identifiers have no defined
# "generalized" form, and PRESERVE of a direct identifier does not belong in
# a generic (context-independent) action space -- only PSEUDONYMIZE and
# REMOVE do.
#
# salary: a numeric category with a registered GENERALIZE strategy
# (transformations/generalization.py) -- the full three-step space applies.
#
# department: transformations/generalization.py has no registered strategy
# for it, so GENERALIZE is excluded from its generic space (mirrors B1/B2's
# own fail-closed downgrade for an unconfigured category) -- only REMOVE and
# PRESERVE.
#
# medical_data: unconditionally BLOCK_REQUEST, unchanged from B1/B2 -- a
# single-element space, so every relevance level (including AMBIGUOUS and
# NOT_RELEVANT) resolves to the same, only available action.
TASK_AWARE_ACTION_SPACES: dict[str, tuple[DisclosureAction, ...]] = {
    "employee_name": (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE),
    "cpf": (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE),
    "cnpj": (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE),
    "email": (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE),
    "phone": (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE),
    "salary": (DisclosureAction.REMOVE, DisclosureAction.GENERALIZE, DisclosureAction.PRESERVE),
    "department": (DisclosureAction.REMOVE, DisclosureAction.PRESERVE),
    "medical_data": (DisclosureAction.BLOCK_REQUEST,),
    # --- Contracts domain (Issue #56), built by the same rules as the HR
    # entries above, not by inventing new ones:
    #
    # party_name/representative_name: direct entity identifiers, so REMOVE
    # and PSEUDONYMIZE only -- there is no defined "generalized" form of a
    # company or a person, and PRESERVE of a direct identifier does not
    # belong in a generic, context-independent space.
    #
    # bank_account: unconditionally BLOCK_REQUEST, the same shape as
    # medical_data. A single-element space, so every relevance level
    # (including AMBIGUOUS) resolves to the only available action.
    #
    # contract_value/penalty_amount: numeric categories with registered
    # NumericBandStrategy entries (transformations/generalization.py), so the
    # full three-step space applies -- exactly like salary.
    #
    # deadline: a date category with a registered MonthYearDateStrategy, so
    # GENERALIZE is genuinely available and belongs in the space. Including
    # it is the LESS disclosing choice, not the more: without an
    # intermediate step, any positively-mentioned deadline would jump
    # straight to PRESERVE. Whether a month-and-year deadline is still
    # useful to a contract reader is a utility question for the corpus to
    # measure, not a reason to withhold the option from B3. Note that
    # `contracts-v1` itself resolves deadline to a hard PRESERVE -- policy
    # moving *above* B3's own choice is a legitimate, measurable B3->B4
    # cell (see transformations/policy_governed.py's `_policy_effect`).
    "party_name": (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE),
    "representative_name": (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE),
    "bank_account": (DisclosureAction.BLOCK_REQUEST,),
    "contract_value": (
        DisclosureAction.REMOVE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    ),
    "penalty_amount": (
        DisclosureAction.REMOVE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    ),
    "deadline": (
        DisclosureAction.REMOVE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    ),
}


_REASONS = TreatmentReasons(
    invalid_spans=(
        "B3 task-aware blocks: span offsets are missing, out of bounds, or do "
        "not match the source text"
    ),
    missing_scope_identifier=(
        "B3 task-aware blocks: the resolved pseudonym scope requires a "
        "lifecycle identifier the governance context does not provide"
    ),
)

_ANALYZER_FAILURE_REASON = (
    "B3 task-aware blocks: the task analyzer raised an exception or reported an "
    "unrecognized relevance level for a detected category, so the whole request "
    "fails closed rather than trusting any of its per-category decisions"
)
_OUT_OF_SPACE_REASON = (
    "B3 task-aware blocks: this category has no entry in the generic task-aware action space"
)


class TaskAwareDiscloser:
    """Task-aware (B3): task-analyzer-driven action selection inside a
    generic, category-fixed action space, applied through the same shared
    machinery B2 -- Reversible Pseudonymization uses (see module docstring).
    """

    treatment = Treatment.TASK_AWARE

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
        with tracer.start_as_current_span("task_aware.sanitize") as otel_span:
            started = time.perf_counter()
            spans = list(spans)
            otel_span.set_attribute("treatment", self.treatment.value)

            if not spans_are_valid(spans, request.text):
                otel_span.set_attribute("task_aware.span_count", len(spans))
                otel_span.set_attribute("task_aware.blocked", True)
                otel_span.set_attribute(
                    "task_aware.categories", sorted({s.category for s in spans})
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
                # A misbehaving analyzer must never take this request down
                # with an unhandled exception, and its exception message is
                # never inspected or recorded (it could echo task content) --
                # only the fact that it failed. See the module docstring's
                # fail-closed contract.
                analysis_failed = True

            ambiguous_categories: set[str] = set()

            decide = self._make_decider(
                relevance_by_category, analysis_failed, ambiguous_categories
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

            # Metadata only: categories, counts, relevance/ambiguity flags
            # and timing -- never the detected value, the raw text, the
            # task, the payload, or any pseudonym/vault content.
            otel_span.set_attribute("task_aware.span_count", len(ordered))
            otel_span.set_attribute("task_aware.blocked", outcome.blocked)
            otel_span.set_attribute("task_aware.categories", categories)
            otel_span.set_attribute("task_aware.analysis_failed", analysis_failed)
            otel_span.set_attribute("task_aware.ambiguous_categories", sorted(ambiguous_categories))
            if outcome.pseudonym_scope is not None:
                otel_span.set_attribute("task_aware.pseudonym_scope", outcome.pseudonym_scope.value)
            otel_span.set_attribute("task_aware.duration_ms", elapsed_ms_since(started))
            return outcome.result

    @staticmethod
    def _make_decider(
        relevance_by_category: dict[str, TaskRelevance],
        analysis_failed: bool,
        ambiguous_categories: set[str],
    ) -> Callable[[SensitiveSpan], ActionDecision]:
        def decide(span: SensitiveSpan) -> ActionDecision:
            if analysis_failed:
                return ActionDecision(
                    action=DisclosureAction.BLOCK_REQUEST, reason=_ANALYZER_FAILURE_REASON
                )

            action_space = TASK_AWARE_ACTION_SPACES.get(span.category)
            if action_space is None:
                return ActionDecision(
                    action=DisclosureAction.BLOCK_REQUEST, reason=_OUT_OF_SPACE_REASON
                )

            level = relevance_by_category[span.category]
            if level is TaskRelevance.AMBIGUOUS:
                ambiguous_categories.add(span.category)
                return ActionDecision(
                    action=action_space[0],
                    reason=(
                        "B3 task-aware: task analyzer reported an ambiguous relevance for "
                        "this category; the least-disclosing action in its action space "
                        "was chosen"
                    ),
                    task_required=None,
                )

            action = select_action_for_relevance(level, action_space)
            return ActionDecision(
                action=action,
                reason=f"B3 task-aware: task relevance resolved to {level.value}",
                task_required=level is not TaskRelevance.NOT_RELEVANT,
            )

        return decide

    def reconstruct(
        self, response_text: str, result: DisclosureResult, context: GovernanceContext
    ) -> str:
        """Authorized local reconstruction, identical to B2's (see
        ``transformations.decision_application.reconstruct``): scopes,
        vault mechanism and reconstruction authorization are all unchanged
        from B2 -- only the pseudonymize-vs-other action decision that
        produced ``result`` differs.
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("task_aware.reconstruct") as otel_span:
            otel_span.set_attribute("treatment", self.treatment.value)

            outcome = decision_application.reconstruct(
                response_text,
                result,
                context,
                policy_repository=self._policies,
                vault=self._vault,
            )
            otel_span.set_attribute("task_aware.pseudonym_count", outcome.pseudonym_count)
            otel_span.set_attribute("task_aware.reconstruction_authorized", outcome.authorized)
            return outcome.text
