"""Pins issue #26's structural audit trail acceptance criteria.

The audit model this module implements mirrors README.md's stages: raw input
-> detected spans -> policy decisions -> transformed payload -> payload
delivered to provider -> provider response -> locally reconstructed
response.

The single most important property pinned here: by default, an
``AuditRecord`` carries metadata only (categories, counts, decisions,
actions, treatment identity, byte counts, content hashes) and is safe to
serialize and log *in full* -- never a raw value, the payload, a provider
response, or vault content. Full raw values are captured only when a caller
explicitly opts in via ``capture_raw_values_for_controlled_experiment=True``,
which must default to ``False`` and never be reachable implicitly.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.audit import build_audit_record
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext, Treatment
from adaptive_disclosure_gateway.providers import FakeProvider, ProviderRequest
from adaptive_disclosure_gateway.transformations import StaticSanitizer

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

HR_FIXTURE_NO_MEDICAL = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)
HR_FIXTURE_WITH_MEDICAL = HR_FIXTURE_NO_MEDICAL + (
    "Medical notes: Reports chronic migraine and requested leave.\n"
)

FORBIDDEN_RAW_SUBSTRINGS = ("Ana Souza", "123.456.789-09", "8500.00", HR_FIXTURE_NO_MEDICAL)


def _allowed_case():
    request = DisclosureRequest(
        text=HR_FIXTURE_NO_MEDICAL,
        task="summarize personnel record",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )
    spans = Detector().detect(request.text)
    result = StaticSanitizer().sanitize(request, spans)
    assert result.status == "allowed"
    provider_response = FakeProvider().generate(
        ProviderRequest(payload=result.external_payload, task=request.task)
    )
    return request, spans, result, provider_response


def test_audit_record_default_never_contains_raw_values_even_serialized_whole():
    request, spans, result, provider_response = _allowed_case()

    audit = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.STATIC_SANITIZATION,
        provider_response=provider_response,
        provider_class="fake",
        reconstructed_text=None,
    )

    assert audit.raw is None
    dumped = audit.model_dump_json()
    for forbidden in FORBIDDEN_RAW_SUBSTRINGS:
        assert forbidden not in dumped, f"audit record leaked raw value {forbidden!r}"


def test_audit_record_captures_raw_values_only_when_explicitly_opted_in():
    request, spans, result, provider_response = _allowed_case()

    without_opt_in = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.STATIC_SANITIZATION,
        provider_response=provider_response,
        provider_class="fake",
        reconstructed_text=None,
    )
    with_opt_in = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.STATIC_SANITIZATION,
        provider_response=provider_response,
        provider_class="fake",
        reconstructed_text=None,
        capture_raw_values_for_controlled_experiment=True,
    )

    assert without_opt_in.raw is None
    assert with_opt_in.raw is not None
    assert with_opt_in.raw.raw_input_text == HR_FIXTURE_NO_MEDICAL
    assert with_opt_in.raw.external_payload == result.external_payload
    assert "Ana Souza" in with_opt_in.raw.raw_input_text


def test_audit_record_covers_the_readme_stages_with_accurate_metadata():
    request, spans, result, provider_response = _allowed_case()

    audit = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.STATIC_SANITIZATION,
        provider_response=provider_response,
        provider_class="fake",
        reconstructed_text=None,
    )

    # raw input -> detected spans
    assert audit.detection.span_count == len(spans)
    assert audit.detection.categories == sorted({s.category for s in spans})
    # -> policy decisions
    assert audit.decisions == result.decisions
    # -> transformed payload
    assert audit.transformation.status == "allowed"
    assert audit.transformation.transformation_count == len(result.transformations)
    assert audit.transformation.payload_byte_count == len(result.external_payload.encode("utf-8"))
    # -> payload delivered to provider / provider response
    assert audit.provider.called is True
    assert audit.provider.model_id == provider_response.model_id
    assert audit.provider.transmitted_bytes == provider_response.transmitted_bytes
    # -> locally reconstructed response (not attempted for B1)
    assert audit.reconstruction.attempted is False


def test_audit_record_blocked_case_records_no_provider_or_reconstruction_activity():
    request = DisclosureRequest(
        text=HR_FIXTURE_WITH_MEDICAL,
        task="summarize personnel record",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )
    spans = Detector().detect(request.text)
    result = StaticSanitizer().sanitize(request, spans)
    assert result.status == "blocked"

    audit = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.STATIC_SANITIZATION,
        provider_response=None,
        provider_class=None,
        reconstructed_text=None,
    )

    assert audit.provider.called is False
    assert audit.provider.model_id is None
    assert audit.provider.transmitted_bytes is None
    assert audit.reconstruction.attempted is False
    assert audit.raw is None


def test_audit_record_reconstruction_stage_reflects_whether_the_response_actually_changed():
    request, spans, result, provider_response = _allowed_case()

    changed = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.REVERSIBLE_PSEUDONYMIZATION,
        provider_response=provider_response,
        provider_class="fake",
        reconstructed_text="a locally reconstructed answer, different from the raw response",
    )
    unchanged = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.REVERSIBLE_PSEUDONYMIZATION,
        provider_response=provider_response,
        provider_class="fake",
        reconstructed_text=provider_response.text,
    )

    assert changed.reconstruction.attempted is True
    assert changed.reconstruction.changed_from_provider_response is True
    assert unchanged.reconstruction.attempted is True
    assert unchanged.reconstruction.changed_from_provider_response is False
    # The reconstructed text's own hash must never equal the raw response's
    # hash when the content differs -- otherwise the hash would be useless
    # as a correlation aid.
    assert changed.reconstruction.reconstructed_hash != changed.provider.response_hash
