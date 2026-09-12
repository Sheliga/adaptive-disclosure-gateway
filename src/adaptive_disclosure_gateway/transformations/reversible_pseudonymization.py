from __future__ import annotations

import time

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
from adaptive_disclosure_gateway.transformations.span_validation import spans_are_valid
from adaptive_disclosure_gateway.vault import Vault

from . import decision_application, generalization
from .decision_application import ActionDecision, TreatmentReasons

# Reversible Pseudonymization (B2): the *same* static, task- and
# policy-independent category -> action mapping as Static Sanitization (B1)
# -- see docs/experimental-design.md's B1->B2 comparison, which isolates
# *reversibility* and nothing else. The only difference from B1's ACTIONS is
# that categories B1 could only REMOVE are instead PSEUDONYMIZE-d here,
# because B2 (unlike B1) has a local vault able to reverse them. salary,
# department and medical_data are unchanged from B1.
#
# This mapping is intentionally a plain module-level dict, not something
# derived by calling into PolicyRepository.decide(): PolicyRepository is
# imported below only to resolve pseudonym scope and to check whether
# reconstruction is authorized, never to choose the action per category.
# tests/test_treatment_isolation.py pins both halves of that rule.
ACTIONS: dict[str, DisclosureAction] = {
    "employee_name": DisclosureAction.PSEUDONYMIZE,
    "cpf": DisclosureAction.PSEUDONYMIZE,
    "cnpj": DisclosureAction.PSEUDONYMIZE,
    "email": DisclosureAction.PSEUDONYMIZE,
    "phone": DisclosureAction.PSEUDONYMIZE,
    "salary": DisclosureAction.GENERALIZE,
    "department": DisclosureAction.PRESERVE,
    "medical_data": DisclosureAction.BLOCK_REQUEST,
    # --- Contracts domain (Issue #56), following the same B1->B2 rule as
    # everything above: the categories B1 could only REMOVE become
    # PSEUDONYMIZE here, and the GENERALIZE/BLOCK_REQUEST ones are unchanged.
    #
    # This is where Contracts relation preservation actually happens, and it
    # needed no new machinery: the vault issues one stable pseudonym per
    # original value within a scope, so the same company reads as the same
    # pseudonym everywhere in the document while the two parties never
    # collapse into one reference -- and the role word, living in the
    # detector's label rather than in the detected span (see
    # detection/rules.py), is never transformed at all. "ACME must pay Beta"
    # therefore survives as "[party A] must pay [party B]", assignment intact.
    "party_name": DisclosureAction.PSEUDONYMIZE,
    "representative_name": DisclosureAction.PSEUDONYMIZE,
    "bank_account": DisclosureAction.BLOCK_REQUEST,
    "contract_value": DisclosureAction.GENERALIZE,
    "penalty_amount": DisclosureAction.GENERALIZE,
    "deadline": DisclosureAction.GENERALIZE,
}


def _resolve_action(category: str) -> DisclosureAction:
    """Look up ``category``'s static action, downgrading GENERALIZE to
    BLOCK_REQUEST if no generalization strategy is configured for it
    (issue #16: fail closed rather than silently disclosing the original
    value). Resolved before any text slicing happens.

    The unconfigured-GENERALIZE downgrade checked here is a cheap,
    category-only pre-check; the *value*-level downgrade (a configured
    strategy that still cannot parse this particular value) happens in
    ``transformations.decision_application``'s shared apply pipeline, which
    every GENERALIZE decision from any treatment passes through.
    """
    action = ACTIONS.get(category, DisclosureAction.BLOCK_REQUEST)
    if action is DisclosureAction.GENERALIZE and not generalization.is_configured(category):
        return DisclosureAction.BLOCK_REQUEST
    return action


_REASONS = TreatmentReasons(
    invalid_spans=(
        "B2 reversible pseudonymization blocks: span offsets are missing, out "
        "of bounds, or do not match the source text"
    ),
    missing_scope_identifier=(
        "B2 reversible pseudonymization blocks: the resolved pseudonym scope "
        "requires a lifecycle identifier the governance context does not provide"
    ),
)


def _decide(span: SensitiveSpan) -> ActionDecision:
    action = _resolve_action(span.category)
    if action is DisclosureAction.BLOCK_REQUEST:
        reason = "B2 reversible pseudonymization blocks this category unconditionally"
    else:
        reason = "B2 reversible pseudonymization: static category mapping"
    return ActionDecision(action=action, reason=reason)


class ReversiblePseudonymizer:
    """Reversible Pseudonymization (B2): B1's static mapping, plus a local,
    reversible vault for categories B1 could only remove irreversibly.

    ``request.task`` is intentionally never read for choosing an action:
    the category -> action mapping stays static and task-independent, exactly
    like B1. That staticness is what B2->B3 isolates (see
    docs/experimental-design.md) -- B3 is the first treatment allowed to let
    task relevance influence the choice of action.

    Span validation, overlap resolution, GENERALIZE fail-closed handling,
    pseudonym-scope resolution/vault storage, payload assembly and
    reconstruction are shared with Task-aware (B3) through
    ``transformations.decision_application`` -- this class supplies only the
    static per-category decision above; see that module's docstring for why
    the split exists and why it leaves B2's own behavior unchanged.
    """

    treatment = Treatment.REVERSIBLE_PSEUDONYMIZATION

    def __init__(self, vault: Vault, policy_repository: PolicyRepository) -> None:
        self._vault = vault
        self._policies = policy_repository

    def sanitize(self, request: DisclosureRequest, spans: list[SensitiveSpan]) -> DisclosureResult:
        tracer = get_tracer()
        with tracer.start_as_current_span("reversible_pseudonymization.sanitize") as otel_span:
            started = time.perf_counter()
            spans = list(spans)
            otel_span.set_attribute("treatment", self.treatment.value)

            # Boundary check before any slicing -- reused verbatim from T14,
            # not reimplemented (issue #17).
            if not spans_are_valid(spans, request.text):
                otel_span.set_attribute("reversible_pseudonymization.span_count", len(spans))
                otel_span.set_attribute("reversible_pseudonymization.blocked", True)
                otel_span.set_attribute(
                    "reversible_pseudonymization.categories", sorted({s.category for s in spans})
                )
                return decision_application.invalid_span_result(spans, _REASONS)

            ordered = resolve_overlaps(spans)

            outcome = decision_application.apply(
                text=request.text,
                ordered=ordered,
                decide=_decide,
                policy_repository=self._policies,
                vault=self._vault,
                context=request.context,
                reasons=_REASONS,
            )

            # Metadata only: categories, counts, a block flag and timing --
            # never the detected value, the raw text, the payload, or any
            # pseudonym/vault content.
            otel_span.set_attribute("reversible_pseudonymization.span_count", len(ordered))
            otel_span.set_attribute("reversible_pseudonymization.blocked", outcome.blocked)
            otel_span.set_attribute(
                "reversible_pseudonymization.categories", sorted({s.category for s in ordered})
            )
            if outcome.pseudonym_scope is not None:
                otel_span.set_attribute(
                    "reversible_pseudonymization.pseudonym_scope", outcome.pseudonym_scope.value
                )
            otel_span.set_attribute(
                "reversible_pseudonymization.duration_ms", elapsed_ms_since(started)
            )
            return outcome.result

    def reconstruct(
        self, response_text: str, result: DisclosureResult, context: GovernanceContext
    ) -> str:
        """Authorized local reconstruction of a provider response: pseudonyms
        that this same ``result`` produced are mapped back to their original
        values. Never consults or exposes any pseudonym/original outside
        this local call.

        If ``context`` is not authorized to reconstruct (per
        ``PolicyRepository.is_reconstruction_authorized``), ``response_text``
        is returned unchanged -- no original value is ever substituted in.
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("reversible_pseudonymization.reconstruct") as otel_span:
            otel_span.set_attribute("treatment", self.treatment.value)

            outcome = decision_application.reconstruct(
                response_text,
                result,
                context,
                policy_repository=self._policies,
                vault=self._vault,
            )
            otel_span.set_attribute(
                "reversible_pseudonymization.pseudonym_count", outcome.pseudonym_count
            )
            otel_span.set_attribute(
                "reversible_pseudonymization.reconstruction_authorized", outcome.authorized
            )
            return outcome.text
