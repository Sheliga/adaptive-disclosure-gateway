"""Pins the OTel acceptance criterion: spans may carry categories, counts and
timing only -- never the detected value, the raw text, the payload, or (for
B2) the pseudonym mapping / vault content.
"""

from pathlib import Path

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations import ReversiblePseudonymizer, StaticSanitizer
from adaptive_disclosure_gateway.vault import InMemoryVault

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

SECRET_TEXT = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)

# Issue #16 (2b): a configured-but-unparseable GENERALIZE value, used below to
# confirm the fail-closed pre-pass doesn't leak the unparseable value through
# telemetry either -- not just through the external payload.
UNPARSEABLE_SALARY_TEXT = "Salary: to be negotiated later\n"


def _assert_span_attributes_never_leak(spans, *forbidden_values: str) -> None:
    assert spans, "expected at least one recorded span"
    for span in spans:
        for key, value in span.attributes.items():
            serialized = str(value)
            for forbidden in forbidden_values:
                if not forbidden:
                    continue
                assert forbidden not in serialized, (
                    f"span attribute {key}={serialized!r} leaked forbidden value {forbidden!r}"
                )


def test_detector_span_attributes_never_contain_detected_values_or_raw_text(recorded_spans):
    Detector().detect(SECRET_TEXT)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "Ana Souza", "123.456.789-09", "8500", SECRET_TEXT)


def test_b1_span_attributes_never_contain_detected_values_or_payload(recorded_spans):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task="summarize",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )
    spans = Detector().detect(SECRET_TEXT)
    recorded_spans.clear()  # isolate Static Sanitization (B1)'s own span from the detector's

    result = StaticSanitizer().sanitize(request, spans)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished, "Ana Souza", "123.456.789-09", "8500", SECRET_TEXT, result.external_payload
    )


def test_b2_span_attributes_never_contain_detected_values_payload_or_pseudonym_mapping(
    recorded_spans,
):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task="summarize",
        context=GovernanceContext(
            domain="hr", purpose="team_summary", requester_id="u1", policy_version="hr-v1"
        ),
    )
    spans = Detector().detect(SECRET_TEXT)
    recorded_spans.clear()  # isolate B2's own spans from the detector's

    pseudonymizer = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = pseudonymizer.sanitize(request, spans)

    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    # The mapping itself (which original a pseudonym stands for) is exactly
    # what the vault protects; a telemetry attribute combining the two would
    # leak the mapping even though neither string alone is sensitive here.
    pseudonym_mapping = f"Ana Souza:{pseudonym}"

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished,
        "Ana Souza",
        "123.456.789-09",
        "8500",
        SECRET_TEXT,
        result.external_payload,
        pseudonym_mapping,
    )


def test_b1_configured_unparseable_generalize_span_attributes_do_not_leak_the_value(
    recorded_spans,
):
    request = DisclosureRequest(
        text=UNPARSEABLE_SALARY_TEXT,
        task="summarize",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )
    spans = Detector().detect(UNPARSEABLE_SALARY_TEXT)
    recorded_spans.clear()  # isolate Static Sanitization (B1)'s own span from the detector's

    result = StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "to be negotiated later", UNPARSEABLE_SALARY_TEXT)


def test_b2_configured_unparseable_generalize_span_attributes_do_not_leak_the_value(
    recorded_spans,
):
    request = DisclosureRequest(
        text=UNPARSEABLE_SALARY_TEXT,
        task="summarize",
        context=GovernanceContext(
            domain="hr", purpose="team_summary", requester_id="u1", policy_version="hr-v1"
        ),
    )
    spans = Detector().detect(UNPARSEABLE_SALARY_TEXT)
    recorded_spans.clear()  # isolate B2's own spans from the detector's

    pseudonymizer = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = pseudonymizer.sanitize(request, spans)

    assert result.status == "blocked"
    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "to be negotiated later", UNPARSEABLE_SALARY_TEXT)


def test_b2_reconstruct_span_attributes_never_contain_original_values(recorded_spans):
    request = DisclosureRequest(
        text=SECRET_TEXT,
        task="summarize",
        context=GovernanceContext(
            domain="hr", purpose="team_summary", requester_id="u1", policy_version="hr-v1"
        ),
    )
    spans = Detector().detect(SECRET_TEXT)
    pseudonymizer = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    result = pseudonymizer.sanitize(request, spans)
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    recorded_spans.clear()  # isolate reconstruct()'s own span

    response_text = f"Contact {pseudonym} about the leave request."
    reconstructed = pseudonymizer.reconstruct(response_text, result, request.context)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(finished, "Ana Souza", SECRET_TEXT, reconstructed)
