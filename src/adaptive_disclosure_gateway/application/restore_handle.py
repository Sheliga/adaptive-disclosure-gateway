"""Stateless, sealed restore handles for deferred local re-identification
(T26 / issue #67).

The gap this closes
--------------------

``POST /documents/preview`` (and now ``/documents/export``) already return
the disclosed representation of a document -- the same ``external_payload``
a reviewer sees before anything is sent to a provider. What did not exist
was a way to take that representation *outside* the gateway (into another
tool, another model, a person's inbox) and, later, on request, turn the
pseudonyms it contains back into their originals -- without the gateway
retaining anything server-side between the two calls.

Design: seal, don't store (ADR-0002)
-------------------------------------

A restore handle is an AES-256-GCM envelope over exactly the
``(pseudonym -> original)`` entries that exist in one export, plus a
version and an expiry -- nothing else, and nothing kept on this process.
``RestoreHandleSealer.issue`` never writes anything to memory that outlives
the call (beyond the handle string it returns), and ``.open`` never needs
anything but the handle itself and this deployment's key material. This
preserves the T25 stateless-container / ephemeral-by-default posture: a
handle survives a restart or a different worker picking up the request,
because nothing about it depends on server-side state at all.

This is a deliberately different mechanism from
``application/preview_confirmation.py``'s HMAC token, even though both are
"stateless, server-keyed envelopes": a confirmation only ever needs to prove
*that a state was seen*, so a keyed digest is enough and the state itself is
recomputed by the verifier. A restore handle has to carry the actual
pseudonym -> original entries *forward in time*, to be decrypted by a later,
unrelated request -- so it needs authenticated **encryption**, not just
authentication.

Why HKDF-derived key material, not the raw configured secret
--------------------------------------------------------------

``ADG_RESTORE_HANDLE_SECRET`` is put through HKDF-SHA256 with a fixed
domain-separation info label (``_HKDF_INFO``) before it ever reaches AESGCM.
This keeps the derived key cryptographically independent of
``ADG_PREVIEW_CONFIRMATION_SECRET`` even if an operator (against the
documented guidance) reuses the same raw value for both: the two mechanisms
must never be able to influence, forge or downgrade each other because they
happen to share one HMAC/AEAD key.

Why no ephemeral-key mode
--------------------------

``PreviewConfirmationSigner.with_ephemeral_secret`` exists because a preview
confirmation only ever needs to outlive one browser round trip within the
same process. A restore handle is explicitly meant to outlive the issuing
process -- that is the entire feature -- so a per-process key would make
every handle silently unusable the moment the process restarts or a
different worker serves the restore call, with no error at issue time to
say so. There is deliberately no ``with_ephemeral_secret`` here. Unset
``ADG_RESTORE_HANDLE_SECRET`` therefore does not degrade to a weaker mode;
`.issue`/`.open` refuse outright (``RestoreUnavailableError``, mapped to
HTTP 503) while every other route keeps working -- see
``application/settings.py``.

Why padding
-----------

The plaintext JSON is padded to the next multiple of
``_PADDING_BUCKET_BYTES`` before encryption, using an explicit ``"pad"``
field of ASCII zero characters (which need no JSON escaping, so the byte
length added is exactly the length requested). Without this, the ciphertext
length would reveal how much was pseudonymized -- a coarse but real
side channel, and CLAUDE.md's "a guessable representation counts as a leak"
applies to size as much as to content for a small, low-entropy export.

Why a regex is needed for ``restore``'s unresolved count, but not for
replacement
----------------------------------------------------------------------

Replacing known tokens reuses
``transformations.decision_application.replace_ordered`` verbatim -- the
same literal, longest-first substring algorithm local reconstruction
already uses, so there is exactly one token-replacement implementation in
the codebase. But ``restore`` also has to report how many pseudonym-shaped
tokens in the submitted text did *not* resolve (e.g. because they belong to
a different document's scope) -- and unlike reconstruction, this call has no
``DisclosureResult``/vault to consult for "what counts as a pseudonym here".
``_PSEUDONYM_TOKEN_PATTERN`` recognizes the fixed, already-public shape
``vault/in_memory.py`` emits (``PSEUDO-<category>-<32 hex chars>`` with an
optional ``-<suffix>``) purely to *count* candidates -- it never drives
substitution, which is still done only for tokens present in the handle.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from adaptive_disclosure_gateway.application.preview_confirmation import canonical_json
from adaptive_disclosure_gateway.observability import get_tracer
from adaptive_disclosure_gateway.transformations.decision_application import replace_ordered

HANDLE_VERSION = 1
"""Bumping this changes the sealed schema; ``open`` refuses any other
version rather than guessing how to interpret it."""

HANDLE_PREFIX = "rh1"
"""The wire-visible version tag prefixed to every handle."""

DEFAULT_TTL_SECONDS = 86400
"""24 hours."""

MAX_TTL_SECONDS = 604800
"""7 days -- the outer bound ``ADG_RESTORE_HANDLE_TTL_SECONDS`` may configure."""

# Matches MIN_SECRET_BYTES in preview_confirmation.py: 32 bytes is the
# HMAC/HKDF block-appropriate minimum this project already requires for its
# other server-keyed secret.
MIN_SECRET_BYTES = 32

_HKDF_INFO = b"adg-restore-handle-v1"
_AAD = b"adg-restore-handle-v1"
_NONCE_BYTES = 12
_PADDING_BUCKET_BYTES = 256

# The fixed shape InMemoryVault emits (vault/in_memory.py: `_make_pseudonym`)
# -- 32 hex characters (`secrets.token_hex(16)`) with an optional
# `-<suffix>` collision-disambiguation counter. Used only to COUNT
# pseudonym-shaped tokens present in submitted text for `unresolved_count`;
# never used to drive a substitution (see the module docstring).
_PSEUDONYM_TOKEN_PATTERN = re.compile(r"PSEUDO-[A-Za-z0-9_]+-[0-9a-f]{32}(?:-\d+)?")

_INVALID_MESSAGE = (
    "restore handle is invalid, malformed, or does not match this deployment's key material"
)
_EXPIRED_MESSAGE = "restore handle has expired"


class RestoreHandleConfigurationError(Exception):
    """Raised at ``RestoreHandleSealer`` construction time for a
    deployment-level misconfiguration: a configured secret shorter than
    ``MIN_SECRET_BYTES``, or a TTL outside ``[1, MAX_TTL_SECONDS]``.

    Distinct from ``RestoreUnavailableError``: this is a value that WAS
    supplied and is wrong, so failing the whole process at startup is
    correct; an unset secret is a deliberate, supported "feature disabled"
    state instead (see ``RestoreUnavailableError``). Names the requirement
    only, never the rejected value.
    """


class RestoreUnavailableError(Exception):
    """Raised by ``issue``/``open`` (never at construction) when no restore
    handle secret is configured.

    Deliberately NOT raised at construction: a deployment with
    ``ADG_RESTORE_HANDLE_SECRET`` unset must still start and serve every
    other route (including ``/health`` and document preview/execute)
    normally -- only export and restore are unavailable. Maps to HTTP 503;
    the CLI reports a non-zero exit naming the environment variable, never a
    value.
    """


class RestoreHandleError(Exception):
    """Base class for a handle that was opened and rejected. Every subclass
    message is a fixed constant -- never the handle, the decrypted entries,
    or any text passed in alongside it.
    """


class RestoreHandleExpiredError(RestoreHandleError):
    """The handle decrypted and authenticated correctly, but its ``exp``
    claim is in the past."""


class RestoreHandleInvalidError(RestoreHandleError):
    """Every other rejection: wrong version/prefix, malformed base64,
    truncated ciphertext, a failed AEAD tag (tampering, or a wrong/rotated
    key), or a payload that does not decode to the expected schema.

    Deliberately one error for all of these: distinguishing "tampered" from
    "wrong key" from "truncated" would not help a legitimate caller (their
    remedy is identical -- export again) and would help an attacker
    fingerprint which byte they broke.
    """


@dataclass(frozen=True)
class IssuedRestoreHandle:
    """What ``RestoreHandleSealer.issue`` hands back to the caller: the
    opaque handle string and the expiry it carries (surfaced so a response
    can tell a caller when a handle stops working, without decoding it).
    """

    handle: str
    expires_at: int


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _derive_key(secret: bytes) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO)
    return hkdf.derive(secret)


def _pad_to_bucket(payload: dict[str, object]) -> bytes:
    """Serialize ``payload`` plus a ``"pad"`` field of ASCII ``"0"``
    characters sized so the encoded result's byte length is the smallest
    multiple of ``_PADDING_BUCKET_BYTES`` at least as large as the
    unpadded encoding. ASCII digits need no JSON escaping, so the bytes
    added equal exactly the characters requested.
    """
    unpadded = dict(payload)
    unpadded["pad"] = ""
    base_len = len(canonical_json(unpadded).encode("utf-8"))
    remainder = base_len % _PADDING_BUCKET_BYTES
    pad_len = 0 if remainder == 0 else _PADDING_BUCKET_BYTES - remainder
    unpadded["pad"] = "0" * pad_len
    return canonical_json(unpadded).encode("utf-8")


class RestoreHandleSealer:
    """Issues and opens restore handles for one deployment.

    ``secret`` is deployment key material (or ``None``, meaning the feature
    is unavailable -- see ``RestoreUnavailableError``) and never leaves this
    object: not stored on any returned value, not logged, not returned by
    ``__repr__``, never interpolated into an exception message. ``clock`` is
    injectable so expiry is testable without sleeping, mirroring
    ``PreviewConfirmationSigner``.
    """

    def __init__(
        self,
        *,
        secret: bytes | str | None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not (0 < ttl_seconds <= MAX_TTL_SECONDS):
            raise RestoreHandleConfigurationError(
                "the restore handle validity window must be a positive integer number of "
                f"seconds, at most {MAX_TTL_SECONDS} (7 days)"
            )
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        if secret is None:
            self._key: bytes | None = None
        else:
            raw = secret.encode("utf-8") if isinstance(secret, str) else secret
            if len(raw) < MIN_SECRET_BYTES:
                raise RestoreHandleConfigurationError(
                    "the restore handle secret is too short to derive key material from; at "
                    f"least {MIN_SECRET_BYTES} bytes of key material are required"
                )
            self._key = _derive_key(raw)

    def __repr__(self) -> str:
        return (
            f"RestoreHandleSealer(ttl_seconds={self._ttl_seconds}, "
            f"configured={self._key is not None})"
        )

    @property
    def configured(self) -> bool:
        return self._key is not None

    def _require_configured(self) -> bytes:
        if self._key is None:
            raise RestoreUnavailableError(
                "ADG_RESTORE_HANDLE_SECRET is not configured; export and restore are "
                "unavailable until a deployment secret is set (see .env.example)"
            )
        return self._key

    def issue(self, entries: Mapping[str, str]) -> IssuedRestoreHandle:
        """Seal ``entries`` (pseudonym -> original) into a fresh handle.

        A fresh random nonce is drawn on every call, so two exports of
        identical content never produce the same handle -- it is not a
        reproducible digest of anything.
        """
        key = self._require_configured()
        tracer = get_tracer()
        with tracer.start_as_current_span("restore_handle.issue") as span:
            issued_at = int(self._clock())
            expires_at = issued_at + self._ttl_seconds
            plaintext = _pad_to_bucket(
                {
                    "v": HANDLE_VERSION,
                    "iat": issued_at,
                    "exp": expires_at,
                    "entries": dict(entries),
                }
            )
            nonce = secrets.token_bytes(_NONCE_BYTES)
            ciphertext = AESGCM(key).encrypt(nonce, plaintext, _AAD)
            handle = f"{HANDLE_PREFIX}.{_b64(nonce + ciphertext)}"

            # Metadata only -- counts and timing, never an entry's pseudonym
            # or original.
            span.set_attribute("restore_handle.entry_count", len(entries))
            span.set_attribute("restore_handle.ttl_seconds", self._ttl_seconds)
            return IssuedRestoreHandle(handle=handle, expires_at=expires_at)

    def open(self, handle: str) -> dict[str, str]:
        """Decrypt and authenticate ``handle``, returning its
        ``(pseudonym -> original)`` entries.

        Every failure mode below -- malformed structure, bad base64, a
        truncated envelope, a failed AEAD tag (tampering or a wrong/rotated
        key), an unparseable or schema-invalid plaintext -- raises
        ``RestoreHandleInvalidError`` with the one fixed message; a
        cryptographically valid but time-expired handle raises
        ``RestoreHandleExpiredError``. Nothing decrypted is ever attached to
        either exception: every parser here that could otherwise echo
        attacker- or content-controlled bytes into its own message
        (``json.loads``, ``bytes.decode``, base64's own decoder) is broken
        from its exception with ``raise ... from None``.
        """
        key = self._require_configured()
        tracer = get_tracer()
        with tracer.start_as_current_span("restore_handle.restore") as span:
            span.set_attribute("restore_handle.outcome", "invalid")  # overwritten on success

            prefix, _, blob = handle.partition(".")
            if not blob or prefix != HANDLE_PREFIX:
                raise RestoreHandleInvalidError(_INVALID_MESSAGE)
            try:
                raw = _unb64(blob)
            except (ValueError, binascii.Error):
                raise RestoreHandleInvalidError(_INVALID_MESSAGE) from None
            if len(raw) <= _NONCE_BYTES:
                raise RestoreHandleInvalidError(_INVALID_MESSAGE)
            nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
            try:
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, _AAD)
            except InvalidTag:
                raise RestoreHandleInvalidError(_INVALID_MESSAGE) from None
            try:
                payload = json.loads(plaintext.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                # ``plaintext`` is the decrypted content -- it may carry
                # original values. json's own JSONDecodeError and a
                # UnicodeDecodeError both quote their offending input in
                # their message; the chain is broken so neither reaches a
                # caller (CLAUDE.md's no-leak invariant).
                raise RestoreHandleInvalidError(_INVALID_MESSAGE) from None

            if (
                not isinstance(payload, dict)
                or payload.get("v") != HANDLE_VERSION
                or not isinstance(payload.get("exp"), int)
                or not isinstance(payload.get("entries"), dict)
            ):
                raise RestoreHandleInvalidError(_INVALID_MESSAGE)

            entries = payload["entries"]
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in entries.items()):
                raise RestoreHandleInvalidError(_INVALID_MESSAGE)

            if self._clock() > payload["exp"]:
                span.set_attribute("restore_handle.outcome", "expired")
                raise RestoreHandleExpiredError(_EXPIRED_MESSAGE)

            span.set_attribute("restore_handle.outcome", "ok")
            span.set_attribute("restore_handle.entry_count", len(entries))
            return entries


def restore_pseudonyms(text: str, mapping: Mapping[str, str]) -> tuple[str, int, int]:
    """Replace only the pseudonyms in ``mapping`` that actually occur in
    ``text``, leaving every other pseudonym-shaped token untouched.

    Returns ``(restored_text, restored_count, unresolved_count)``.
    ``restored_count`` is the number of distinct ``mapping`` entries found
    (and replaced) in ``text``; ``unresolved_count`` is the number of
    distinct pseudonym-shaped tokens found in ``text`` that are NOT in
    ``mapping`` -- e.g. because they belong to a different document's
    scope/handle (no cross-scope oracle: this function never consults any
    scope other than the one ``mapping`` already represents).

    Replacement itself reuses
    ``transformations.decision_application.replace_ordered`` -- the same
    literal, longest-first algorithm local reconstruction uses -- rather
    than a second implementation; see the module docstring for why counting
    unresolved tokens still needs its own recognition pattern.
    """
    present_tokens = set(_PSEUDONYM_TOKEN_PATTERN.findall(text))
    resolvable = sorted(
        (token for token in present_tokens if token in mapping), key=len, reverse=True
    )
    pairs = [(token, mapping[token]) for token in resolvable]
    restored_text = replace_ordered(text, pairs)
    restored_count = len(resolvable)
    unresolved_count = len(present_tokens) - restored_count
    return restored_text, restored_count, unresolved_count
