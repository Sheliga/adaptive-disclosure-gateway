"""Pins T08 / issue #7 Phase A's controlled HR policy matrix
(``configs/policies/hr-v2.yaml``, ``configs/policies/hr-v3.yaml``) directly
against ``PolicyRepository.decide()`` -- independent of any B4 treatment
code -- so a future edit that silently flattens the matrix (removing the
very variation the B3->B4 experiment needs to measure) fails this suite
immediately, before it could ever reach B4's own behavioral tests.

Two families of test live here:

1. **hr-v1 inventory confirmation** -- re-verifies, directly against
   ``PolicyRepository``, this ticket's Phase A measurement of hr-v1's
   *existing* behavior: only `salary` x `purpose` varies the resolved
   action space; `requester_role` and `provider_class` change nothing about
   disclosure action (only pseudonym scope, a separate axis); `hr_analyst`
   and `hr_admin` resolve the same pseudonym scope absent an explicit
   `requested_pseudonym_scope`. This is the baseline the new matrix is
   built to extend, not replace -- ``configs/policies/hr-v1.yaml`` itself is
   never edited (CLAUDE.md's hard restriction).
2. **hr-v2/hr-v3 identifiability** -- for each of the four contextual
   dimensions the B4 experiment claims (`purpose`, `requester_role`,
   `provider_class`, `policy_version`), at least one matrix cell exists
   where the *resolved* action/allowed-action-space genuinely differs when
   only that one dimension changes and everything else is held constant.
   This is written to fail for real: a future edit collapsing any one of
   these cells back to a constant resolution breaks the corresponding
   assertion, not just a docstring's claim.

None of this derives a rule from ``corpus/hr/v1``, `sample_id`,
`task_family` or oracle content -- these tests only exercise the policy
matrix itself via governance-context fixtures constructed inline.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    GovernanceContext,
    PseudonymScope,
)
from adaptive_disclosure_gateway.policies import PolicyRepository

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "requester_role": "hr_analyst",
        "policy_version": "hr-v1",
    }
    values.update(overrides)
    return GovernanceContext(**values)


# --- 1. hr-v1 inventory confirmation ----------------------------------------


def test_hr_v1_salary_purpose_is_the_only_cell_that_varies_disclosure_action_space():
    repo = _repo()

    generic_purpose_actions = repo.decide(
        _context(purpose="team_summary", policy_version="hr-v1"), "salary"
    ).allowed_actions
    compensation_purpose_actions = repo.decide(
        _context(purpose="salary_analysis", policy_version="hr-v1"), "salary"
    ).allowed_actions

    assert generic_purpose_actions == [DisclosureAction.REMOVE, DisclosureAction.GENERALIZE]
    assert compensation_purpose_actions == [
        DisclosureAction.REMOVE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    ]
    assert generic_purpose_actions != compensation_purpose_actions


def test_hr_v1_requester_role_never_changes_any_categorys_resolved_action():
    repo = _repo()
    categories = ["employee_name", "cpf", "medical_data", "department"]
    roles = ["hr_viewer", "hr_analyst", "hr_admin"]

    for category in categories:
        resolved = {
            role: repo.decide(
                _context(requester_role=role, policy_version="hr-v1"), category
            ).action
            for role in roles
        }
        assert len(set(resolved.values())) == 1, (
            f"expected hr-v1's {category!r} action to be role-invariant, got {resolved}"
        )

    # salary/team_summary (a purpose whose allowed_actions never includes
    # PRESERVE) also never varies by role under hr-v1.
    salary_by_role = {
        role: repo.decide(
            _context(requester_role=role, purpose="team_summary", policy_version="hr-v1"),
            "salary",
        ).allowed_actions
        for role in roles
    }
    assert len({tuple(v) for v in salary_by_role.values()}) == 1


def test_hr_v1_provider_class_never_changes_any_categorys_resolved_action():
    repo = _repo()
    categories = ["employee_name", "cpf", "medical_data", "department"]
    provider_classes = ["external_llm", "internal_llm"]

    for category in categories:
        resolved = {
            provider_class: repo.decide(
                _context(provider_class=provider_class, policy_version="hr-v1"), category
            ).action
            for provider_class in provider_classes
        }
        assert len(set(resolved.values())) == 1, (
            f"expected hr-v1's {category!r} action to be provider_class-invariant, got {resolved}"
        )

    salary_by_provider = {
        provider_class: repo.decide(
            _context(
                provider_class=provider_class, purpose="salary_analysis", policy_version="hr-v1"
            ),
            "salary",
        ).allowed_actions
        for provider_class in provider_classes
    }
    assert len({tuple(v) for v in salary_by_provider.values()}) == 1


def test_hr_v2_and_hr_v3_sit_alongside_the_frozen_hr_v1_baseline():
    # Before this ticket, hr-v1 was the only hr-domain policy version (Phase
    # A's inventory). This pins that hr-v2/hr-v3 are added *alongside*
    # hr-v1, not a replacement for it -- configs/policies/hr-v1.yaml itself
    # is never edited (CLAUDE.md's hard restriction).
    repo = _repo()
    hr_versions = {version for version, policy in repo._policies.items() if policy.domain == "hr"}
    assert {"hr-v1", "hr-v2", "hr-v3"} <= hr_versions


def test_hr_v1_role_ceiling_makes_analyst_and_admin_resolve_the_same_scope_absent_a_request():
    # Confirms the Phase A inventory claim: without an explicit
    # requested_pseudonym_scope in the context, hr_analyst and hr_admin
    # resolve to the same scope, because role_max is a ceiling
    # (min(requested, ceiling)) and the default requested_pseudonym_scope
    # (SESSION) already sits below hr_analyst's own ceiling (also SESSION).
    repo = _repo()
    analyst_scope = repo.resolve_pseudonym_scope(
        _context(requester_role="hr_analyst", policy_version="hr-v1")
    )
    admin_scope = repo.resolve_pseudonym_scope(
        _context(requester_role="hr_admin", policy_version="hr-v1")
    )
    assert analyst_scope == admin_scope == PseudonymScope.SESSION


# --- 2. hr-v2/hr-v3 identifiability ----------------------------------------


def test_purpose_dimension_changes_the_resolved_action_space_in_hr_v2():
    repo = _repo()
    generic = repo.decide(
        _context(purpose="team_summary", requester_role="hr_analyst", policy_version="hr-v2"),
        "salary",
    )
    compensation = repo.decide(
        _context(purpose="salary_analysis", requester_role="hr_analyst", policy_version="hr-v2"),
        "salary",
    )
    assert generic.allowed_actions != compensation.allowed_actions
    assert DisclosureAction.PRESERVE not in generic.allowed_actions
    assert DisclosureAction.PRESERVE in compensation.allowed_actions


def test_requester_role_dimension_changes_the_resolved_action_in_hr_v2():
    repo = _repo()
    analyst = repo.decide(
        _context(purpose="salary_analysis", requester_role="hr_analyst", policy_version="hr-v2"),
        "salary",
    )
    viewer = repo.decide(
        _context(purpose="salary_analysis", requester_role="hr_viewer", policy_version="hr-v2"),
        "salary",
    )
    assert analyst.action is DisclosureAction.TASK_DEPENDENT
    assert DisclosureAction.PRESERVE in analyst.allowed_actions
    assert viewer.action is DisclosureAction.REMOVE
    assert analyst.allowed_actions != viewer.allowed_actions


def test_requester_role_override_survives_every_purpose_including_ones_with_purpose_actions():
    # The engine-trap regression: a viewer's hard REMOVE override must hold
    # for every purpose, specifically including purposes that have their own
    # purpose_actions entry (which would otherwise silently overwrite a
    # TASK_DEPENDENT override's allowed_actions -- see policies.py's decide()
    # and docs/hr-policy-matrix.md's "engine trap" section).
    repo = _repo()
    for purpose in ("team_summary", "salary_analysis", "compensation_review", "headcount_planning"):
        decision = repo.decide(
            _context(purpose=purpose, requester_role="hr_viewer", policy_version="hr-v2"),
            "salary",
        )
        assert decision.action is DisclosureAction.REMOVE, (
            f"expected hr_viewer's salary override to hold for purpose={purpose!r}, "
            f"got action={decision.action!r}"
        )


def test_provider_class_dimension_changes_the_resolved_action_in_hr_v2():
    repo = _repo()
    internal = repo.decide(
        _context(provider_class="internal_llm", policy_version="hr-v2"), "employee_name"
    )
    external = repo.decide(
        _context(provider_class="external_llm", policy_version="hr-v2"), "employee_name"
    )
    assert internal.action is DisclosureAction.PSEUDONYMIZE
    assert external.action is DisclosureAction.REMOVE
    assert internal.action != external.action


def test_policy_version_dimension_changes_the_resolved_action_space_between_v2_and_v3():
    repo = _repo()
    context = _context(
        purpose="compensation_review", requester_role="hr_analyst", policy_version="hr-v2"
    )
    v2_decision = repo.decide(context, "salary")
    v3_decision = repo.decide(context.model_copy(update={"policy_version": "hr-v3"}), "salary")

    assert DisclosureAction.PRESERVE in v2_decision.allowed_actions
    assert DisclosureAction.PRESERVE not in v3_decision.allowed_actions
    assert v2_decision.allowed_actions != v3_decision.allowed_actions

    # salary_analysis is the deliberately-unchanged purpose between v2 and
    # v3 -- confirms the delta is scoped to compensation_review only, not a
    # blanket rewrite of the whole salary rule.
    unaffected_context = context.model_copy(update={"purpose": "salary_analysis"})
    v2_salary_analysis = repo.decide(unaffected_context, "salary").allowed_actions
    v3_salary_analysis = repo.decide(
        unaffected_context.model_copy(update={"policy_version": "hr-v3"}), "salary"
    ).allowed_actions
    assert v2_salary_analysis == v3_salary_analysis


def test_hr_v2_and_hr_v3_both_still_block_medical_data_unconditionally():
    repo = _repo()
    for version in ("hr-v2", "hr-v3"):
        decision = repo.decide(_context(policy_version=version), "medical_data")
        assert decision.action is DisclosureAction.BLOCK_REQUEST


def test_hr_v2_and_hr_v3_domain_stays_hr_not_a_substitute_cross_domain_change():
    repo = _repo()
    for version in ("hr-v2", "hr-v3"):
        assert repo._policies[version].domain == "hr"
