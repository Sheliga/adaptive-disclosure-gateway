from __future__ import annotations

import hashlib
from collections.abc import Callable

from adaptive_disclosure_gateway.domain import PseudonymScope

from .base import Vault

_DIGEST_LENGTH = 12


def _default_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


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
    """

    def __init__(self, digest: Callable[[str], str] = _default_digest) -> None:
        self._digest = digest
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
        candidate = self._make_pseudonym(partition, category, value, suffix)
        while candidate in reverse:
            # Collision: some other original value in this partition already
            # claimed this exact pseudonym string. Disambiguate by appending
            # an incrementing counter directly to the emitted string (not
            # just folding it into the digest input) so this terminates even
            # against a degenerate digest function that ignores its input
            # entirely -- see tests/test_vault.py's forced-collision case.
            suffix += 1
            candidate = self._make_pseudonym(partition, category, value, suffix)

        forward[entry_key] = candidate
        reverse[candidate] = value
        return candidate

    def _make_pseudonym(
        self, partition: tuple[str, str], category: str, value: str, suffix: int
    ) -> str:
        # The partition (scope + scope_key) is folded into the digest input
        # so the same value pseudonymized under two different partitions
        # never produces the same pseudonym string -- an observer comparing
        # two payloads across scopes/scope_keys cannot tell they refer to
        # the same underlying value just by string-matching pseudonyms.
        scope_value, scope_key = partition
        digest = self._digest(f"{scope_value}:{scope_key}:{category}:{value}")
        if suffix == 0:
            return f"PSEUDO-{category}-{digest}"
        return f"PSEUDO-{category}-{digest}-{suffix}"

    def reconstruct(self, scope: PseudonymScope, scope_key: str, pseudonym: str) -> str | None:
        partition = (scope.value, scope_key)
        return self._reverse.get(partition, {}).get(pseudonym)
