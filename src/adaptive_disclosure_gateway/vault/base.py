from __future__ import annotations

from abc import ABC, abstractmethod

from adaptive_disclosure_gateway.domain import PseudonymScope


class Vault(ABC):
    """Local-only store mapping original sensitive values to stable,
    scope-partitioned pseudonyms, plus authorized local reconstruction.

    A Vault is never given network access and nothing it returns from
    ``reconstruct`` is safe to place in an external payload -- that boundary
    is enforced by the caller (``ReversiblePseudonymizer``), not by this
    class, but every implementation must stay purely local so there is
    nothing here that *could* leak even if a caller misused it.
    """

    @abstractmethod
    def pseudonymize(self, scope: PseudonymScope, scope_key: str, category: str, value: str) -> str:
        """Return a stable pseudonym for ``value`` within ``(scope, scope_key)``.

        Calling this again with the same four arguments returns the exact
        same pseudonym (stability within a scope). The same ``value`` under
        a different ``scope`` or ``scope_key`` must not resolve to the same
        pseudonym (scopes do not share mappings). Two different ``value``s
        within the same ``(scope, scope_key, category)`` must never receive
        the same pseudonym -- even if they happen to collide under whatever
        pseudonym-generation scheme an implementation uses internally; see
        ``InMemoryVault`` for how collisions are disambiguated.
        """

    @abstractmethod
    def reconstruct(self, scope: PseudonymScope, scope_key: str, pseudonym: str) -> str | None:
        """Return the original value ``pseudonym`` stands for within
        ``(scope, scope_key)``, or ``None`` if this vault never issued that
        pseudonym for that partition (including a pseudonym issued under a
        different scope or scope_key).
        """
