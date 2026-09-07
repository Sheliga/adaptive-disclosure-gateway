"""Shared decision-*application* machinery for reversible, vault-backed
treatments (T07 / issue #6).

Before this module, ``ReversiblePseudonymizer`` (B2 -- Reversible
Pseudonymization) mixed two responsibilities in one class: (a) deciding
*which* ``DisclosureAction`` applies to each detected category, and (b)
*applying* that decision -- validating span offsets, resolving overlaps,
attempting GENERALIZE (failing closed if unconfigured/unparseable),
resolving pseudonym scope and authorization through ``PolicyRepository``,
storing/retrieving pseudonyms through a ``Vault``, slicing the payload, and
assembling a ``DisclosureResult``. Reconstruction mirrored the same split.

Task-aware (B3 -- Task-aware, ``transformations/task_aware.py``) needs
exactly the same "(b) apply" machinery, differing from B2 only in "(a)
decide": B2 decides from a static per-category map; B3 decides from a task
analyzer's relevance judgement over a generic, fixed action space. Extracting
(b) here lets both treatments share it verbatim rather than duplicating the
vault/scope/slicing logic -- see docs/experimental-design.md's B2->B3
comparison, which requires the reversible mechanism to stay *constant* while
only task-awareness varies. ``ReversiblePseudonymizer``'s own behavior must
not change: this module was extracted from it, not reimplemented, and every
existing B2 test stays green with no edits.

``PolicyRepository`` is used here only to resolve pseudonym scope
(``resolve_pseudonym_scope``) and to authorize reconstruction
(``is_reconstruction_authorized``) -- never to choose a category's action.
Callers (``ReversiblePseudonymizer.sanitize``, ``TaskAwareDiscloser.sanitize``)
must have already decided each span's candidate action (via their own,
treatment-specific ``decide`` callback) before calling ``apply`` below; this
module only resolves the GENERALIZE fail-closed downgrade, then applies
whatever action results.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureResult,
    GovernanceContext,
    PolicyDecision,
    PseudonymScope,
    SensitiveSpan,
    Transformation,
)
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.vault import Vault

from . import generalization

_SCOPE_IDENTIFIER_ATTR: dict[PseudonymScope, str] = {
    PseudonymScope.REQUEST: "request_id",
    PseudonymScope.DOCUMENT: "document_id",
    PseudonymScope.SESSION: "session_id",
}


def scope_key(scope: PseudonymScope, context: GovernanceContext) -> str | None:
    """Deterministically derive a vault partition key from governance
    context alone (moved verbatim from
    ``reversible_pseudonymization._scope_key`` -- see issue #23 / T16 for the
    full rationale). A later, separate call to ``reconstruct()`` with an
    equal context recomputes the identical key used during ``apply()``.

    REQUEST -> ``request_id``, DOCUMENT -> ``document_id``,
    SESSION -> ``session_id``, ORGANIZATION -> the domain alone. Returns
    ``None`` -- rather than inventing or falling back to a weaker key --
    when the resolved scope needs an identifier ``context`` does not carry.
    Callers must treat ``None`` as "fail closed".
    """
    if scope is PseudonymScope.ORGANIZATION:
        return f"organization:{context.domain}"
    identifier = getattr(context, _SCOPE_IDENTIFIER_ATTR[scope])
    if identifier is None:
        return None
    return f"{scope.value}:{context.domain}:{identifier}"


@dataclass(frozen=True)
class ActionDecision:
    """One span's already-decided outcome, handed to :func:`apply` by a
    caller that has already resolved *which* action a category maps to
    (statically for B2, via task analysis for B3).

    ``reason`` is treatment-specific, human-readable audit text -- it must
    never embed the span's ``value`` (only categories/levels/flags, per
    CLAUDE.md's no-leak invariant). ``task_required`` mirrors
    ``domain.PolicyDecision.task_required``: ``None`` when the deciding
    treatment has no notion of task necessity (B2), ``True``/``False`` when
    it does (B3), left ``None`` for a genuinely undetermined case.
    """

    action: DisclosureAction
    reason: str
    task_required: bool | None = None


@dataclass(frozen=True)
class TreatmentReasons:
    """Fixed, treatment-specific wording for the outcomes this module
    produces without per-category input from the caller's ``decide``
    callback: an invalid span, an unconditional block (every category in a
    blocked request whose own ``ActionDecision.reason`` should be used
    instead is unaffected -- this covers only the generic "some other span
    forced this block" categories that end up with no individual say), and a
    missing pseudonym-scope identifier.
    """

    invalid_spans: str
    missing_scope_identifier: str


@dataclass(frozen=True)
class ApplyOutcome:
    """Everything a treatment's own ``sanitize()`` needs to both return a
    result and populate its own (treatment-namespaced) telemetry attributes.
    """

    result: DisclosureResult
    blocked: bool
    pseudonym_scope: PseudonymScope | None


@dataclass(frozen=True)
class ReconstructionOutcome:
    """Everything a treatment's own ``reconstruct()`` needs to populate its
    own telemetry attributes alongside the reconstructed text.
    """

    text: str
    pseudonym_count: int
    authorized: bool


def _resolve_generalize_downgrades(
    ordered: list[SensitiveSpan],
    decide: Callable[[SensitiveSpan], ActionDecision],
) -> tuple[list[ActionDecision], dict[int, str]]:
    """Call ``decide`` for every span, then attempt GENERALIZE immediately
    for any span it decided GENERALIZE for -- all before any text slicing
    happens (mirrors B1/B2's own pre-pass; see issue #16 (2b)).

    A GENERALIZE decision that turns out unconfigured or unparseable is
    downgraded to BLOCK_REQUEST here, in the same pre-pass, so a parse
    failure fails that one span closed instead of raising mid-slice with a
    half-built payload. Returns the (possibly downgraded) decisions in the
    same order as ``ordered``, plus a map from span index to its precomputed
    generalized value for every span whose action is (still) GENERALIZE.
    """
    decisions: list[ActionDecision] = []
    generalized_values: dict[int, str] = {}
    for index, span in enumerate(ordered):
        decision = decide(span)
        if decision.action is DisclosureAction.GENERALIZE:
            try:
                generalized_values[index] = generalization.generalize(span.category, span.value)
            except generalization.GeneralizationError:
                decision = ActionDecision(
                    action=DisclosureAction.BLOCK_REQUEST,
                    reason=(
                        f"{decision.reason} -- but no generalization strategy is configured "
                        "for this category, or the configured strategy could not parse this "
                        "value, so the category fails closed instead of disclosing it"
                    ),
                    task_required=decision.task_required,
                )
        decisions.append(decision)
    return decisions, generalized_values


def invalid_span_result(spans: list[SensitiveSpan], reasons: TreatmentReasons) -> DisclosureResult:
    """Fail-closed result for spans that do not pass ``spans_are_valid``
    against the request text. Callers check that boundary themselves (it
    needs ``request.text``, which this module does not receive) before
    calling ``apply`` at all.
    """
    categories = sorted({span.category for span in spans})
    decisions = [
        PolicyDecision(
            category=category,
            action=DisclosureAction.BLOCK_REQUEST,
            reason=reasons.invalid_spans,
            allowed_actions=[DisclosureAction.BLOCK_REQUEST],
        )
        for category in categories
    ]
    return DisclosureResult(
        external_payload="", decisions=decisions, transformations=[], status="blocked"
    )


def _blocked_result(
    ordered: list[SensitiveSpan], decisions: list[ActionDecision]
) -> DisclosureResult:
    """Every span whose own decision resolved to BLOCK_REQUEST gets a
    ``PolicyDecision`` carrying *that span's own* reason (so B3's
    category-specific fail-closed wording -- out-of-space category,
    ambiguous relevance, analyzer failure -- survives into the audit trail
    rather than being flattened to one generic string).
    """
    by_category: dict[str, str] = {}
    for span, decision in zip(ordered, decisions):
        if decision.action is DisclosureAction.BLOCK_REQUEST:
            by_category.setdefault(span.category, decision.reason)
    policy_decisions = [
        PolicyDecision(
            category=category,
            action=DisclosureAction.BLOCK_REQUEST,
            reason=reason,
            allowed_actions=[DisclosureAction.BLOCK_REQUEST],
        )
        for category, reason in sorted(by_category.items())
    ]
    return DisclosureResult(
        external_payload="", decisions=policy_decisions, transformations=[], status="blocked"
    )


def _missing_scope_identifier_result(
    ordered: list[SensitiveSpan], reasons: TreatmentReasons
) -> DisclosureResult:
    categories = sorted({span.category for span in ordered})
    decisions = [
        PolicyDecision(
            category=category,
            action=DisclosureAction.BLOCK_REQUEST,
            reason=reasons.missing_scope_identifier,
            allowed_actions=[DisclosureAction.BLOCK_REQUEST],
        )
        for category in categories
    ]
    return DisclosureResult(
        external_payload="", decisions=decisions, transformations=[], status="blocked"
    )


def _allowed_result(
    text: str,
    ordered: list[SensitiveSpan],
    decisions: list[ActionDecision],
    generalized_values: dict[int, str],
    vault: Vault,
    scope: PseudonymScope,
    key: str,
) -> DisclosureResult:
    payload_parts: list[str] = []
    transformations: list[Transformation] = []
    policy_decisions: list[PolicyDecision] = []
    seen_categories: set[str] = set()
    cursor = 0
    any_pseudonymized = False

    for index, (span, decision) in enumerate(zip(ordered, decisions)):
        action = decision.action
        start, end = span.start, span.end
        payload_parts.append(text[cursor:start])

        if action is DisclosureAction.REMOVE:
            transformed = None
        elif action is DisclosureAction.GENERALIZE:
            # Already resolved, before any slicing started, by
            # _resolve_generalize_downgrades -- a GENERALIZE span only
            # reaches here (i.e. it was not downgraded) once its value has
            # already been generalized successfully.
            transformed = generalized_values[index]
        elif action is DisclosureAction.PSEUDONYMIZE:
            transformed = vault.pseudonymize(scope, key, span.category, span.value)
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
            policy_decisions.append(
                PolicyDecision(
                    category=span.category,
                    action=action,
                    reason=decision.reason,
                    task_required=decision.task_required,
                    allowed_actions=[action],
                )
            )

        cursor = end

    payload_parts.append(text[cursor:])

    return DisclosureResult(
        external_payload="".join(payload_parts),
        decisions=policy_decisions,
        transformations=transformations,
        reconstruction_required=any_pseudonymized,
        status="allowed",
    )


def apply(
    *,
    text: str,
    ordered: list[SensitiveSpan],
    decide: Callable[[SensitiveSpan], ActionDecision],
    policy_repository: PolicyRepository,
    vault: Vault,
    context: GovernanceContext,
    reasons: TreatmentReasons,
) -> ApplyOutcome:
    """Apply already-overlap-resolved ``ordered`` spans through ``decide``
    (the caller's category -> action decision), then the shared vault/scope
    machinery. ``ordered`` must already have passed ``spans_are_valid`` and
    ``resolve_overlaps`` -- this function does not repeat those checks.
    """
    decisions, generalized_values = _resolve_generalize_downgrades(ordered, decide)
    blocked = any(decision.action is DisclosureAction.BLOCK_REQUEST for decision in decisions)

    if blocked:
        return ApplyOutcome(
            result=_blocked_result(ordered, decisions), blocked=True, pseudonym_scope=None
        )

    scope = policy_repository.resolve_pseudonym_scope(context)
    key = scope_key(scope, context)
    if key is None:
        return ApplyOutcome(
            result=_missing_scope_identifier_result(ordered, reasons),
            blocked=True,
            pseudonym_scope=scope,
        )

    result = _allowed_result(text, ordered, decisions, generalized_values, vault, scope, key)
    return ApplyOutcome(result=result, blocked=False, pseudonym_scope=scope)


def reconstruct(
    response_text: str,
    result: DisclosureResult,
    context: GovernanceContext,
    *,
    policy_repository: PolicyRepository,
    vault: Vault,
) -> ReconstructionOutcome:
    """Authorized local reconstruction of a provider response: pseudonyms
    that this same ``result`` produced are mapped back to their original
    values. Never consults or exposes any pseudonym/original outside this
    local call. Moved verbatim from
    ``ReversiblePseudonymizer.reconstruct``.
    """
    pseudonymized = [t for t in result.transformations if t.action is DisclosureAction.PSEUDONYMIZE]

    authorized = policy_repository.is_reconstruction_authorized(context)
    if not authorized:
        return ReconstructionOutcome(
            text=response_text, pseudonym_count=len(pseudonymized), authorized=False
        )

    scope = policy_repository.resolve_pseudonym_scope(context)
    key = scope_key(scope, context)
    if key is None:
        # Fail closed (issue #23 / T16): the resolved scope requires a
        # lifecycle identifier ``context`` does not carry. Return nothing
        # reconstructed rather than falling back to another partition.
        return ReconstructionOutcome(
            text=response_text, pseudonym_count=len(pseudonymized), authorized=True
        )

    # Longest pseudonym first: defensive against one pseudonym string
    # happening to be a substring of another, which would otherwise make
    # replacement order-dependent.
    ordered_pseudonyms = sorted(
        (t.transformed for t in pseudonymized if t.transformed is not None),
        key=len,
        reverse=True,
    )

    reconstructed = response_text
    for pseudonym in ordered_pseudonyms:
        original = vault.reconstruct(scope, key, pseudonym)
        if original is not None:
            reconstructed = reconstructed.replace(pseudonym, original)

    return ReconstructionOutcome(
        text=reconstructed, pseudonym_count=len(pseudonymized), authorized=True
    )
