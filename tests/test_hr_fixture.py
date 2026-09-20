"""Controlled synthetic HR fixture for Milestone 1's first vertical slice.

The values below are invented for testing only (no real employer or
organizational data), and exercise all five frozen HR categories:
employee_name, cpf, salary, department and medical_data.
"""

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
)
from adaptive_disclosure_gateway.transformations import StaticSanitizer

HR_FIXTURE_NO_MEDICAL = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)

HR_FIXTURE_WITH_MEDICAL = HR_FIXTURE_NO_MEDICAL + (
    "Medical notes: Reports chronic migraine and requested leave.\n"
)


def _request(text: str) -> DisclosureRequest:
    return DisclosureRequest(
        text=text,
        task="summarize personnel record",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )


def test_detector_covers_all_five_frozen_hr_categories():
    spans = Detector().detect(HR_FIXTURE_WITH_MEDICAL)
    categories = {span.category for span in spans}

    assert categories == {
        "employee_name",
        "cpf",
        "salary",
        "department",
        "medical_data",
    }


def test_b1_sanitizes_non_medical_fixture_without_leaking_removed_or_generalized_values():
    text = HR_FIXTURE_NO_MEDICAL
    spans = Detector().detect(text)

    result = StaticSanitizer().sanitize(_request(text), spans)

    assert result.status == "allowed"
    assert "Ana Souza" not in result.external_payload
    assert "123.456.789-09" not in result.external_payload
    assert "8500.00" not in result.external_payload
    assert "Engineering" in result.external_payload

    actions_by_category = {t.category: t.action for t in result.transformations}
    assert actions_by_category == {
        "employee_name": DisclosureAction.REMOVE,
        "cpf": DisclosureAction.REMOVE,
        "salary": DisclosureAction.GENERALIZE,
        "department": DisclosureAction.PRESERVE,
    }


def test_b1_blocks_fixture_with_medical_data_and_leaks_nothing():
    text = HR_FIXTURE_WITH_MEDICAL
    spans = Detector().detect(text)

    result = StaticSanitizer().sanitize(_request(text), spans)

    assert result.status == "blocked"
    assert result.external_payload == ""
