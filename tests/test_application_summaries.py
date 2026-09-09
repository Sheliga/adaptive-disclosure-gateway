"""T20 / issue #28, slice 1: ``application/summaries.py`` builds the
presentational ``DisclosureSummary`` from a real ``pipeline.DisclosureDecision``
-- the shared decision phase both preview and execute run through. These
tests run real treatments (no mocking of core logic) so a real production
defect in the action->outcome mapping or the occurrence-count derivation
can actually fail them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_disclosure_gateway.application.contracts import DisclosureOutcome
from adaptive_disclosure_gateway.application.summaries import build_disclosure_summary
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
)
from adaptive_disclosure_gateway.pipeline import decide_disclosure
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations import ReversiblePseudonymizer, StaticSanitizer
from adaptive_disclosure_gateway.vault import InMemoryVault

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

HR_TEXT = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
HR_TEXT_WITH_MEDICAL = HR_TEXT + "Medical notes: Reports chronic migraine.\n"


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
        "session_id": "s1",
    }
    values.update(overrides)
    return GovernanceContext(**values)


def _request(text: str, task: str = "summarize personnel record", **overrides) -> DisclosureRequest:
    return DisclosureRequest(text=text, task=task, context=_context(**overrides))


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def test_summary_for_an_allowed_static_sanitization_case_maps_every_category_correctly():
    decision = decide_disclosure(StaticSanitizer(), _request(HR_TEXT))
    summary = build_disclosure_summary(decision)

    assert summary.status == "allowed"
    by_category = {c.category: c for c in summary.categories}

    # employee_name/cpf are REMOVEd by B1 -- outcome REMOVED, does not cross.
    assert by_category["employee_name"].outcome == DisclosureOutcome.REMOVED
    assert by_category["employee_name"].crosses_trust_boundary is False
    assert by_category["employee_name"].action == DisclosureAction.REMOVE

    # salary is GENERALIZEd -- outcome GENERALIZED, crosses.
    assert by_category["salary"].outcome == DisclosureOutcome.GENERALIZED
    assert by_category["salary"].crosses_trust_boundary is True

    # department is PRESERVEd -- outcome PRESERVED, crosses.
    assert by_category["department"].outcome == DisclosureOutcome.PRESERVED
    assert by_category["department"].crosses_trust_boundary is True

    assert summary.detected_span_count == len(decision.spans)
    assert summary.detected_categories == tuple(sorted({s.category for s in decision.spans}))


def test_summary_occurrence_count_matches_the_number_of_detected_occurrences():
    text = "Employee: Ana Souza\nEmployee: Ana Souza again\n"
    # Craft a request whose text has employee_name appearing twice is hard
    # with the real detector's line rule (one labeled line per field); use
    # the CPF regex rule instead, which can match multiple times in one text.
    text = "CPF: 123.456.789-09 and again CPF: 987.654.321-00\n"
    decision = decide_disclosure(StaticSanitizer(), _request(text))
    summary = build_disclosure_summary(decision)

    cpf_summary = next(c for c in summary.categories if c.category == "cpf")
    cpf_span_count = len([s for s in decision.spans if s.category == "cpf"])
    assert cpf_span_count == 2
    assert cpf_summary.occurrence_count == cpf_span_count


def test_summary_for_a_blocked_case_reports_blocked_status_and_outcome():
    decision = decide_disclosure(StaticSanitizer(), _request(HR_TEXT_WITH_MEDICAL))
    summary = build_disclosure_summary(decision)

    assert summary.status == "blocked"
    medical = next(c for c in summary.categories if c.category == "medical_data")
    assert medical.outcome == DisclosureOutcome.BLOCKED
    assert medical.crosses_trust_boundary is False
    assert medical.action == DisclosureAction.BLOCK_REQUEST


def test_summary_carries_required_for_task_and_reason_through_from_b2():
    decision = decide_disclosure(
        ReversiblePseudonymizer(vault=InMemoryVault(), policy_repository=_policy_repo()),
        _request(HR_TEXT),
    )
    summary = build_disclosure_summary(decision)

    employee = next(c for c in summary.categories if c.category == "employee_name")
    assert employee.outcome == DisclosureOutcome.PSEUDONYMIZED
    assert employee.crosses_trust_boundary is True
    # B2's static category->action mapping never consults PolicyRepository
    # to choose an action (see reversible_pseudonymization.py's module
    # docstring), so its PolicyDecision.policy_version stays None -- only
    # B4 -- Policy-governed ever sets it.
    assert employee.policy_version is None
    # B2 does not evaluate task necessity -- task_required stays None.
    assert employee.required_for_task is None
    assert isinstance(employee.technical_reason, str) and employee.technical_reason


def test_summary_carries_the_real_policy_version_through_from_b4():
    from adaptive_disclosure_gateway.transformations import PolicyGovernedDiscloser

    decision = decide_disclosure(
        PolicyGovernedDiscloser(vault=InMemoryVault(), policy_repository=_policy_repo()),
        _request(HR_TEXT, purpose="salary_analysis"),
    )
    summary = build_disclosure_summary(decision)

    salary = next(c for c in summary.categories if c.category == "salary")
    assert salary.policy_version == "hr-v1"
    assert salary.policy_restricted in (True, False)
    assert salary.impossible_under_policy in (True, False)


def test_every_disclosure_action_is_covered_by_the_outcome_mapping():
    """A future action added to DisclosureAction must not silently default
    to 'does not cross the trust boundary' by being absent from the
    mapping -- import the private mapping and assert it is exhaustive.
    """
    from adaptive_disclosure_gateway.application.summaries import _OUTCOME_BY_ACTION

    assert set(_OUTCOME_BY_ACTION) == set(DisclosureAction)


def test_a_resolved_task_dependent_action_fails_closed_by_raising():
    """TASK_DEPENDENT must never reach the summary boundary as a resolved
    per-category action (PolicyRepository.decide() always resolves it to a
    concrete action first) -- if it ever does, this must raise rather than
    silently guessing an outcome.
    """
    from adaptive_disclosure_gateway.application.summaries import _outcome_for_action

    with pytest.raises(ValueError, match="TASK_DEPENDENT"):
        _outcome_for_action(DisclosureAction.TASK_DEPENDENT)
