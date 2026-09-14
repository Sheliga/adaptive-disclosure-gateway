"""Adversarial and behavioral tests for the sealed vault-explorer reference
(T29 / issue #72): ``application/vault_explorer.py``.

Mirrors ``tests/test_restore_handle.py``'s style: every test targets a real
defect this mechanism could plausibly have -- tampering, truncation, a
wrong-process key, expiry, cross-decision bleed, and the fail-closed issuance
rules (blocked decision, ORGANIZATION scope, missing scope-key identifier,
vault mismatch).
"""

from __future__ import annotations

import base64

import pytest

from adaptive_disclosure_gateway.application.vault_explorer import (
    VAULT_EXPLORER_REFERENCE_TTL_SECONDS,
    VaultExplorerReferenceError,
    VaultExplorerSealer,
    VaultExplorerView,
)
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureResult,
    GovernanceContext,
    PolicyDecision,
    PseudonymScope,
    Transformation,
)
from adaptive_disclosure_gateway.pipeline import DisclosureDecision
from adaptive_disclosure_gateway.vault import InMemoryVault

ORIGINAL_A = "Ana Souza"
ORIGINAL_B = "Carlos Lima"


class _FrozenClock:
    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class _StubPolicyRepository:
    """Duck-typed stand-in exposing only what ``issue_reference`` calls
    (``resolve_pseudonym_scope``) -- the real ``PolicyRepository`` resolves
    scope from on-disk policy config, which is more than these unit tests
    need to control precisely.
    """

    def __init__(self, scope: PseudonymScope) -> None:
        self._scope = scope

    def resolve_pseudonym_scope(self, context: GovernanceContext) -> PseudonymScope:
        return self._scope


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
        "provider_class": "fake",
        "session_id": "demo-session",
    }
    values.update(overrides)
    return GovernanceContext(**values)


def _decision(
    transformations: list[Transformation], *, status: str = "allowed"
) -> DisclosureDecision:
    result = DisclosureResult(
        external_payload="irrelevant for this module",
        decisions=[
            PolicyDecision(category=t.category, action=t.action, reason="test")
            for t in transformations
        ],
        transformations=transformations,
        status=status,
    )
    return DisclosureDecision(spans=[], result=result)


def _pseudonymize(category: str, original: str, transformed: str) -> Transformation:
    return Transformation(
        category=category,
        original=original,
        transformed=transformed,
        action=DisclosureAction.PSEUDONYMIZE,
    )


def _preserve(category: str, value: str) -> Transformation:
    return Transformation(
        category=category, original=value, transformed=value, action=DisclosureAction.PRESERVE
    )


def _sealer(clock=None) -> VaultExplorerSealer:
    return VaultExplorerSealer(clock=clock if clock is not None else _FrozenClock())


def _flip_a_ciphertext_byte(token: str) -> str:
    prefix, blob = token.split(".", 1)
    raw = bytearray(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))
    middle = len(raw) // 2
    raw[middle] ^= 0xFF
    tampered = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode("ascii")
    return f"{prefix}.{tampered}"


# --- round trip ---------------------------------------------------------------


def test_issue_then_explore_round_trips_pseudonymize_entries_only():
    vault = InMemoryVault()
    context = _context()
    key = "session:hr:demo-session"
    pseudonym = vault.pseudonymize(PseudonymScope.SESSION, key, "employee_name", ORIGINAL_A)

    decision = _decision(
        [
            _pseudonymize("employee_name", ORIGINAL_A, pseudonym),
            _preserve("department", "Engineering"),
        ]
    )
    sealer = _sealer()
    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.SESSION), vault
    )
    assert isinstance(token, str)
    assert token.startswith("vx1.")

    view = sealer.explore(token, vault)
    assert isinstance(view, VaultExplorerView)
    assert view.scope == "session"
    assert len(view.entries) == 1
    entry = view.entries[0]
    assert entry.category == "employee_name"
    assert entry.pseudonym == pseudonym
    assert entry.original == ORIGINAL_A
    assert entry.present is True


def test_no_pseudonymize_transformations_issue_a_token_with_null_scope_and_no_entries():
    vault = InMemoryVault()
    context = _context()
    decision = _decision([_preserve("department", "Engineering")])
    sealer = _sealer()

    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.SESSION), vault
    )
    assert token is not None

    view = sealer.explore(token, vault)
    assert view.scope is None
    assert view.entries == ()


def test_deduplicates_identical_pseudonym_category_pairs_keeping_first_seen_order():
    vault = InMemoryVault()
    context = _context()
    key = "session:hr:demo-session"
    pseudonym = vault.pseudonymize(PseudonymScope.SESSION, key, "employee_name", ORIGINAL_A)

    decision = _decision(
        [
            _pseudonymize("employee_name", ORIGINAL_A, pseudonym),
            # Same (category, pseudonym) pair repeated -- must be
            # deduplicated, keeping the first-seen original for the
            # verification step, not this (deliberately wrong) second one.
            _pseudonymize("employee_name", "some-other-value-never-shown", pseudonym),
        ]
    )
    sealer = _sealer()
    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.SESSION), vault
    )
    assert token is not None

    view = sealer.explore(token, vault)
    assert len(view.entries) == 1
    assert view.entries[0].original == ORIGINAL_A


# --- fail-closed issuance ------------------------------------------------------


def test_blocked_decision_never_issues_a_token():
    vault = InMemoryVault()
    context = _context()
    decision = _decision([], status="blocked")
    sealer = _sealer()

    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.SESSION), vault
    )
    assert token is None


def test_organization_scope_never_issues_a_token():
    vault = InMemoryVault()
    context = _context()
    pseudonym = vault.pseudonymize(
        PseudonymScope.ORGANIZATION, "organization:hr", "employee_name", ORIGINAL_A
    )
    decision = _decision([_pseudonymize("employee_name", ORIGINAL_A, pseudonym)])
    sealer = _sealer()

    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.ORGANIZATION), vault
    )
    assert token is None


def test_missing_scope_key_identifier_never_issues_a_token():
    vault = InMemoryVault()
    # REQUEST scope needs context.request_id -- deliberately absent.
    context = _context(request_id=None)
    pseudonym = vault.pseudonymize(
        PseudonymScope.REQUEST, "request:hr:whatever", "employee_name", ORIGINAL_A
    )
    decision = _decision([_pseudonymize("employee_name", ORIGINAL_A, pseudonym)])
    sealer = _sealer()

    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.REQUEST), vault
    )
    assert token is None


def test_vault_mismatch_fails_closed_and_issues_no_token():
    """The vault does not actually hold the pseudonym the (fabricated)
    transformation claims -- issuance must refuse rather than seal a
    reference that would silently resolve to nothing, or worse, to a
    different original than the decision itself recorded.
    """
    vault = InMemoryVault()  # empty: never pseudonymized anything
    context = _context()
    decision = _decision(
        [_pseudonymize("employee_name", ORIGINAL_A, "PSEUDO-employee_name-deadbeef")]
    )
    sealer = _sealer()

    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.SESSION), vault
    )
    assert token is None


# --- tamper / malformed / cross-process rejection ------------------------------


def _issued_token(vault=None) -> tuple[VaultExplorerSealer, str]:
    vault = vault if vault is not None else InMemoryVault()
    context = _context()
    key = "session:hr:demo-session"
    pseudonym = vault.pseudonymize(PseudonymScope.SESSION, key, "employee_name", ORIGINAL_A)
    decision = _decision([_pseudonymize("employee_name", ORIGINAL_A, pseudonym)])
    sealer = _sealer()
    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.SESSION), vault
    )
    assert token is not None
    return sealer, token


def test_tampered_ciphertext_is_rejected():
    sealer, token = _issued_token()
    tampered = _flip_a_ciphertext_byte(token)
    with pytest.raises(VaultExplorerReferenceError):
        sealer.explore(tampered, InMemoryVault())


def test_truncated_token_is_rejected():
    sealer, token = _issued_token()
    with pytest.raises(VaultExplorerReferenceError):
        sealer.explore(token[:-10], InMemoryVault())


def test_wrong_prefix_is_rejected():
    sealer, token = _issued_token()
    _, blob = token.split(".", 1)
    with pytest.raises(VaultExplorerReferenceError):
        sealer.explore(f"zz9.{blob}", InMemoryVault())


def test_empty_token_is_rejected():
    sealer, _ = _issued_token()
    with pytest.raises(VaultExplorerReferenceError):
        sealer.explore("", InMemoryVault())


def test_random_forged_token_is_rejected():
    sealer, _ = _issued_token()
    forged = "vx1." + base64.urlsafe_b64encode(b"\x00" * 40).rstrip(b"=").decode("ascii")
    with pytest.raises(VaultExplorerReferenceError):
        sealer.explore(forged, InMemoryVault())


def test_token_from_a_different_process_instance_is_rejected():
    """Simulates a restart: a new ``VaultExplorerSealer`` (fresh random key)
    must reject a token issued by a previous instance, by design (module
    docstring) -- this is a deliberate non-durability property, not a bug.
    """
    _issuer, token = _issued_token()
    new_instance = _sealer()
    with pytest.raises(VaultExplorerReferenceError):
        new_instance.explore(token, InMemoryVault())


def test_expired_token_is_rejected_via_injected_clock():
    vault = InMemoryVault()
    context = _context()
    key = "session:hr:demo-session"
    pseudonym = vault.pseudonymize(PseudonymScope.SESSION, key, "employee_name", ORIGINAL_A)
    decision = _decision([_pseudonymize("employee_name", ORIGINAL_A, pseudonym)])
    clock = _FrozenClock()
    sealer = _sealer(clock=clock)

    token = sealer.issue_reference(
        decision, context, _StubPolicyRepository(PseudonymScope.SESSION), vault
    )
    assert token is not None

    clock.now += VAULT_EXPLORER_REFERENCE_TTL_SECONDS + 1
    with pytest.raises(VaultExplorerReferenceError):
        sealer.explore(token, vault)


def test_no_error_message_ever_contains_the_original_or_pseudonym():
    sealer, token = _issued_token()
    tampered = _flip_a_ciphertext_byte(token)
    try:
        sealer.explore(tampered, InMemoryVault())
        pytest.fail("expected VaultExplorerReferenceError")
    except VaultExplorerReferenceError as exc:
        assert ORIGINAL_A not in str(exc)
        assert token not in str(exc)
        assert tampered not in str(exc)


# --- isolation between two references on one shared vault ---------------------


def test_two_interleaved_tokens_each_see_only_their_own_entries():
    vault = InMemoryVault()
    sealer = _sealer()

    context_a = _context(session_id="session-a")
    key_a = "session:hr:session-a"
    pseudonym_a = vault.pseudonymize(PseudonymScope.SESSION, key_a, "employee_name", ORIGINAL_A)
    token_a = sealer.issue_reference(
        _decision([_pseudonymize("employee_name", ORIGINAL_A, pseudonym_a)]),
        context_a,
        _StubPolicyRepository(PseudonymScope.SESSION),
        vault,
    )

    context_b = _context(session_id="session-b")
    key_b = "session:hr:session-b"
    pseudonym_b = vault.pseudonymize(PseudonymScope.SESSION, key_b, "employee_name", ORIGINAL_B)
    token_b = sealer.issue_reference(
        _decision([_pseudonymize("employee_name", ORIGINAL_B, pseudonym_b)]),
        context_b,
        _StubPolicyRepository(PseudonymScope.SESSION),
        vault,
    )

    assert token_a is not None and token_b is not None
    assert token_a != token_b

    view_a = sealer.explore(token_a, vault)
    view_b = sealer.explore(token_b, vault)

    assert view_a.entries[0].original == ORIGINAL_A
    assert view_b.entries[0].original == ORIGINAL_B
    assert ORIGINAL_B not in [e.original for e in view_a.entries]
    assert ORIGINAL_A not in [e.original for e in view_b.entries]
    assert pseudonym_a != pseudonym_b


def test_concurrent_explore_calls_are_isolated_across_threads():
    from concurrent.futures import ThreadPoolExecutor

    vault = InMemoryVault()
    sealer = _sealer()
    tokens_and_originals = []
    for i in range(8):
        context = _context(session_id=f"session-{i}")
        key = f"session:hr:session-{i}"
        original = f"Original-{i}"
        pseudonym = vault.pseudonymize(PseudonymScope.SESSION, key, "employee_name", original)
        token = sealer.issue_reference(
            _decision([_pseudonymize("employee_name", original, pseudonym)]),
            context,
            _StubPolicyRepository(PseudonymScope.SESSION),
            vault,
        )
        assert token is not None
        tokens_and_originals.append((token, original))

    def _explore(pair):
        token, expected_original = pair
        view = sealer.explore(token, vault)
        return view.entries[0].original == expected_original

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_explore, tokens_and_originals))

    assert all(results)
