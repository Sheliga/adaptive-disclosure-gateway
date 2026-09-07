"""Pins the Vault acceptance criteria from issue #3: stable pseudonyms per
scope, no sharing across scopes/scope_keys, collision handling, and
authorized local reconstruction.
"""

from adaptive_disclosure_gateway.domain import PseudonymScope
from adaptive_disclosure_gateway.vault import InMemoryVault


def test_pseudonymize_is_stable_within_the_same_scope_and_key():
    vault = InMemoryVault()

    first = vault.pseudonymize(PseudonymScope.SESSION, "user-1", "employee_name", "Ana Souza")
    second = vault.pseudonymize(PseudonymScope.SESSION, "user-1", "employee_name", "Ana Souza")

    assert first == second


def test_different_scope_keys_do_not_share_mappings():
    vault = InMemoryVault()

    user_1 = vault.pseudonymize(PseudonymScope.SESSION, "user-1", "employee_name", "Ana Souza")
    user_2 = vault.pseudonymize(PseudonymScope.SESSION, "user-2", "employee_name", "Ana Souza")

    assert user_1 != user_2
    # A pseudonym issued under user-1's partition must not resolve inside
    # user-2's partition, even for the identical underlying value.
    assert vault.reconstruct(PseudonymScope.SESSION, "user-2", user_1) is None
    assert vault.reconstruct(PseudonymScope.SESSION, "user-1", user_1) == "Ana Souza"


def test_different_scopes_do_not_share_mappings_even_with_the_same_key():
    vault = InMemoryVault()

    session_scoped = vault.pseudonymize(PseudonymScope.SESSION, "k", "employee_name", "Ana Souza")
    org_scoped = vault.pseudonymize(PseudonymScope.ORGANIZATION, "k", "employee_name", "Ana Souza")

    assert session_scoped != org_scoped
    assert vault.reconstruct(PseudonymScope.ORGANIZATION, "k", session_scoped) is None
    assert vault.reconstruct(PseudonymScope.SESSION, "k", org_scoped) is None


def test_collision_between_different_originals_never_shares_a_pseudonym():
    # A token factory that ignores the request entirely, forcing every
    # candidate pseudonym for every value to collide. This proves the vault's
    # collision handling actually disambiguates by mutating the emitted
    # string, not by hoping the generator varies (issue #24: the generator
    # is now an opaque random token factory rather than a digest of the
    # value, but the same forced-collision guarantee must still hold).
    def colliding_token_factory() -> str:
        return "deadbeef"

    vault = InMemoryVault(token_factory=colliding_token_factory)

    first = vault.pseudonymize(PseudonymScope.SESSION, "k", "employee_name", "Ana Souza")
    second = vault.pseudonymize(PseudonymScope.SESSION, "k", "employee_name", "Bruno Lima")
    third = vault.pseudonymize(PseudonymScope.SESSION, "k", "employee_name", "Carla Dias")

    assert len({first, second, third}) == 3
    assert vault.reconstruct(PseudonymScope.SESSION, "k", first) == "Ana Souza"
    assert vault.reconstruct(PseudonymScope.SESSION, "k", second) == "Bruno Lima"
    assert vault.reconstruct(PseudonymScope.SESSION, "k", third) == "Carla Dias"


def test_reconstruct_returns_none_for_a_pseudonym_it_never_issued():
    vault = InMemoryVault()

    assert vault.reconstruct(PseudonymScope.SESSION, "k", "PSEUDO-employee_name-notreal") is None


def test_default_production_vaults_are_not_required_to_agree_on_a_pseudonym():
    # Issue #24: the opposite of the old unkeyed-digest guarantee. Two
    # independently constructed production vaults (default CSPRNG token
    # factory) must not emit the same pseudonym for the same original --
    # otherwise an observer holding payloads produced by two different vault
    # instances could correlate them by pseudonym string alone, which is
    # exactly the offline-guessing surface this issue closes. (This can only
    # fail flakily on an astronomically unlikely token collision, given
    # 128 bits of CSPRNG entropy per token.)
    first_vault = InMemoryVault()
    second_vault = InMemoryVault()

    first = first_vault.pseudonymize(PseudonymScope.DOCUMENT, "doc-1", "cpf", "123.456.789-09")
    second = second_vault.pseudonymize(PseudonymScope.DOCUMENT, "doc-1", "cpf", "123.456.789-09")

    assert first != second


def test_injected_deterministic_token_factory_reproduces_across_vault_instances():
    # Experiments still need reproducibility: an explicitly injected,
    # deterministic test-only token factory makes two independent vault
    # instances agree -- without requiring the production default (above)
    # to do so.
    def make_sequential_factory():
        counter = iter(range(10_000))
        return lambda: f"seed{next(counter):06d}"

    first_vault = InMemoryVault(token_factory=make_sequential_factory())
    second_vault = InMemoryVault(token_factory=make_sequential_factory())

    first = first_vault.pseudonymize(PseudonymScope.DOCUMENT, "doc-1", "cpf", "123.456.789-09")
    second = second_vault.pseudonymize(PseudonymScope.DOCUMENT, "doc-1", "cpf", "123.456.789-09")

    assert first == second


def test_default_token_has_sufficient_entropy_to_resist_offline_guessing():
    # Issue #24: production pseudonyms must not be practically enumerable.
    # The token portion of the emitted pseudonym must carry enough entropy
    # (>= 128 bits / 32 hex characters) that brute-forcing it offline is
    # infeasible -- unlike the old 12-hex-character truncated digest of a
    # public/predictable input, which was exhaustible in seconds for a
    # low-entropy category such as CPF.
    vault = InMemoryVault()

    pseudonym = vault.pseudonymize(PseudonymScope.SESSION, "user-1", "cpf", "123.456.789-09")

    token = pseudonym[len("PSEUDO-cpf-") :]
    assert len(token) >= 32
    int(token, 16)  # must be valid hex -- raises ValueError otherwise
