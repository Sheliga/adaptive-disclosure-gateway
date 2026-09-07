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
    # A digest function that ignores its input entirely, forcing every
    # candidate pseudonym for every value to collide. This proves the vault's
    # collision handling actually disambiguates by mutating the emitted
    # string, not by hoping the digest varies.
    def colliding_digest(_payload: str) -> str:
        return "deadbeef"

    vault = InMemoryVault(digest=colliding_digest)

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


def test_pseudonymize_is_deterministic_across_independent_vault_instances():
    # Reproducibility for experiments: a fresh vault, given the same inputs,
    # must not depend on process-specific randomness (e.g. hash seeding).
    first_vault = InMemoryVault()
    second_vault = InMemoryVault()

    first = first_vault.pseudonymize(PseudonymScope.DOCUMENT, "doc-1", "cpf", "123.456.789-09")
    second = second_vault.pseudonymize(PseudonymScope.DOCUMENT, "doc-1", "cpf", "123.456.789-09")

    assert first == second
