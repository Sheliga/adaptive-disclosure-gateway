from __future__ import annotations

import secrets
from collections.abc import Callable

from adaptive_disclosure_gateway.domain import PseudonymScope

from .base import Vault

# 128 bits of CSPRNG entropy per token (issue #24): enough that brute-forcing
# or dictionary-guessing a token offline is infeasible, and that an
# accidental collision between two independently generated tokens is
# negligible. This replaced a truncated, unkeyed SHA-256 digest of
# (scope, scope_key, category, value) -- for a low-entropy value such as an
# 11-digit CPF, or a name under a guessable ORGANIZATION-scope key, that
# digest could be inverted by an external observer through offline brute
# force or a dictionary attack. A random token has nothing to invert: it is
# not derived from the original value, or from any public/predictable
# context, at all.
_TOKEN_NBYTES = 16


def _default_token_factory() -> str:
    """Production token generator: a fresh CSPRNG token on every call, never
    derived from the value being pseudonymized or from any scope/category
    context. Independent ``InMemoryVault`` instances are therefore not
    expected to agree on a pseudonym for the same original -- see
    ``tests/test_vault.py``'s coverage of that non-reproducibility, which is
    the deliberate opposite of the previous digest-based design.
    """
    return secrets.token_hex(_TOKEN_NBYTES)


class InMemoryVault(Vault):
    """Process-local, in-memory pseudonym vault.

    Not persisted across process restarts and not shared across processes --
    a SQLite-backed implementation for durable/shared storage is explicitly
    out of scope for this PR (see docs/implementation-status.md).

    Partitioning: mappings are stored per ``(scope, scope_key)``, so the same
    original value pseudonymized under two different scopes (or two
    different scope_keys within the same scope) gets independent,
    unrelated pseudonyms -- reconstructing a pseudonym issued in one
    partition never succeeds against another.

    Pseudonym generation (issue #24): the emitted token is an opaque random
    value stored in the vault's forward/reverse maps, never a function of
    the original value or of public/predictable context. Stability within a
    partition comes entirely from the forward-map lookup below (same
    original -> same stored token), not from the token generator being
    deterministic -- so the production default (``_default_token_factory``,
    a CSPRNG) can safely be unkeyed and still not reproducible across
    independent vault instances. Tests inject a deterministic
    ``token_factory`` where cross-instance reproducibility is required for
    experiments; production code must never do this.
    """

    def __init__(self, token_factory: Callable[[], str] = _default_token_factory) -> None:
        self._token_factory = token_factory
        # (scope.value, scope_key) -> {(category, value): pseudonym}
        self._forward: dict[tuple[str, str], dict[tuple[str, str], str]] = {}
        # (scope.value, scope_key) -> {pseudonym: value}
        self._reverse: dict[tuple[str, str], dict[str, str]] = {}

    def pseudonymize(self, scope: PseudonymScope, scope_key: str, category: str, value: str) -> str:
        partition = (scope.value, scope_key)
        forward = self._forward.setdefault(partition, {})
        reverse = self._reverse.setdefault(partition, {})
        entry_key = (category, value)

        existing = forward.get(entry_key)
        if existing is not None:
            return existing

        suffix = 0
        candidate = self._make_pseudonym(category, suffix)
        while candidate in reverse:
            # Collision: some other original value in this partition already
            # claimed this exact pseudonym string. Disambiguate by appending
            # an incrementing counter directly to the emitted string (not
            # just hoping the next generated token differs) so this
            # terminates even against a degenerate token factory that
            # returns the same value on every call -- see
            # tests/test_vault.py's forced-collision case.
            suffix += 1
            candidate = self._make_pseudonym(category, suffix)

        forward[entry_key] = candidate
        reverse[candidate] = value
        return candidate

    def _make_pseudonym(self, category: str, suffix: int) -> str:
        # The category is kept in the emitted string purely for audit
        # readability (see PSEUDO-{category}- prefix); with an opaque random
        # token there is nothing left for an attacker to guess from it. The
        # token itself carries no information about the partition, the
        # category or the original value -- partition isolation instead
        # comes from each (scope, scope_key) having its own forward/reverse
        # maps, so the same value pseudonymized under two partitions gets
        # two independently generated, unrelated tokens.
        token = self._token_factory()
        if suffix == 0:
            return f"PSEUDO-{category}-{token}"
        return f"PSEUDO-{category}-{token}-{suffix}"

    def reconstruct(self, scope: PseudonymScope, scope_key: str, pseudonym: str) -> str | None:
        partition = (scope.value, scope_key)
        return self._reverse.get(partition, {}).get(pseudonym)
