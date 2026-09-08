"""T10 / issue #8 -- item 15: isolation of B4's contextual matrix
comparisons.

Per ``docs/hr-policy-matrix.md``, only four dimensions (``purpose``,
``requester_role``, ``provider_class``, ``policy_version``) have at least
one documented cell where the resolved policy permission genuinely changes
-- and only for specific category/context combinations, never a cartesian
product. This file pins:

- every declared comparison spec genuinely changes the resolved
  action/allowed-action-space for its category (the identifiability
  guarantee ``docs/hr-policy-matrix.md`` already requires of the policy
  documents themselves, now proven end-to-end through the real B4
  treatment rather than only against ``PolicyRepository`` directly);
- each comparison holds every *other* ``GovernanceContext`` field
  byte-for-byte identical between its two sides -- so an observed
  difference is attributable only to the one named dimension;
- a dimension that does *not* change anything under a given policy
  (hr-v1's ``requester_role``/``provider_class`` invariance,
  ``docs/hr-policy-matrix.md``'s own inventory) is correctly reported as
  "no permission change" rather than spuriously flagged.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.experiments.contextual_matrix import (
    CONTEXTUAL_MATRIX_SPECS,
    evaluate_contextual_comparison,
    run_contextual_comparison,
)
from adaptive_disclosure_gateway.experiments.corpus_source import build_request, load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.policies import PolicyRepository

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _cases():
    return {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def test_every_declared_contextual_spec_covers_exactly_one_of_the_four_documented_dimensions():
    dimensions = {spec.dimension for spec in CONTEXTUAL_MATRIX_SPECS}
    assert dimensions == {"purpose", "requester_role", "provider_class", "policy_version"}


def test_every_declared_contextual_comparison_genuinely_changes_the_resolved_permission():
    cases = _cases()
    policy_repo = _policy_repo()

    for spec in CONTEXTUAL_MATRIX_SPECS:
        case = cases[spec.base_sample_id]
        execution_a, execution_b = run_contextual_comparison(
            spec,
            case.input,
            policy_repository=policy_repo,
            corpus_version="hr/v1",
            run_classification=PILOT_DEVELOPMENT,
        )
        comparison = evaluate_contextual_comparison(spec, execution_a, execution_b)
        assert comparison.permission_changed, (
            f"{spec.name} was declared as a dimension that changes permission, "
            f"but action_a={comparison.action_a!r} allowed_a={comparison.allowed_actions_a!r} "
            f"== action_b={comparison.action_b!r} allowed_b={comparison.allowed_actions_b!r}"
        )


def test_every_declared_contextual_comparison_holds_every_other_field_constant():
    """The only field that may differ between the two ``GovernanceContext``
    objects actually built for each spec is the one dimension it names --
    ``text``/``task`` must also be identical (the case's own, unchanged).
    """
    cases = _cases()

    for spec in CONTEXTUAL_MATRIX_SPECS:
        case = cases[spec.base_sample_id]
        request_a = build_request(case.input, context_overrides=spec.context_a)
        request_b = build_request(case.input, context_overrides=spec.context_b)

        assert request_a.text == request_b.text
        assert request_a.task == request_b.task

        context_a = request_a.context.model_dump()
        context_b = request_b.context.model_dump()
        differing_fields = {field for field in context_a if context_a[field] != context_b[field]}
        # The dimension itself always differs (that is the point of the
        # spec); policy_version-dimension specs also, necessarily, vary
        # policy_version -- but never anything else.
        allowed_diff = {spec.dimension}
        if spec.dimension != "policy_version" and "policy_version" in spec.context_a:
            pass  # policy_version pinned identically on both sides already
        assert differing_fields <= allowed_diff, (
            f"{spec.name} was supposed to hold every field but {spec.dimension!r} "
            f"constant; also differs on {differing_fields - allowed_diff}"
        )


def test_a_dimension_with_no_documented_effect_under_hr_v1_is_correctly_reported_as_unchanged():
    """Negative control: requester_role has *no* effect on employee_name's
    resolved action under hr-v1 (docs/hr-policy-matrix.md's own inventory,
    also pinned directly against PolicyRepository in
    tests/test_hr_policy_matrix.py). Exercised here through the same
    contextual-comparison machinery, to prove it does not spuriously flag a
    "permission changed" result when the frozen policy genuinely has none.
    """
    from dataclasses import replace

    cases = _cases()
    policy_repo = _policy_repo()
    inert_spec = replace(
        CONTEXTUAL_MATRIX_SPECS[0],
        name="requester_role_employee_name_hr_v1_inert",
        dimension="requester_role",
        base_sample_id="hr_team_summary_001",
        category="employee_name",
        context_a={
            "requester_role": "hr_viewer",
            "policy_version": "hr-v1",
            "request_id": "inert-spec-req-1",
        },
        context_b={
            "requester_role": "hr_analyst",
            "policy_version": "hr-v1",
            "request_id": "inert-spec-req-1",
        },
    )
    case = cases[inert_spec.base_sample_id]
    execution_a, execution_b = run_contextual_comparison(
        inert_spec,
        case.input,
        policy_repository=policy_repo,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
    )
    comparison = evaluate_contextual_comparison(inert_spec, execution_a, execution_b)
    assert comparison.permission_changed is False
    assert comparison.action_a == comparison.action_b
