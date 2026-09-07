"""Structural audit trail (issue #26 / T19).

The stages this module records mirror README.md's audit model exactly:

    raw input
    -> detected spans
    -> policy decisions
    -> transformed payload
    -> payload delivered to provider
    -> provider response
    -> locally reconstructed response

By default an ``AuditRecord`` carries **metadata only**: categories, counts,
decisions, actions, treatment identity, and content *hashes* -- never a raw
value, the payload, a provider response, or vault content. This is the
single most important property of this module: an audit trail that quietly
becomes a second home for sensitive data would defeat the whole
disclosure-control architecture this codebase exists to validate. The
metadata-only default must stay safe to serialize and log **in full** --
see ``tests/test_audit.py::test_audit_record_default_never_contains_raw_values_even_serialized_whole``,
which dumps a complete ``AuditRecord`` to JSON and asserts none of the raw
fixture values appear anywhere in it.

Full raw values may be captured **only** when a caller explicitly passes
``capture_raw_values_for_controlled_experiment=True`` to
``build_audit_record``. That name is deliberately long, explicit and
unambiguous -- never ``debug``, ``verbose``, ``include_raw`` or a value read
from an environment variable or config file -- specifically so it cannot be
enabled by accident: there is no default, no implicit code path, and no
alias that reaches it. Every call site in this codebase that does not pass
it explicitly gets the safe, metadata-only behavior.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any

from pydantic import BaseModel

from adaptive_disclosure_gateway.domain import (
    DisclosureRequest,
    DisclosureResult,
    PolicyDecision,
    SensitiveSpan,
    Treatment,
)
from adaptive_disclosure_gateway.providers import ProviderResponse

# Keyed content hashing (closes the same defect class as issue #24's
# pseudonym digest, applied here to the audit trail): a plain
# ``hashlib.sha256(value).hexdigest()`` is a public, reproducible digest.
# Anyone holding a default "metadata-only" audit record -- which is meant to
# be safe to log or persist in full -- could dictionary-attack
# ``payload_hash``/``response_hash``/``reconstructed_hash`` for low-entropy
# content (an 11-digit CPF, a name) by recomputing SHA-256 over candidate
# values entirely offline, no access to this codebase required. HMAC-SHA256
# with local key material closes that: without the key, the digest cannot be
# reproduced or dictionary-attacked from outside the local trust boundary.
#
# The key itself must never be derived from the content it hashes (exactly
# the reasoning already applied to vault/in_memory.py's pseudonym tokens) and
# must never leave this boundary -- it is used only as an HMAC key, never
# stored on ``AuditRecord``, logged, or interpolated into an exception
# message. It is generated once per process (below), not once per
# ``build_audit_record`` call, so hashes stay *stable within a run*: two
# audit records produced by the same process for equal content get equal
# hashes, which is the whole point of recording a hash at all (comparing
# whether two values are the same without either audit record holding the
# value). Across independent process runs -- and hence across independent
# experiment runs -- the key differs, so the resulting hashes are not
# reproducible from one run to the next either.
#
# ``audit_key`` on ``build_audit_record`` makes this injectable: production
# code must never pass it (so it gets this non-reproducible per-process
# default), while tests can pass a fixed key to get deterministic hashes to
# assert against -- mirroring ``InMemoryVault``'s injectable ``token_factory``.
_AUDIT_HASH_KEY_NBYTES = 32
_DEFAULT_AUDIT_HASH_KEY: bytes = secrets.token_bytes(_AUDIT_HASH_KEY_NBYTES)


def _content_hash(value: str, key: bytes) -> str:
    """HMAC-SHA256 hex digest of ``value``, keyed by ``key``.

    A correlation aid, exactly the "identifiers/hashes" README.md's audit
    model and issue #26's acceptance criteria call for: it lets two audit
    records be compared for "same content" without either of them carrying
    the content itself, and it lets an operator confirm a payload matches a
    known value without the audit record ever holding that value -- but only
    an operator who holds ``key``, which never appears in the audit record
    itself. See the module-level key material comment above for why this
    must be keyed rather than a plain unkeyed digest.
    """
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


class DetectionStage(BaseModel):
    """``raw input -> detected spans``: counts and categories only, never a
    detected value.
    """

    span_count: int
    categories: list[str]


class TransformationStage(BaseModel):
    """``policy decisions -> transformed payload``: the outcome shape and a
    content hash of the external payload, never the payload itself.
    """

    status: str
    transformation_count: int
    actions_by_category: dict[str, str]
    payload_byte_count: int
    payload_hash: str


class ProviderStage(BaseModel):
    """``payload delivered to provider -> provider response``.

    ``called`` is ``False`` (and every other field ``None``/default) whenever
    the request was blocked before reaching a provider -- this is how a
    reader of the audit trail confirms BLOCK_REQUEST actually stopped the
    external call, without needing raw payload content to do so. ``called``
    is ``True`` whenever a provider was actually invoked, regardless of
    whether the call ultimately succeeded -- see ``failed``/``failure_kind``
    below for how an attempted-but-unsuccessful call is distinguished from a
    successful one.

    ``decoding_config`` records the decoding parameters the provider actually
    used (temperature, sampling strategy, max tokens, ...) -- issue #12
    requires model id, snapshot *and* decoding configuration recorded per run
    for reproducibility; without it a run cannot be reproduced. ``None``
    whenever no response was received (blocked request, or a failed/timed
    out call).

    ``failed``/``failure_kind`` record a provider error or timeout (issue:
    "a provider error or timeout produces no audit at all") without ever
    recording the provider's own exception message -- a third-party client
    can echo request content in that message (see
    ``providers.invoke_provider``'s docstring) -- only the failure *kind*
    (the raised exception's class name, e.g. ``"ProviderError"`` or
    ``"ProviderTimeoutError"``).
    """

    called: bool
    provider_class: str | None = None
    model_id: str | None = None
    model_snapshot: str | None = None
    decoding_config: dict[str, Any] | None = None
    transmitted_bytes: int | None = None
    response_hash: str | None = None
    failed: bool = False
    failure_kind: str | None = None


class ReconstructionStage(BaseModel):
    """``locally reconstructed response``.

    ``attempted`` is ``False`` for a treatment with no reconstruction
    capability (B0, B1) or a blocked request -- never fabricated as "not
    applicable" text that could be confused with an actual outcome.
    """

    attempted: bool
    reconstructed_hash: str | None = None
    changed_from_provider_response: bool | None = None


class RawValueCapture(BaseModel):
    """Only ever populated when a caller explicitly opts in via
    ``capture_raw_values_for_controlled_experiment=True`` on
    ``build_audit_record``. Every other field on ``AuditRecord`` must remain
    hash/metadata-only regardless of whether this is present.
    """

    raw_input_text: str
    external_payload: str
    provider_response_text: str | None = None
    reconstructed_text: str | None = None


class AuditRecord(BaseModel):
    """One run's full structural audit trail, covering every stage
    README.md names. Safe to log or persist in full by default: ``raw`` is
    ``None`` unless a caller explicitly opted in (see module docstring).
    """

    treatment: Treatment
    domain: str
    purpose: str
    status: str
    detection: DetectionStage
    decisions: list[PolicyDecision]
    transformation: TransformationStage
    provider: ProviderStage
    reconstruction: ReconstructionStage
    raw: RawValueCapture | None = None


def build_audit_record(
    *,
    request: DisclosureRequest,
    spans: list[SensitiveSpan],
    result: DisclosureResult,
    treatment: Treatment,
    provider_response: ProviderResponse | None,
    provider_class: str | None,
    reconstructed_text: str | None,
    provider_attempted: bool | None = None,
    provider_failure_kind: str | None = None,
    capture_raw_values_for_controlled_experiment: bool = False,
    audit_hash_key: bytes | None = None,
) -> AuditRecord:
    """Build the structural audit record for one run of one case through one
    treatment.

    ``provider_response`` is ``None`` whenever the request never reached a
    provider (``result.status == "blocked"``) or reached one that failed.
    ``provider_attempted`` tells these two ``None`` cases apart: pass it
    explicitly (``True``/``False``) whenever the caller knows for certain
    whether a call was actually made -- ``pipeline.run_disclosure_case`` does
    this so a provider error/timeout still records ``called=True,
    failed=True`` rather than looking identical to a blocked request that
    never reached a provider at all. Left ``None`` (the default), it is
    inferred as ``provider_response is not None``, which preserves this
    function's previous behavior for callers -- such as the direct
    ``tests/test_audit.py`` call sites -- that only ever describe a fully
    successful or a blocked run. ``provider_failure_kind`` records the raised
    exception's class name only (e.g. ``"ProviderError"``,
    ``"ProviderTimeoutError"``) -- never its message, which a third-party
    provider client could have populated with request content.

    ``reconstructed_text`` is ``None`` whenever the treatment has no
    reconstruction capability (B0, B1), the request was blocked, or the
    provider call failed; the resulting ``ReconstructionStage.attempted`` is
    ``False``.

    ``capture_raw_values_for_controlled_experiment`` defaults to ``False``
    and must be passed explicitly by a caller to capture anything beyond
    metadata -- see the module docstring for why this boundary matters and
    why the flag is named the way it is.

    ``audit_hash_key`` is the HMAC key used for every content hash in this
    record (``payload_hash``, ``response_hash``, ``reconstructed_hash``) --
    see the module-level key material comment near ``_content_hash`` for why
    this must be keyed rather than a plain digest. Left ``None`` (the
    production default), it uses this process's non-reproducible default key
    so hashes cannot be dictionary-attacked from outside this trust boundary
    but stay stable within this run. Tests may inject a fixed key for
    deterministic assertions; the key itself is never stored on
    ``AuditRecord`` or otherwise exposed.
    """
    key = audit_hash_key if audit_hash_key is not None else _DEFAULT_AUDIT_HASH_KEY
    attempted = (
        provider_attempted if provider_attempted is not None else provider_response is not None
    )
    failed = provider_failure_kind is not None

    detection = DetectionStage(
        span_count=len(spans),
        categories=sorted({span.category for span in spans}),
    )

    transformation = TransformationStage(
        status=result.status,
        transformation_count=len(result.transformations),
        actions_by_category={
            decision.category: decision.action.value for decision in result.decisions
        },
        payload_byte_count=len(result.external_payload.encode("utf-8")),
        payload_hash=_content_hash(result.external_payload, key),
    )

    provider_stage = ProviderStage(
        called=attempted,
        provider_class=provider_class if attempted else None,
        model_id=provider_response.model_id if provider_response is not None else None,
        model_snapshot=provider_response.model_snapshot if provider_response is not None else None,
        decoding_config=(
            dict(provider_response.decoding_config) if provider_response is not None else None
        ),
        transmitted_bytes=(
            provider_response.transmitted_bytes if provider_response is not None else None
        ),
        response_hash=(
            _content_hash(provider_response.text, key) if provider_response is not None else None
        ),
        failed=failed,
        failure_kind=provider_failure_kind,
    )

    reconstruction_stage = ReconstructionStage(
        attempted=reconstructed_text is not None,
        reconstructed_hash=(
            _content_hash(reconstructed_text, key) if reconstructed_text is not None else None
        ),
        changed_from_provider_response=(
            reconstructed_text != provider_response.text
            if reconstructed_text is not None and provider_response is not None
            else None
        ),
    )

    raw = None
    if capture_raw_values_for_controlled_experiment:
        raw = RawValueCapture(
            raw_input_text=request.text,
            external_payload=result.external_payload,
            provider_response_text=(
                provider_response.text if provider_response is not None else None
            ),
            reconstructed_text=reconstructed_text,
        )

    return AuditRecord(
        treatment=treatment,
        domain=request.context.domain,
        purpose=request.context.purpose,
        status=result.status,
        detection=detection,
        decisions=result.decisions,
        transformation=transformation,
        provider=provider_stage,
        reconstruction=reconstruction_stage,
        raw=raw,
    )
