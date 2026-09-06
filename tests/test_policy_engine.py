from pathlib import Path

from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    GovernanceContext,
    PseudonymScope,
)
from adaptive_disclosure_gateway.policies import PolicyRepository


POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _context(**overrides):
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "requester_role": "hr_analyst",
        "policy_version": "hr-v1",
    }
    values.update(overrides)
    return GovernanceContext(**values)


def test_hr_hard_rules_are_deterministic():
    repository = PolicyRepository.from_directory(POLICY_DIR)
    context = _context()

    assert repository.decide(context, "employee_name").action is DisclosureAction.PSEUDONYMIZE
    assert repository.decide(context, "cpf").action is DisclosureAction.REMOVE
    assert repository.decide(context, "medical_data").action is DisclosureAction.BLOCK_REQUEST
    assert repository.decide(context, "department").action is DisclosureAction.PRESERVE


def test_task_dependent_rule_returns_allowed_action_space():
    repository = PolicyRepository.from_directory(POLICY_DIR)
    decision = repository.decide(_context(purpose="salary_analysis"), "salary")

    assert decision.action is DisclosureAction.TASK_DEPENDENT
    assert decision.allowed_actions == [
        DisclosureAction.REMOVE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    ]


def test_missing_category_fails_closed():
    repository = PolicyRepository.from_directory(POLICY_DIR)
    decision = repository.decide(_context(), "unknown_category")

    assert decision.action is DisclosureAction.BLOCK_REQUEST
    assert "missing rule" in decision.reason.lower()


def test_missing_policy_version_fails_closed():
    repository = PolicyRepository.from_directory(POLICY_DIR)
    decision = repository.decide(_context(policy_version="does-not-exist"), "cpf")

    assert decision.action is DisclosureAction.BLOCK_REQUEST
    assert "policy" in decision.reason.lower()


def test_policy_domain_mismatch_fails_closed():
    repository = PolicyRepository.from_directory(POLICY_DIR)
    decision = repository.decide(
        _context(domain="contracts", policy_version="hr-v1"),
        "employee_name",
    )

    assert decision.action is DisclosureAction.BLOCK_REQUEST


def test_role_scope_is_a_ceiling_and_task_can_only_narrow_it():
    repository = PolicyRepository.from_directory(POLICY_DIR)

    request_scope = repository.resolve_pseudonym_scope(
        _context(requester_role="hr_viewer", requested_pseudonym_scope=PseudonymScope.SESSION)
    )
    admin_scope = repository.resolve_pseudonym_scope(
        _context(requester_role="hr_admin", requested_pseudonym_scope=PseudonymScope.ORGANIZATION)
    )

    assert request_scope is PseudonymScope.REQUEST
    assert admin_scope is PseudonymScope.ORGANIZATION


def test_unknown_role_does_not_gain_scope():
    repository = PolicyRepository.from_directory(POLICY_DIR)

    resolved = repository.resolve_pseudonym_scope(
        _context(requester_role="unknown", requested_pseudonym_scope=PseudonymScope.ORGANIZATION)
    )

    assert resolved is PseudonymScope.SESSION
