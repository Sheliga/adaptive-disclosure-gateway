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
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations.span_validation import spans_are_valid
from adaptive_disclosure_gateway.vault import Vault

from . import generalization

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


def _resolve_action(category: str) -> DisclosureAction:
    """Look up ``category``'s static action, downgrading GENERALIZE to
    BLOCK_REQUEST if no generalization strategy is configured for it
    (issue #16: fail closed rather than silently disclosing the original
    value). Resolved before any text slicing happens.
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
    request blocks with an empty payload instead of raising. Mirrors
    ``static_sanitization._resolve_actions_and_generalized_values`` (B1); both
    treatments need the identical fix (see tests/test_static_sanitization.py
    and tests/test_reversible_pseudonymization.py).

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


_SCOPE_IDENTIFIER_ATTR: dict[PseudonymScope, str] = {
    PseudonymScope.REQUEST: "request_id",
    PseudonymScope.DOCUMENT: "document_id",
    PseudonymScope.SESSION: "session_id",
}


def _scope_key(scope: PseudonymScope, context: GovernanceContext) -> str | None:
    """Deterministically derive a vault partition key from governance
    context alone, so a later, separate call to ``reconstruct()`` with an
    equal context recomputes the identical key used during ``sanitize()``
    without needing extra state threaded through ``DisclosureResult`` (whose
    shape must stay identical across every treatment).

    Issue #23 / T16: each scope now keys on the lifecycle identifier its name
    actually promises, not on requester identity --
    REQUEST -> ``request_id``, DOCUMENT -> ``document_id``,
    SESSION -> ``session_id``, ORGANIZATION -> the domain alone (shared by
    every requester in the domain, unchanged from before). There is no
    fallback to ``requester_id``/``requester_role``: a partition durable
    beyond its scope's intended lifetime, or shared by two different users
    who happen to lack an identifier, is exactly the defect this closes.

    Returns ``None`` -- rather than inventing or falling back to a weaker
    key -- when the resolved scope needs an identifier that ``context`` does
    not carry. Callers must treat ``None`` as "fail closed": block the
    request in ``sanitize()``, return nothing reconstructed in
    ``reconstruct()``. Never let a missing identifier silently resolve some
    other partition.
    """
    if scope is PseudonymScope.ORGANIZATION:
        return f"organization:{context.domain}"
    identifier = getattr(context, _SCOPE_IDENTIFIER_ATTR[scope])
    if identifier is None:
        return None
    return f"{scope.value}:{context.domain}:{identifier}"


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
            actions, generalized_values = _resolve_actions_and_generalized_values(ordered)
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
                    elapsed_ms_since(started),
                )
                return self._blocked_result(ordered, actions)

            scope = self._policies.resolve_pseudonym_scope(request.context)
            scope_key = _scope_key(scope, request.context)
            otel_span.set_attribute("reversible_pseudonymization.pseudonym_scope", scope.value)

            if scope_key is None:
                # Fail closed (issue #23 / T16): the resolved scope requires
                # a lifecycle identifier the governance context does not
                # carry. Block the whole request rather than resolving some
                # other, weaker partition -- see _scope_key's docstring.
                otel_span.set_attribute("reversible_pseudonymization.blocked", True)
                otel_span.set_attribute(
                    "reversible_pseudonymization.duration_ms",
                    elapsed_ms_since(started),
                )
                return self._missing_scope_identifier_result(ordered)

            result = self._allowed_result(
                request.text, ordered, actions, generalized_values, scope, scope_key
            )
            otel_span.set_attribute(
                "reversible_pseudonymization.duration_ms", elapsed_ms_since(started)
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
            if scope_key is None:
                # Fail closed (issue #23 / T16): the resolved scope requires
                # a lifecycle identifier ``context`` does not carry. Return
                # nothing reconstructed rather than falling back to another
                # partition -- never substitute in an original value here.
                return response_text

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
    def _missing_scope_identifier_result(ordered: list[SensitiveSpan]) -> DisclosureResult:
        """Fail-closed result for issue #23 / T16: the resolved pseudonym
        scope needs a lifecycle identifier (``request_id``, ``document_id``
        or ``session_id``) that the governance context does not carry.
        Blocks the whole request rather than resolving some other,
        unintended partition -- see ``_scope_key``.
        """
        categories = sorted({span.category for span in ordered})
        decisions = [
            PolicyDecision(
                category=category,
                action=DisclosureAction.BLOCK_REQUEST,
                reason=(
                    "B2 reversible pseudonymization blocks: the resolved pseudonym scope "
                    "requires a lifecycle identifier the governance context does not provide"
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
        generalized_values: dict[int, str],
        scope: PseudonymScope,
        scope_key: str,
    ) -> DisclosureResult:
        payload_parts: list[str] = []
        transformations: list[Transformation] = []
        decisions: list[PolicyDecision] = []
        seen_categories: set[str] = set()
        cursor = 0
        any_pseudonymized = False

        for index, (span, action) in enumerate(zip(ordered, actions)):
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
