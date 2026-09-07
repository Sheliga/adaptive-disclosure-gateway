"""Pins the OTel acceptance criterion: spans may carry categories, counts and
timing only -- never the detected value, the raw text, or the payload.
"""

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext
from adaptive_disclosure_gateway.transformations import StaticSanitizer

SECRET_TEXT = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)


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
    recorded_spans.clear()  # isolate B1's own span from the detector's

    result = StaticSanitizer().sanitize(request, spans)

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished, "Ana Souza", "123.456.789-09", "8500", SECRET_TEXT, result.external_payload
    )
