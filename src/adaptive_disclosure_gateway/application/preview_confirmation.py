"""Stateless, server-authenticated proof that one ``/documents/execute`` is
the ``/documents/preview`` a reviewer actually approved (T20 / issue #28's
demo-integration slice; issue #41 gate A).

The defect this closes
----------------------

``/documents/preview`` and ``/documents/execute`` were two unrelated
requests. A client could preview under ``recommended``/B4 -- Policy-governed
with ``analysis_mode=contract_summary``, show the reviewer that result, and
then execute the same upload under ``strategy=b0`` (B0 -- Direct: the raw
document) with ``analysis_mode=financial_audit``. The server accepted it as
a fresh execution. So **the content executed need not be the content the
reviewer reviewed** -- which is the demo's central guarantee ("see exactly
what will be sent to the provider before authorising it"), and it let a
client run an untransformed document straight at a real provider.

Why a signed token rather than server-side state
------------------------------------------------

The obvious fix -- keep the preview server-side and let execute name it --
is the one thing the demo's no-persistence rule forbids: an advisor's
uploaded contract must not be retained between two requests, and this slice
introduces no database, cache, session table or filesystem persistence.

So the proof travels with the request instead. ``preview`` issues a token
over a fingerprint of the state it just showed; ``execute`` re-uploads the
same file, **re-computes that state from the new request**, and verifies the
token against the recomputed state. Nothing is read *out* of the token and
trusted -- the token carries no state at all, only the validity window and a
MAC. A divergence anywhere is a rejection, and the provider is never called.

Duplicating the upload on execute is the cost, and it is deliberate.

Why the binding must be server-keyed
------------------------------------

A client-supplied ``sha256(file)`` would prove nothing: a client that
changes the strategy can recompute one. Equally, a *public* digest of the
document, the task or the payload would be dictionary-reversible for
low-entropy content and would turn the token itself into a disclosure
channel -- CLAUDE.md's "a guessable representation counts as a leak", and
the same defect ``audit.py`` already closed for its own content hashes.

Every content-derived component here is therefore an HMAC-SHA256 keyed by
the deployment secret and domain-separated by the semantics version and the
field name, and the token as a whole is an HMAC over the canonical signed
document. Standard library only (``hmac``/``hashlib``); no JWT, no external
dependency.

What the token reveals
----------------------

Its three segments are the semantics version, a base64url ``{issued_at,
expires_at}`` claims object, and the MAC. No original, no pseudonym, no
payload, no task, no filename, no key material -- pinned by
``tests/test_application_preview_confirmation.py`` and again over HTTP in
``tests/test_api_documents_upload.py``.

Versioning
----------

``CONFIRMATION_SEMANTICS_VERSION`` is the first segment of every token and
is also inside the signed document. Changing which fields are bound, how
they are canonicalised, or how they are digested requires bumping it, so a
token issued under the old rule can never be reinterpreted under the new
one -- it simply stops verifying.

Known limitation: replay of an unchanged state
----------------------------------------------

A token stays valid for its whole window for *the state it was issued for*.
Executing the same approved state twice inside that window is accepted.
Preventing that needs a record of spent tokens, which is storage, which this
design deliberately does not have. The window is therefore short, and the
property actually guaranteed is the one the demo needs: an execute can only
ever run a state a reviewer approved, never a different one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

CONFIRMATION_SEMANTICS_VERSION = "document-preview-confirmation-v1"
"""Identifies which fingerprint rule produced a token. See *Versioning*."""

DEFAULT_CONFIRMATION_TTL_SECONDS = 900
"""15 minutes: long enough to read a disclosure review, short enough that an
approval is a review window rather than a standing grant."""

# 32 bytes of key material is the HMAC-SHA256 block-appropriate minimum this
# project already uses for its audit hash key (audit.py). A configured
# secret shorter than this is a misconfiguration, not a weaker-but-working
# deployment.
MIN_SECRET_BYTES = 32

# One message for every rejection. Distinguishing "expired" from "tampered"
# from "the strategy changed" would tell a client which half of the approval
# to adjust, and none of those distinctions is safe to expose at this
# boundary. The reviewer's remedy is identical in every case: preview again.
_REJECTION_MESSAGE = "document preview confirmation is invalid or no longer matches this request"

_SEPARATOR = "\x1f"


class PreviewConfirmationError(Exception):
    """Raised when a confirmation token is absent, malformed, unknown,
    expired, forged, or no longer matches the request being executed.

    Its message is a fixed constant -- never the token, the state, the
    document, the task, the payload or the secret. Safe to surface as an
    HTTP body (``api/app.py`` maps it to 400).
    """


class PreviewConfirmationConfigurationError(Exception):
    """Raised when confirmation signing itself is misconfigured -- no
    secret where one is required, a secret too short to key an HMAC, a
    non-positive validity window.

    A deployment error surfaced at construction time, deliberately not a
    ``PreviewConfirmationError``: the latter is a rejected request, this is
    a server that must not start serving structured uploads at all. Its
    message names the requirement, never the rejected value.
    """


def canonical_json(payload: Mapping[str, object]) -> str:
    """The one serialization used for anything that gets signed.

    Deterministic by construction: keys sorted (so the fingerprint cannot
    depend on the order the server happened to build its mapping in),
    compact separators (so it cannot depend on pretty-printing defaults),
    and ``ensure_ascii=False`` (so one character has one encoding). Never
    ``str(dict)`` or ``repr`` -- both are order-incidental and neither is a
    stable contract across Python versions.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True, repr=False)
class PreviewConfirmationState:
    """Everything an approval is an approval *of*.

    Three of these fields are sensitive -- ``normalized_document``, ``task``
    and ``external_payload`` -- and this is the one object that holds all
    three together, so ``repr`` is overridden below rather than inherited:
    a default dataclass repr would print the whole document into any
    traceback, log line or debugger frame that touched an instance.

    ``external_payload`` is bound for a reason worth stating explicitly. The
    other fields bind what the caller *asked for*; the payload binds what
    the server *decided*. Including it means a preview produced under one
    detector, one treatment implementation, one policy resolution or one
    transformation stops authorising an execute the moment any of those
    changes -- even though every caller-facing parameter still matches.
    """

    normalized_document: str
    task: str
    document_type: str
    analysis_mode: str
    domain: str
    policy_version: str
    purpose: str
    requester_role: str | None
    requested_pseudonym_scope: str
    governance_provider_class: str
    provider_class: str
    strategy: str
    treatment: str
    external_payload: str

    def __repr__(self) -> str:
        return "PreviewConfirmationState(<redacted>)"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


class PreviewConfirmationSigner:
    """Issues and verifies preview confirmations for one deployment.

    ``secret`` is deployment key material and never leaves this object: it
    is not stored on a state, not put in a token, not logged, not returned
    by ``__repr__`` and never interpolated into an exception message.

    ``clock`` is injectable so expiry is testable without sleeping, mirroring
    ``InMemoryVault``'s injectable ``token_factory`` and ``audit.py``'s
    injectable ``audit_key``.
    """

    def __init__(
        self,
        *,
        secret: bytes | str,
        ttl_seconds: int = DEFAULT_CONFIRMATION_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        key = secret.encode("utf-8") if isinstance(secret, str) else secret
        if len(key) < MIN_SECRET_BYTES:
            # Names the requirement only -- never the rejected material.
            raise PreviewConfirmationConfigurationError(
                "the preview confirmation secret is too short to key an HMAC; at least "
                f"{MIN_SECRET_BYTES} bytes of key material are required"
            )
        if ttl_seconds <= 0:
            raise PreviewConfirmationConfigurationError(
                "the preview confirmation validity window must be a positive number of seconds"
            )
        self._secret = key
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    @classmethod
    def with_ephemeral_secret(cls, **kwargs) -> PreviewConfirmationSigner:
        """A signer keyed by freshly generated per-process key material.

        This is **not** a way to disable confirmation: every token is still
        issued and verified exactly as it would be under a configured
        secret. What it gives up is durability -- tokens do not survive a
        restart, and two processes do not honour each other's -- which makes
        it right for development against ``FakeProvider`` and wrong for a
        deployment wired to an external provider. ``application/settings.py``
        draws exactly that line and fails closed on the wrong side of it.

        The same shape ``audit.py`` already uses for its per-process content
        hash key.
        """
        return cls(secret=secrets.token_bytes(MIN_SECRET_BYTES), **kwargs)

    def __repr__(self) -> str:
        return f"PreviewConfirmationSigner(ttl_seconds={self._ttl_seconds})"

    def issue(self, state: PreviewConfirmationState) -> str:
        """The token ``/documents/preview`` hands back alongside the review.

        A pure function of (secret, state, clock): the same state reviewed
        twice at the same instant yields the same token, so nothing depends
        on hidden per-call state.
        """
        issued_at = int(self._clock())
        claims = {"expires_at": issued_at + self._ttl_seconds, "issued_at": issued_at}
        claims_json = canonical_json(claims)
        mac = self._mac(self._signed_document(state, claims))
        return f"{CONFIRMATION_SEMANTICS_VERSION}.{_b64(claims_json.encode('utf-8'))}.{_b64(mac)}"

    def verify(self, token: str, state: PreviewConfirmationState) -> None:
        """Accept ``token`` only as an approval of exactly ``state``.

        ``state`` is always recomputed by the caller from the request being
        executed -- nothing is read out of the token and trusted except the
        validity window, which is itself inside the MAC. Returns ``None`` on
        success; every failure raises ``PreviewConfirmationError`` with the
        single fixed message.
        """
        claims, presented_mac = self._parse(token)
        expected = self._mac(self._signed_document(state, claims))
        if not hmac.compare_digest(expected, presented_mac):
            raise PreviewConfirmationError(_REJECTION_MESSAGE)
        # Checked only after the MAC: the window is signed data, so an
        # unauthenticated token must never get as far as having its
        # timestamps believed.
        if self._clock() > claims["expires_at"]:
            raise PreviewConfirmationError(_REJECTION_MESSAGE)

    # --- internals -----------------------------------------------------------

    def _parse(self, token: str) -> tuple[dict[str, int], bytes]:
        """Split a presented token into its signed claims and its MAC.

        Every decode here is wrapped and re-raised with ``from None``: the
        token is attacker-supplied text arriving on the same request as the
        document, and the stdlib parsers it passes through quote their input
        in their own messages -- ``json.JSONDecodeError`` embeds the document
        it failed to parse, ``binascii``/``UnicodeDecodeError`` the offending
        bytes. Chaining any of them would carry that text to whatever
        renders ``__cause__`` (CLAUDE.md's no-leak invariant).
        """
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != CONFIRMATION_SEMANTICS_VERSION:
            raise PreviewConfirmationError(_REJECTION_MESSAGE)
        try:
            decoded = json.loads(_unb64(parts[1]).decode("utf-8"))
            presented_mac = _unb64(parts[2])
        except (ValueError, TypeError):
            # Every decoder on this path raises one of these: binascii's
            # Error and json's JSONDecodeError are both ValueError
            # subclasses, as is UnicodeDecodeError.
            raise PreviewConfirmationError(_REJECTION_MESSAGE) from None
        if not isinstance(decoded, dict) or set(decoded) != {"issued_at", "expires_at"}:
            raise PreviewConfirmationError(_REJECTION_MESSAGE)
        if not all(isinstance(decoded[name], int) for name in ("issued_at", "expires_at")):
            raise PreviewConfirmationError(_REJECTION_MESSAGE)
        return decoded, presented_mac

    def _digest(self, field_name: str, content: str) -> str:
        """A keyed, domain-separated digest of one sensitive field.

        Keyed so it cannot be recomputed or dictionary-attacked from outside
        this trust boundary; domain-separated by version and field name so a
        digest computed for one field can never be replayed as another's.
        """
        material = _SEPARATOR.join((CONFIRMATION_SEMANTICS_VERSION, field_name, content))
        return hmac.new(self._secret, material.encode("utf-8"), hashlib.sha256).hexdigest()

    def _signed_document(self, state: PreviewConfirmationState, claims: Mapping[str, int]) -> str:
        return canonical_json(
            {
                "analysis_mode": state.analysis_mode,
                "document_digest": self._digest("normalized_document", state.normalized_document),
                "document_type": state.document_type,
                "domain": state.domain,
                "expires_at": claims["expires_at"],
                "external_payload_digest": self._digest("external_payload", state.external_payload),
                "governance_provider_class": state.governance_provider_class,
                "issued_at": claims["issued_at"],
                "policy_version": state.policy_version,
                "provider_class": state.provider_class,
                "purpose": state.purpose,
                "requested_pseudonym_scope": state.requested_pseudonym_scope,
                "requester_role": state.requester_role,
                "strategy": state.strategy,
                "task_digest": self._digest("task", state.task),
                "treatment": state.treatment,
                "version": CONFIRMATION_SEMANTICS_VERSION,
            }
        )

    def _mac(self, signed_document: str) -> bytes:
        return hmac.new(self._secret, signed_document.encode("utf-8"), hashlib.sha256).digest()
