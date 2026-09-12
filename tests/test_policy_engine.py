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


def test_reconstruction_is_authorized_for_a_valid_matching_policy():
    repository = PolicyRepository.from_directory(POLICY_DIR)

    assert repository.is_reconstruction_authorized(_context()) is True


def test_reconstruction_is_blocked_when_policy_version_is_missing():
    repository = PolicyRepository.from_directory(POLICY_DIR)

    assert (
        repository.is_reconstruction_authorized(_context(policy_version="does-not-exist")) is False
    )


def test_reconstruction_is_blocked_on_domain_mismatch():
    repository = PolicyRepository.from_directory(POLICY_DIR)

    resolved = repository.is_reconstruction_authorized(
        _context(domain="contracts", policy_version="hr-v1")
    )

    assert resolved is False


# --- Unknown policy keys must fail closed, never be silently dropped -------
#
# Issue #56 found `configs/policies/contracts-v1.yaml` shipping a top-level
# `semantic_constraints:` block (`preserve_party_roles`,
# `preserve_obligation_assignment`) that `PolicyDocument` never declared.
# Pydantic's default `extra` behaviour dropped it silently, so the YAML read
# as if two governance guarantees were enforced while nothing in the engine
# had ever heard of them. That is the fail-OPEN direction: a governance knob
# that looks enforced and is ignored is strictly worse than one that is
# absent, because a reviewer reading the config concludes the wrong thing.
#
# The fix is structural rather than a one-off YAML cleanup: the model
# rejects unknown keys, so `from_directory` records a load error, and every
# request under that version resolves to BLOCK_REQUEST (the loader treats an
# unloadable document as a missing policy). Fail-closed, and impossible to
# reintroduce by adding another undeclared key later.


def _write_policy(tmp_path: Path, body: str) -> PolicyRepository:
    (tmp_path / "probe-v1.yaml").write_text(body, encoding="utf-8")
    return PolicyRepository.from_directory(tmp_path)


def test_unknown_top_level_policy_key_fails_to_load_instead_of_being_silently_dropped(tmp_path):
    repository = _write_policy(
        tmp_path,
        "version: probe-v1\n"
        "domain: probe\n"
        "rules:\n"
        "  some_category:\n"
        "    default: preserve\n"
        "semantic_constraints:\n"
        "  preserve_party_roles: true\n",
    )

    assert "probe-v1.yaml" in repository.load_errors

    decision = repository.decide(
        _context(domain="probe", policy_version="probe-v1"), "some_category"
    )
    assert decision.action is DisclosureAction.BLOCK_REQUEST


def test_unknown_rule_level_policy_key_fails_to_load(tmp_path):
    repository = _write_policy(
        tmp_path,
        "version: probe-v1\n"
        "domain: probe\n"
        "rules:\n"
        "  some_category:\n"
        "    default: preserve\n"
        "    allowed_action: [preserve]\n",
    )

    assert "probe-v1.yaml" in repository.load_errors


def test_unknown_override_and_scope_keys_fail_to_load(tmp_path):
    repository = _write_policy(
        tmp_path,
        "version: probe-v1\n"
        "domain: probe\n"
        "pseudonym_scope:\n"
        "  default: session\n"
        "  role_maximum:\n"
        "    probe_viewer: request\n"
        "rules:\n"
        "  some_category:\n"
        "    default: preserve\n",
    )

    assert "probe-v1.yaml" in repository.load_errors


def test_every_shipped_policy_document_still_loads_under_the_stricter_model():
    # The other half of the invariant above: forbidding unknown keys turns a
    # typo in any shipped YAML into "policy missing" for every request under
    # that version. That is the right posture, but it must be visible here
    # rather than discovered as an unexplained BLOCK_REQUEST at runtime.
    repository = PolicyRepository.from_directory(POLICY_DIR)

    assert repository.load_errors == {}
