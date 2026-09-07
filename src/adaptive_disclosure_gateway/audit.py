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

from pydantic import BaseModel

from adaptive_disclosure_gateway.domain import (
    DisclosureRequest,
    DisclosureResult,
    PolicyDecision,
    SensitiveSpan,
    Treatment,
)
from adaptive_disclosure_gateway.providers import ProviderResponse


def _content_hash(value: str) -> str:
    """SHA-256 hex digest of ``value``.

    Not a security commitment (no salt or key) -- purely a correlation aid,
    exactly the "identifiers/hashes" README.md's audit model and issue #26's
    acceptance criteria call for: it lets two audit records be compared for
    "same content" without either of them carrying the content itself, and
    it lets an operator confirm a payload matches a known value without the
    audit record ever holding that value.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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

    ``called`` is ``False`` (and every other field ``None``) whenever the
    request was blocked before reaching a provider -- this is how a reader
    of the audit trail confirms BLOCK_REQUEST actually stopped the external
    call, without needing raw payload content to do so.
    """

    called: bool
    provider_class: str | None = None
    model_id: str | None = None
    model_snapshot: str | None = None
    transmitted_bytes: int | None = None
    response_hash: str | None = None


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
    capture_raw_values_for_controlled_experiment: bool = False,
) -> AuditRecord:
    """Build the structural audit record for one run of one case through one
    treatment.

    ``provider_response`` is ``None`` whenever the request never reached a
    provider (``result.status == "blocked"``) -- the resulting
    ``ProviderStage.called`` is ``False`` and every other provider field is
    ``None``, which is how a reader confirms BLOCK_REQUEST actually stopped
    the external call. ``reconstructed_text`` is ``None`` whenever the
    treatment has no reconstruction capability (B0, B1) or the request was
    blocked; the resulting ``ReconstructionStage.attempted`` is ``False``.

    ``capture_raw_values_for_controlled_experiment`` defaults to ``False``
    and must be passed explicitly by a caller to capture anything beyond
    metadata -- see the module docstring for why this boundary matters and
    why the flag is named the way it is.
    """
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
        payload_hash=_content_hash(result.external_payload),
    )

    provider_stage = ProviderStage(
        called=provider_response is not None,
        provider_class=provider_class if provider_response is not None else None,
        model_id=provider_response.model_id if provider_response is not None else None,
        model_snapshot=provider_response.model_snapshot if provider_response is not None else None,
        transmitted_bytes=(
            provider_response.transmitted_bytes if provider_response is not None else None
        ),
        response_hash=(
            _content_hash(provider_response.text) if provider_response is not None else None
        ),
    )

    reconstruction_stage = ReconstructionStage(
        attempted=reconstructed_text is not None,
        reconstructed_hash=(
            _content_hash(reconstructed_text) if reconstructed_text is not None else None
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
