"""Sealed, local-only vault-explorer references (T29 / issue #72).

What this closes
-----------------
T27/T28 (issues #69-#70) let a demo operator SEE that reversible
pseudonymization happened (the inspection diff, export/restore). Neither
lets an operator confirm, for one specific decision, exactly which vault
entries back it and that reconstruction genuinely resolves them -- the
pedagogical point Issue #72 asks for ("mostrar metadados necessários para
explicar a relação entre transformação e reconstrução"). This module is the
ONLY application/api-layer code allowed to call ``Vault.reconstruct`` for
that purpose (pinned by
``tests/test_vault_explorer_import_isolation.py``) -- every other route
still only ever reconstructs through the existing
``transformations.decision_application.reconstruct`` path used by
``execute``.

Design: seal, don't store -- and don't reuse anyone else's key
----------------------------------------------------------------
Like ``application/restore_handle.py``, a reference is an AES-256-GCM
envelope with nothing kept server-side beyond the token string itself. It
deliberately differs from ``RestoreHandleSealer`` in the one place that
matters for a demo/debug-only feature: the AEAD key is a **fresh random
32-byte value generated once per process** (``secrets.token_bytes(32)``),
never derived from any configured secret and never shared with the preview-
confirmation signer or the restore-handle sealer. A vault-explorer
reference is not meant to outlive the process that issued it -- unlike a
restore handle, which specifically must survive a restart or a different
worker -- so there is no durability requirement pulling toward a
configured/derived key, and every reason to avoid one: reusing
``ADG_RESTORE_HANDLE_SECRET`` or ``ADG_PREVIEW_CONFIRMATION_SECRET`` here
would let a bug in this debug-only surface influence or be influenced by
either production mechanism. This also means a reference from one process
is unconditionally rejected by another (see ``explore``'s docstring) --
that is a feature, not a limitation, for a local demo tool.

What the sealed plaintext carries
----------------------------------
``{"v": 1, "exp": <epoch seconds>, "scope": <PseudonymScope value> | null,
"scope_key": <str> | null, "entries": [{"pseudonym": ..., "category": ...},
...]}``. Never the original values -- those are looked up fresh, from the
live vault, only inside ``explore``. ``scope``/``scope_key`` are null
together exactly when there is nothing reversible to show (B0 -- Direct,
B1 -- Static Sanitization, or a B2-B4 decision that pseudonymized nothing);
``entries`` is empty in that case too. The plaintext is padded to a fixed
256-byte bucket (mirrors ``restore_handle._pad_to_bucket``) so ciphertext
length does not reveal how many entries a decision produced.

Why one error, one fixed message
-----------------------------------
``VaultExplorerReferenceError`` covers every rejection -- bad prefix,
malformed base64, a truncated envelope, a failed AEAD tag (tampering, a
wrong/rotated per-process key, or a token from a different process
entirely), a schema-invalid plaintext, and an expired ``exp`` claim -- all
with the identical message. Distinguishing them would not help a
legitimate caller (the remedy is always "preview again") and would help an
attacker fingerprint which byte they broke; see
``restore_handle.RestoreHandleInvalidError`` for the same reasoning applied
to that mechanism. Every parser that could otherwise echo attacker- or
plaintext-controlled bytes into its own exception message (``json.loads``,
``bytes.decode``, the base64 decoder) is broken from its exception with
``raise ... from None``.

Fail-closed issuance
----------------------
``issue_reference`` returns ``None`` -- never raises -- whenever there is
nothing safe to show: a blocked decision, a resolved scope of
``PseudonymScope.ORGANIZATION`` (an explorer scoped to the whole
organization would defeat the purpose of a per-decision demo lens), a
missing scope-key identifier, or an entry whose freshly-verified
``vault.reconstruct`` does not equal the transformation's own recorded
original (should never happen against the vault that just produced it, but
verified rather than assumed). ``DisclosureApplicationService`` treats
``None`` as "no token for this preview", exactly like a caller who never
asked for one.

No-leak invariant
-------------------
The only OTel spans here (``vault_explorer.issue``, ``vault_explorer.explore``)
carry counts only (``entry_count``, ``present_count``) -- never a pseudonym,
an original, a scope key or the token itself. Nothing here writes to disk,
a database, or any module-level mutable collection (pinned by
``tests/test_vault_explorer_import_isolation.py``); the only state is the
per-instance AEAD key and injectable clock on ``VaultExplorerSealer``.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from adaptive_disclosure_gateway.application.preview_confirmation import canonical_json
from adaptive_disclosure_gateway.domain import DisclosureAction, GovernanceContext, PseudonymScope
from adaptive_disclosure_gateway.observability import get_tracer
from adaptive_disclosure_gateway.pipeline import DisclosureDecision
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations.decision_application import (
    scope_key as _resolve_scope_key,
)
from adaptive_disclosure_gateway.vault import Vault

VAULT_EXPLORER_REFERENCE_TTL_SECONDS = 900
"""15 minutes -- long enough to walk through a demo, short enough that a
reference left open in a browser tab does not stay usable indefinitely."""

_PREFIX = "vx1"
_AAD = b"adg-vault-explorer-ref-v1"
_NONCE_BYTES = 12
_PADDING_BUCKET_BYTES = 256
_KEY_BYTES = 32

_INVALID_MESSAGE = (
    "vault explorer reference is invalid, malformed, expired, or was not issued by this process"
)


class VaultExplorerReferenceError(Exception):
    """Raised by :meth:`VaultExplorerSealer.explore` for any rejected
    token. One fixed message for every rejection reason -- see the module
    docstring for why.
    """


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _pad_to_bucket(payload: dict[str, object]) -> bytes:
    """Serialize ``payload`` plus a ``"pad"`` field of ASCII ``"0"``
    characters sized so the encoded result's byte length is the smallest
    multiple of ``_PADDING_BUCKET_BYTES`` at least as large as the unpadded
    encoding -- verbatim mirror of ``restore_handle._pad_to_bucket``
    (duplicated rather than imported: that function is private to
    ``restore_handle.py``, and this module must not reach into another
    sealer's internals for a few lines of shared math).
    """
    unpadded = dict(payload)
    unpadded["pad"] = ""
    base_len = len(canonical_json(unpadded).encode("utf-8"))
    remainder = base_len % _PADDING_BUCKET_BYTES
    pad_len = 0 if remainder == 0 else _PADDING_BUCKET_BYTES - remainder
    unpadded["pad"] = "0" * pad_len
    return canonical_json(unpadded).encode("utf-8")


@dataclass(frozen=True)
class VaultExplorerEntry:
    """One reversible entry as shown to the local operator: the category,
    the pseudonym that appeared in the disclosed payload, and the original
    the vault currently resolves it to (``None``/``present=False`` if the
    vault no longer -- or never did -- resolve it, which cannot happen for
    a same-process reference against an in-memory vault but is still
    represented rather than assumed).
    """

    category: str
    pseudonym: str
    original: str | None
    present: bool


@dataclass(frozen=True)
class VaultExplorerView:
    """What :meth:`VaultExplorerSealer.explore` returns: the resolved scope
    (``None`` when the decision had nothing reversible) and its entries.
    """

    scope: str | None
    entries: tuple[VaultExplorerEntry, ...]


class VaultExplorerSealer:
    """Issues and opens vault-explorer references for one process lifetime.

    ``clock`` is injectable so expiry is testable without sleeping,
    mirroring ``RestoreHandleSealer``/``PreviewConfirmationSigner``. Unlike
    both of those, there is no configured-secret constructor path at all:
    the key is always a fresh ``secrets.token_bytes(_KEY_BYTES)`` drawn at
    construction -- see the module docstring for why.
    """

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._key = secrets.token_bytes(_KEY_BYTES)
        self._clock = clock

    def issue_reference(
        self,
        decision: DisclosureDecision,
        context: GovernanceContext,
        policy_repository: PolicyRepository,
        vault: Vault,
    ) -> str | None:
        """Seal a reference to every distinct PSEUDONYMIZE transformation in
        ``decision``, or ``None`` if nothing may be issued -- see the module
        docstring's "Fail-closed issuance" section for every ``None`` case.
        """
        if decision.result.status != "allowed":
            return None

        seen: set[tuple[str, str]] = set()
        pseudonymized: list[tuple[str, str, str]] = []
        for transformation in decision.result.transformations:
            if transformation.action is not DisclosureAction.PSEUDONYMIZE:
                continue
            if transformation.transformed is None:
                continue
            dedup_key = (transformation.category, transformation.transformed)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            pseudonymized.append(
                (transformation.category, transformation.transformed, transformation.original)
            )

        if not pseudonymized:
            return self._seal(scope=None, partition_key=None, entries=[])

        scope = policy_repository.resolve_pseudonym_scope(context)
        if scope is PseudonymScope.ORGANIZATION:
            return None
        partition_key = _resolve_scope_key(scope, context)
        if partition_key is None:
            return None

        for category, pseudonym, original in pseudonymized:
            if vault.reconstruct(scope, partition_key, pseudonym) != original:
                return None

        entries = [
            {"pseudonym": pseudonym, "category": category}
            for category, pseudonym, _original in pseudonymized
        ]
        return self._seal(scope=scope.value, partition_key=partition_key, entries=entries)

    def _seal(
        self, *, scope: str | None, partition_key: str | None, entries: list[dict[str, str]]
    ) -> str:
        tracer = get_tracer()
        with tracer.start_as_current_span("vault_explorer.issue") as span:
            issued_at = int(self._clock())
            expires_at = issued_at + VAULT_EXPLORER_REFERENCE_TTL_SECONDS
            plaintext = _pad_to_bucket(
                {
                    "v": 1,
                    "exp": expires_at,
                    "scope": scope,
                    "scope_key": partition_key,
                    "entries": entries,
                }
            )
            nonce = secrets.token_bytes(_NONCE_BYTES)
            ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, _AAD)
            # Metadata only -- a count, never an entry's pseudonym/category.
            span.set_attribute("vault_explorer.entry_count", len(entries))
            return f"{_PREFIX}.{_b64(nonce + ciphertext)}"

    def explore(self, token: str, vault: Vault) -> VaultExplorerView:
        """Open ``token`` and resolve each of its sealed entries against
        ``vault`` -- a point lookup per entry, never an enumeration.

        A token issued by a different ``VaultExplorerSealer`` instance
        (including one from a prior process -- see the module docstring)
        always fails the AEAD tag check here and raises
        ``VaultExplorerReferenceError``: this sealer's key is per-process
        and never persisted or shared.
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("vault_explorer.explore") as span:
            payload = self._open(token)
            scope_value = payload["scope"]
            partition_key = payload["scope_key"]
            raw_entries = payload["entries"]

            entries: list[VaultExplorerEntry] = []
            present_count = 0
            if scope_value is not None and partition_key is not None:
                scope = PseudonymScope(scope_value)
                for raw_entry in raw_entries:
                    pseudonym = raw_entry["pseudonym"]
                    category = raw_entry["category"]
                    original = vault.reconstruct(scope, partition_key, pseudonym)
                    present = original is not None
                    if present:
                        present_count += 1
                    entries.append(
                        VaultExplorerEntry(
                            category=category,
                            pseudonym=pseudonym,
                            original=original,
                            present=present,
                        )
                    )

            # Metadata only -- counts, never a pseudonym, an original or the
            # scope key.
            span.set_attribute("vault_explorer.entry_count", len(entries))
            span.set_attribute("vault_explorer.present_count", present_count)
            return VaultExplorerView(scope=scope_value, entries=tuple(entries))

    def _open(self, token: str) -> dict[str, object]:
        prefix, _, blob = token.partition(".")
        if not blob or prefix != _PREFIX:
            raise VaultExplorerReferenceError(_INVALID_MESSAGE)
        try:
            raw = _unb64(blob)
        except (ValueError, binascii.Error):
            raise VaultExplorerReferenceError(_INVALID_MESSAGE) from None
        if len(raw) <= _NONCE_BYTES:
            raise VaultExplorerReferenceError(_INVALID_MESSAGE)
        nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        try:
            plaintext = AESGCM(self._key).decrypt(nonce, ciphertext, _AAD)
        except InvalidTag:
            raise VaultExplorerReferenceError(_INVALID_MESSAGE) from None
        try:
            payload = json.loads(plaintext.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            # ``plaintext`` may carry sealed entries -- json's own
            # JSONDecodeError and UnicodeDecodeError both quote their
            # offending input in their own message, so the chain is broken
            # rather than trusting that this specific plaintext never would
            # (CLAUDE.md's no-leak invariant).
            raise VaultExplorerReferenceError(_INVALID_MESSAGE) from None

        if not _is_valid_schema(payload):
            raise VaultExplorerReferenceError(_INVALID_MESSAGE)
        if self._clock() > payload["exp"]:
            raise VaultExplorerReferenceError(_INVALID_MESSAGE)
        return payload


def _is_valid_schema(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("v") != 1:
        return False
    if not isinstance(payload.get("exp"), int) or isinstance(payload.get("exp"), bool):
        return False
    scope = payload.get("scope")
    partition_key = payload.get("scope_key")
    if scope is not None and not isinstance(scope, str):
        return False
    if partition_key is not None and not isinstance(partition_key, str):
        return False
    if (scope is None) != (partition_key is None):
        return False
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"pseudonym", "category"}:
            return False
        if not isinstance(entry["pseudonym"], str) or not isinstance(entry["category"], str):
            return False
    return True
