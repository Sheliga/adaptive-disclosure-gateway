from __future__ import annotations

import time

from adaptive_disclosure_gateway.detection.overlap import resolve_overlaps
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    DisclosureResult,
    GovernanceContext,
    PolicyDecision,
    PseudonymScope,
    SensitiveSpan,
    Transformation,
    Treatment,
)
from adaptive_disclosure_gateway.observability import get_tracer
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations.span_validation import spans_are_valid
from adaptive_disclosure_gateway.vault import Vault

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
}

# TODO(T13 / issue #16): replace with the semantic generalization registry.
# Kept identical to B1's current placeholder for this commit so B2 lands
# without depending on unmerged T13 work; both treatments switch to real
# generalization together in the next commit.
_GENERALIZED_PLACEHOLDER = "[REDACTED:{category}]"


def _scope_key(scope: PseudonymScope, context: GovernanceContext) -> str:
    """Deterministically derive a vault partition key from governance
    context alone, so a later, separate call to ``reconstruct()`` with an
    equal context recomputes the identical key used during ``sanitize()``
    without needing extra state threaded through ``DisclosureResult`` (whose
    shape must stay identical across every treatment).

    Known Milestone 1 simplification: ``GovernanceContext`` does not yet
    model an explicit per-request or per-document identifier (no session or
    document orchestration layer exists yet -- see
    docs/implementation-status.md). REQUEST and DOCUMENT scope therefore key
    on the same requester identity as SESSION scope; only ORGANIZATION scope
    (shared by every requester in a domain) is actually distinguishable from
    the others today. All four remain mutually isolated in the vault because
    the scope name itself is folded into the key, so this simplification
    never lets two *different* scopes share a mapping -- it only means
    REQUEST/DOCUMENT are, for now, as durable as SESSION.
    """
    requester_key = context.requester_id or context.requester_role or "anonymous"
    if scope is PseudonymScope.ORGANIZATION:
        return f"organization:{context.domain}"
    return f"{scope.value}:{context.domain}:{requester_key}"


class ReversiblePseudonymizer:
    """Reversible Pseudonymization (B2): B1's static mapping, plus a local,
    reversible vault for categories B1 could only remove irreversibly.

    ``request.task`` is intentionally never read for choosing an action:
    the category -> action mapping stays static and task-independent, exactly
    like B1. That staticness is what B2->B3 isolates (see
    docs/experimental-design.md) -- B3 is the first treatment allowed to let
    task relevance influence the choice of action.
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
                return self._invalid_span_result(spans)

            ordered = resolve_overlaps(spans)
            actions = [
                ACTIONS.get(span.category, DisclosureAction.BLOCK_REQUEST) for span in ordered
            ]
            blocked = DisclosureAction.BLOCK_REQUEST in actions

            # Metadata only: categories, counts, a block flag and timing --
            # never the detected value, the raw text, the payload, or any
            # pseudonym/vault content.
            otel_span.set_attribute("reversible_pseudonymization.span_count", len(ordered))
            otel_span.set_attribute("reversible_pseudonymization.blocked", blocked)
            otel_span.set_attribute(
                "reversible_pseudonymization.categories", sorted({s.category for s in ordered})
            )

            if blocked:
                otel_span.set_attribute(
                    "reversible_pseudonymization.duration_ms",
                    (time.perf_counter() - started) * 1000,
                )
                return self._blocked_result(ordered, actions)

            scope = self._policies.resolve_pseudonym_scope(request.context)
            scope_key = _scope_key(scope, request.context)
            otel_span.set_attribute("reversible_pseudonymization.pseudonym_scope", scope.value)

            result = self._allowed_result(request.text, ordered, actions, scope, scope_key)
            otel_span.set_attribute(
                "reversible_pseudonymization.duration_ms", (time.perf_counter() - started) * 1000
            )
            return result

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
            pseudonymized = [
                t for t in result.transformations if t.action is DisclosureAction.PSEUDONYMIZE
            ]
            otel_span.set_attribute(
                "reversible_pseudonymization.pseudonym_count", len(pseudonymized)
            )

            authorized = self._policies.is_reconstruction_authorized(context)
            otel_span.set_attribute(
                "reversible_pseudonymization.reconstruction_authorized", authorized
            )
            if not authorized:
                return response_text

            scope = self._policies.resolve_pseudonym_scope(context)
            scope_key = _scope_key(scope, context)

            # Longest pseudonym first: defensive against one pseudonym
            # string happening to be a substring of another, which would
            # otherwise make replacement order-dependent.
            ordered_pseudonyms = sorted(
                (t.transformed for t in pseudonymized if t.transformed is not None),
                key=len,
                reverse=True,
            )

            reconstructed = response_text
            for pseudonym in ordered_pseudonyms:
                original = self._vault.reconstruct(scope, scope_key, pseudonym)
                if original is not None:
                    reconstructed = reconstructed.replace(pseudonym, original)
            return reconstructed

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
                reason="B2 reversible pseudonymization blocks this category unconditionally",
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
        categories = sorted({span.category for span in spans})
        decisions = [
            PolicyDecision(
                category=category,
                action=DisclosureAction.BLOCK_REQUEST,
                reason=(
                    "B2 reversible pseudonymization blocks: span offsets are missing, out "
                    "of bounds, or do not match the source text"
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

    def _allowed_result(
        self,
        text: str,
        ordered: list[SensitiveSpan],
        actions: list[DisclosureAction],
        scope: PseudonymScope,
        scope_key: str,
    ) -> DisclosureResult:
        payload_parts: list[str] = []
        transformations: list[Transformation] = []
        decisions: list[PolicyDecision] = []
        seen_categories: set[str] = set()
        cursor = 0
        any_pseudonymized = False

        for span, action in zip(ordered, actions):
            start, end = span.start, span.end
            payload_parts.append(text[cursor:start])

            if action is DisclosureAction.REMOVE:
                transformed = None
            elif action is DisclosureAction.GENERALIZE:
                transformed = _GENERALIZED_PLACEHOLDER.format(category=span.category)
            elif action is DisclosureAction.PSEUDONYMIZE:
                transformed = self._vault.pseudonymize(scope, scope_key, span.category, span.value)
                any_pseudonymized = True
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
                        reason="B2 reversible pseudonymization: static category mapping",
                        allowed_actions=[action],
                    )
                )

            cursor = end

        payload_parts.append(text[cursor:])

        return DisclosureResult(
            external_payload="".join(payload_parts),
            decisions=decisions,
            transformations=transformations,
            reconstruction_required=any_pseudonymized,
            status="allowed",
        )
