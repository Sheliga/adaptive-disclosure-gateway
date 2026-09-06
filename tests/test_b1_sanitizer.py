from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
)
from adaptive_disclosure_gateway.transformations import B1StaticSanitizer


def _request(text: str, **context_overrides) -> DisclosureRequest:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
    }
    values.update(context_overrides)
    return DisclosureRequest(text=text, task="summarize", context=GovernanceContext(**values))


def test_remove_action_drops_value_and_does_not_leak_original():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    spans = Detector().detect(text)

    result = B1StaticSanitizer().sanitize(request, spans)

    assert "123.456.789-09" not in result.external_payload
    transformation = next(t for t in result.transformations if t.category == "cpf")
    assert transformation.transformed is None
    assert transformation.action is DisclosureAction.REMOVE


def test_generalize_action_replaces_salary_without_leaking_original_value():
    text = "Salary: R$ 8500.00 was paid.\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = B1StaticSanitizer().sanitize(request, spans)

    assert "8500" not in result.external_payload
    transformation = next(t for t in result.transformations if t.category == "salary")
    assert transformation.action is DisclosureAction.GENERALIZE
    assert transformation.transformed is not None
    assert "8500" not in transformation.transformed


def test_preserve_action_keeps_department_value_in_payload():
    text = "Department: Engineering\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = B1StaticSanitizer().sanitize(request, spans)

    assert "Engineering" in result.external_payload
    transformation = next(t for t in result.transformations if t.category == "department")
    assert transformation.action is DisclosureAction.PRESERVE
    assert transformation.transformed == "Engineering"


def test_medical_data_blocks_entire_request_and_suppresses_other_spans():
    text = "Employee: Ana Souza\nMedical notes: Reports chronic migraine.\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = B1StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert result.transformations == []
    assert "Ana Souza" not in result.external_payload


def test_unmapped_category_fails_closed_instead_of_leaking():
    from adaptive_disclosure_gateway.domain import SensitiveSpan

    request = _request("some free text value here")
    spans = [SensitiveSpan(category="unknown_category", value="value here", start=15, end=25)]

    result = B1StaticSanitizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert "value here" not in result.external_payload


def test_sanitizer_output_is_independent_of_governance_context():
    text = "Department: Engineering\n"
    spans = Detector().detect(text)

    result_a = B1StaticSanitizer().sanitize(
        _request(text, purpose="team_summary", requester_role="hr_viewer"), spans
    )
    result_b = B1StaticSanitizer().sanitize(
        _request(text, purpose="salary_analysis", requester_role="hr_admin"), spans
    )

    assert result_a.external_payload == result_b.external_payload
    assert result_a.transformations == result_b.transformations
    assert result_a.status == result_b.status


def test_sanitizer_is_deterministic_across_runs():
    text = "Salary: R$ 8500.00\nDepartment: Engineering\n"
    request = _request(text)
    spans = Detector().detect(text)

    first = B1StaticSanitizer().sanitize(request, spans)
    second = B1StaticSanitizer().sanitize(request, spans)

    assert first == second
