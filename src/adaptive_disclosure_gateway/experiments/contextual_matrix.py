"""B3->B4 contextual comparisons (T10 / issue #8), scoped to exactly the
cells ``docs/hr-policy-matrix.md`` documents as actually changing the
resolved policy permission -- never a cartesian product over every
dimension combination.

Each ``ContextualComparisonSpec`` names one base corpus case and one
category, and varies exactly one ``GovernanceContext`` dimension between two
values while holding every other context field at the base case's own
value (``experiments.corpus_source.build_request``'s ``context_overrides``,
the same ``GovernanceContext.model_copy(update=...)`` technique
``tests/test_hr_policy_matrix.py`` already uses directly against
``PolicyRepository``, applied here at the request-construction boundary so
the full B4 treatment -- not just the policy engine in isolation -- is
exercised). This never edits the frozen corpus or policy documents; it only
parameterizes the request built from an existing case's own text/task.

The four specs below correspond 1:1 to the four rows of
``docs/hr-policy-matrix.md``'s "Which cells change the action space" table:
``purpose`` (salary), ``requester_role`` (salary and department),
``provider_class`` (employee_name), and ``policy_version`` (hr-v2 vs hr-v3,
``compensation_review``).
"""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.domain import DisclosureAction, Treatment
from adaptive_disclosure_gateway.policies import PolicyRepository

from .execution import CaseExecution, execute_case
from .run_identity import RunClassification


@dataclass(frozen=True)
class ContextualComparisonSpec:
    name: str
    dimension: str
    base_sample_id: str
    category: str
    context_a: dict[str, str]
    context_b: dict[str, str]


# Held constant across every spec below, on *both* sides of every
# comparison: a request-scope-capable lifecycle identifier. Without this,
# varying `requester_role` to `hr_viewer` (whose hr-v2/hr-v3 pseudonym-scope
# ceiling is REQUEST -- see docs/hr-policy-matrix.md) can make an unrelated
# category (e.g. `employee_name`, default PSEUDONYMIZE under hr-v2) fail
# closed for a missing `request_id` *before* the category this spec is
# actually studying ever gets sliced -- confounding the comparison with a
# scope-identifier artifact instead of isolating the intended dimension.
# Supplying it identically on both sides removes that confound without
# giving either side a different lifecycle scope than the other.
_LIFECYCLE_IDENTIFIERS = {"request_id": "ctxmatrix-req-1", "document_id": "ctxmatrix-doc-1"}


def _ctx(**overrides: str) -> dict[str, str]:
    return {**_LIFECYCLE_IDENTIFIERS, **overrides}


CONTEXTUAL_MATRIX_SPECS: tuple[ContextualComparisonSpec, ...] = (
    ContextualComparisonSpec(
        name="purpose_salary",
        dimension="purpose",
        base_sample_id="hr_salary_analysis_001",
        category="salary",
        context_a=_ctx(purpose="team_summary", policy_version="hr-v2"),
        context_b=_ctx(purpose="salary_analysis", policy_version="hr-v2"),
    ),
    ContextualComparisonSpec(
        name="requester_role_salary",
        dimension="requester_role",
        base_sample_id="hr_salary_analysis_001",
        category="salary",
        context_a=_ctx(
            requester_role="hr_viewer", purpose="salary_analysis", policy_version="hr-v2"
        ),
        context_b=_ctx(
            requester_role="hr_analyst", purpose="salary_analysis", policy_version="hr-v2"
        ),
    ),
    ContextualComparisonSpec(
        name="requester_role_department",
        dimension="requester_role",
        base_sample_id="hr_department_aggregation_001",
        category="department",
        context_a=_ctx(requester_role="hr_viewer", policy_version="hr-v2"),
        context_b=_ctx(requester_role="hr_analyst", policy_version="hr-v2"),
    ),
    ContextualComparisonSpec(
        name="provider_class_employee_name",
        dimension="provider_class",
        base_sample_id="hr_team_summary_001",
        category="employee_name",
        context_a=_ctx(provider_class="internal_llm", policy_version="hr-v2"),
        context_b=_ctx(provider_class="external_llm", policy_version="hr-v2"),
    ),
    ContextualComparisonSpec(
        name="policy_version_compensation_review",
        dimension="policy_version",
        base_sample_id="hr_salary_analysis_002",
        category="salary",
        context_a=_ctx(policy_version="hr-v2"),
        context_b=_ctx(policy_version="hr-v3"),
    ),
)


@dataclass(frozen=True)
class ContextualComparisonResult:
    spec: ContextualComparisonSpec
    action_a: DisclosureAction | None
    action_b: DisclosureAction | None
    allowed_actions_a: tuple[DisclosureAction, ...]
    allowed_actions_b: tuple[DisclosureAction, ...]
    permission_changed: bool


def run_contextual_comparison(
    spec: ContextualComparisonSpec,
    case_input: CorpusCaseInput,
    *,
    policy_repository: PolicyRepository,
    corpus_version: str,
    run_classification: RunClassification,
) -> tuple[CaseExecution, CaseExecution]:
    """Run B4 -- Policy-governed twice over the *same* case text/task, once
    per side of ``spec``, varying only the one context dimension the spec
    names.
    """
    execution_a = execute_case(
        case_input=case_input,
        treatment=Treatment.POLICY_GOVERNED,
        corpus_version=corpus_version,
        run_classification=run_classification,
        policy_repository=policy_repository,
        context_overrides=spec.context_a,
    )
    execution_b = execute_case(
        case_input=case_input,
        treatment=Treatment.POLICY_GOVERNED,
        corpus_version=corpus_version,
        run_classification=run_classification,
        policy_repository=policy_repository,
        context_overrides=spec.context_b,
    )
    return execution_a, execution_b


def evaluate_contextual_comparison(
    spec: ContextualComparisonSpec, execution_a: CaseExecution, execution_b: CaseExecution
) -> ContextualComparisonResult:
    """Whether ``spec.category``'s resolved action/allowed-action-space
    genuinely differs between the two sides -- the identifiability guarantee
    ``docs/hr-policy-matrix.md`` documents per dimension.
    """
    decisions_a = {d.category: d for d in execution_a.execution.disclosure_result.decisions}
    decisions_b = {d.category: d for d in execution_b.execution.disclosure_result.decisions}
    decision_a = decisions_a.get(spec.category)
    decision_b = decisions_b.get(spec.category)

    action_a = decision_a.action if decision_a is not None else None
    action_b = decision_b.action if decision_b is not None else None
    allowed_a = tuple(decision_a.allowed_actions) if decision_a is not None else ()
    allowed_b = tuple(decision_b.allowed_actions) if decision_b is not None else ()

    return ContextualComparisonResult(
        spec=spec,
        action_a=action_a,
        action_b=action_b,
        allowed_actions_a=allowed_a,
        allowed_actions_b=allowed_b,
        permission_changed=(action_a != action_b) or (allowed_a != allowed_b),
    )
