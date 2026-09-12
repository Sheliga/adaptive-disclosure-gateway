from __future__ import annotations

from adaptive_disclosure_gateway.detection.overlap import resolve_overlaps
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    DisclosureResult,
    PolicyDecision,
    SensitiveSpan,
    Transformation,
    Treatment,
)
from adaptive_disclosure_gateway.observability import get_tracer
from adaptive_disclosure_gateway.transformations.span_validation import spans_are_valid

from . import generalization

# Static Sanitization (B1) baseline: a fixed, task- and policy-independent
# category -> action mapping. It does not consult PolicyRepository, task
# relevance, or the pseudonym vault -- that independence is what separates
# this baseline from the later treatments (B2-B4). Having no vault, it never
# uses PSEUDONYMIZE (which requires reversible local storage); it only uses
# actions that are safe without one.
ACTIONS: dict[str, DisclosureAction] = {
    "employee_name": DisclosureAction.REMOVE,
    "cpf": DisclosureAction.REMOVE,
    "cnpj": DisclosureAction.REMOVE,
    "email": DisclosureAction.REMOVE,
    "phone": DisclosureAction.REMOVE,
    "salary": DisclosureAction.GENERALIZE,
    "department": DisclosureAction.PRESERVE,
    "medical_data": DisclosureAction.BLOCK_REQUEST,
    # --- Contracts domain (Issue #56). Same rule as everything above: fixed,
    # task- and policy-independent. Party and representative identities can
    # only be REMOVE-d here, because B1 has no vault to make them reversible
    # -- that is precisely the B1->B2 delta the experiment isolates, and for
    # Contracts it is unusually visible: removing both party names leaves the
    # roles standing but makes the two parties indistinguishable from each
    # other, so "who owes what to whom" is lost at B1 and recovered at B2.
    "party_name": DisclosureAction.REMOVE,
    "representative_name": DisclosureAction.REMOVE,
    "bank_account": DisclosureAction.BLOCK_REQUEST,
    "contract_value": DisclosureAction.GENERALIZE,
    "penalty_amount": DisclosureAction.GENERALIZE,
    "deadline": DisclosureAction.GENERALIZE,
}


def _resolve_action(category: str) -> DisclosureAction:
    """Look up ``category``'s static action, downgrading GENERALIZE to
    BLOCK_REQUEST if no generalization strategy is configured for it
    (issue #16: fail closed rather than silently falling back to disclosing
    the original value). Resolved before any text slicing happens, so a
    misconfigured category never partially discloses anything.
    """
    action = ACTIONS.get(category, DisclosureAction.BLOCK_REQUEST)
    if action is DisclosureAction.GENERALIZE and not generalization.is_configured(category):
        return DisclosureAction.BLOCK_REQUEST
    return action


def _resolve_actions_and_generalized_values(
    ordered: list[SensitiveSpan],
) -> tuple[list[DisclosureAction], dict[int, str]]:
    """Resolve every span's action *and*, for GENERALIZE actions, attempt the
    generalization itself -- all before any text slicing happens.

    Issue #16 (2b): a category can have a configured strategy yet still fail
    to parse a *particular* value (e.g. a free-text ``Salary:`` field). That
    used to raise ``GeneralizationError`` out of ``_allowed_result`` mid-slice,
    with a half-built payload already in progress. Attempting the
    generalization here, in the same pre-pass that already downgrades an
    unconfigured category, means a parse failure downgrades that one span to
    BLOCK_REQUEST exactly like any other fail-closed category -- so the
    request blocks with an empty payload instead of raising.

    Returns the resolved actions (same order as ``ordered``) plus a map from
    span index to its precomputed generalized value, populated only for
    spans whose action is (still) GENERALIZE. ``_allowed_result`` reads from
    that map instead of calling ``generalization.generalize`` again, so a
    GENERALIZE span it lays out is guaranteed already-resolved.
    """
    actions: list[DisclosureAction] = []
    generalized_values: dict[int, str] = {}
    for index, span in enumerate(ordered):
        action = _resolve_action(span.category)
        if action is DisclosureAction.GENERALIZE:
            try:
                generalized_values[index] = generalization.generalize(span.category, span.value)
            except generalization.GeneralizationError:
                action = DisclosureAction.BLOCK_REQUEST
        actions.append(action)
    return actions, generalized_values


class StaticSanitizer:
    """Static Sanitization (B1): disclosure control independent of task and policy.

    Applies the fixed ``ACTIONS`` mapping above to detected spans, producing
    an auditable ``Transformation`` list and an external payload. Overlaps
    are resolved defensively (via the same rule the detector uses) so a
    caller passing raw, unresolved spans cannot corrupt payload slicing.

    Irreversible by construction: REMOVE drops the value, GENERALIZE replaces
    it with a coarsened band/period from ``transformations.generalization``
    (issue #16), BLOCK_REQUEST blocks the whole request rather than
    partially disclosing it. A category outside ``ACTIONS`` -- or mapped to
    GENERALIZE with no registered generalization strategy -- fails closed
    (BLOCK_REQUEST) instead of risking a silent leak -- mirroring the
    project's fail-closed policy stance, but decided entirely locally,
    without calling the policy engine.

    ``request.task`` and ``request.context`` are intentionally never read:
    This treatment's output depends only on ``request.text`` and the supplied spans.
    """

    treatment = Treatment.STATIC_SANITIZATION

    def sanitize(self, request: DisclosureRequest, spans: list[SensitiveSpan]) -> DisclosureResult:
        tracer = get_tracer()
        with tracer.start_as_current_span("static_sanitization.sanitize") as otel_span:
            spans = list(spans)
            otel_span.set_attribute("treatment", self.treatment.value)

            # Boundary check before any slicing: a span whose offsets are
            # out of bounds or do not match its claimed value against
            # ``request.text`` must fail closed rather than reach
            # ``resolve_overlaps``/``_allowed_result``, where a malformed
            # offset can leave the original value in an "allowed" payload
            # (issue #17).
            if not spans_are_valid(spans, request.text):
                otel_span.set_attribute("static_sanitization.span_count", len(spans))
                otel_span.set_attribute("static_sanitization.blocked", True)
                otel_span.set_attribute(
                    "static_sanitization.categories", sorted({s.category for s in spans})
                )
                return self._invalid_span_result(spans)

            ordered = resolve_overlaps(spans)
            actions, generalized_values = _resolve_actions_and_generalized_values(ordered)
            blocked = DisclosureAction.BLOCK_REQUEST in actions

            # Metadata only: categories, counts and a block flag -- never the
            # detected value, the raw text, or the payload.
            otel_span.set_attribute("static_sanitization.span_count", len(ordered))
            otel_span.set_attribute("static_sanitization.blocked", blocked)
            otel_span.set_attribute(
                "static_sanitization.categories", sorted({s.category for s in ordered})
            )

            if blocked:
                return self._blocked_result(ordered, actions)
            return self._allowed_result(request.text, ordered, actions, generalized_values)

    @staticmethod
    def _blocked_result(
        ordered: list[SensitiveSpan], actions: list[DisclosureAction]
    ) -> DisclosureResult:
        blocking_categories = sorted(
            {
                span.category
                for span, action in zip(ordered, actions)
                if action is DisclosureAction.BLOCK_REQUEST
            }
        )
        decisions = [
            PolicyDecision(
                category=category,
                action=DisclosureAction.BLOCK_REQUEST,
                reason="B1 static baseline blocks this category unconditionally",
                allowed_actions=[DisclosureAction.BLOCK_REQUEST],
            )
            for category in blocking_categories
        ]
        return DisclosureResult(
            external_payload="",
            decisions=decisions,
            transformations=[],
            status="blocked",
        )

    @staticmethod
    def _invalid_span_result(spans: list[SensitiveSpan]) -> DisclosureResult:
        # Fail closed for the whole request rather than trying to identify
        # and drop only the offending span: a span with malformed offsets
        # cannot be safely sliced, so its category (and, conservatively, the
        # rest of the batch) is blocked rather than partially disclosed.
        categories = sorted({span.category for span in spans})
        decisions = [
            PolicyDecision(
                category=category,
                action=DisclosureAction.BLOCK_REQUEST,
                reason=(
                    "B1 static baseline blocks: span offsets are missing, out of "
                    "bounds, or do not match the source text"
                ),
                allowed_actions=[DisclosureAction.BLOCK_REQUEST],
            )
            for category in categories
        ]
        return DisclosureResult(
            external_payload="",
            decisions=decisions,
            transformations=[],
            status="blocked",
        )

    @staticmethod
    def _allowed_result(
        text: str,
        ordered: list[SensitiveSpan],
        actions: list[DisclosureAction],
        generalized_values: dict[int, str],
    ) -> DisclosureResult:
        payload_parts: list[str] = []
        transformations: list[Transformation] = []
        decisions: list[PolicyDecision] = []
        seen_categories: set[str] = set()
        cursor = 0

        for index, (span, action) in enumerate(zip(ordered, actions)):
            # Offsets are guaranteed present, in-bounds and value-matched by
            # this point: SensitiveSpan requires them, and spans_are_valid()
            # already validated them against `text` before sanitize() got here.
            start, end = span.start, span.end
            payload_parts.append(text[cursor:start])

            if action is DisclosureAction.REMOVE:
                transformed = None
            elif action is DisclosureAction.GENERALIZE:
                # Already resolved, before any slicing started, by
                # _resolve_actions_and_generalized_values -- a GENERALIZE
                # span only reaches _allowed_result (i.e. `blocked` was
                # False) once its value has already been generalized
                # successfully, so this lookup cannot raise or be missing.
                transformed = generalized_values[index]
            else:  # PRESERVE
                transformed = span.value

            payload_parts.append(transformed or "")
            transformations.append(
                Transformation(
                    category=span.category,
                    original=span.value,
                    transformed=transformed,
                    action=action,
                )
            )

            if span.category not in seen_categories:
                seen_categories.add(span.category)
                decisions.append(
                    PolicyDecision(
                        category=span.category,
                        action=action,
                        reason="B1 static baseline mapping",
                        allowed_actions=[action],
                    )
                )

            cursor = end

        payload_parts.append(text[cursor:])

        return DisclosureResult(
            external_payload="".join(payload_parts),
            decisions=decisions,
            transformations=transformations,
            status="allowed",
        )
