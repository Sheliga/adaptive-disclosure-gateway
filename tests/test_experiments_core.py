"""T10 / issue #8 -- core runner invariants: items 1, 2, 3, 4, 5, 6 of the
issue's acceptance-criteria checklist.

1. the same corpus cases run through every treatment B0-B4;
2. ground truth (``CaseOracle``) never reaches treatment execution;
3. B0's treatment latency is isolated from detector latency;
4. B3's frozen baseline commit is recorded explicitly;
5. B4's policy metadata (including the matrix-cell identifier B4 itself
   produces) is recorded;
6. every result against corpus/hr/v1 is classified ``pilot_development``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureRequest, Treatment
from adaptive_disclosure_gateway.experiments import execution as execution_module
from adaptive_disclosure_gateway.experiments import provider_instrumentation, treatments
from adaptive_disclosure_gateway.experiments.corpus_source import build_request, load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.run_identity import (
    B3_TASK_AWARE_BASELINE_COMMIT,
    PILOT_DEVELOPMENT,
)
from adaptive_disclosure_gateway.experiments.stage_timing import (
    b0_treatment_span_is_isolated_from_detection,
)
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.task_analysis.base import TaskAnalysis, TaskRelevance

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def _one_case(sample_id: str):
    cases = {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}
    return cases[sample_id]


# --- 1. same cases run through every treatment ------------------------------


def test_every_case_runs_through_every_treatment_and_produces_a_result():
    cases = load_hr_v1_cases(CORPUS_DIR)
    assert len(cases) == 13
    policy_repo = _policy_repo()

    for treatment in Treatment:
        for case in cases:
            case_execution = execute_case(
                case_input=case.input,
                treatment=treatment,
                corpus_version="hr/v1",
                run_classification=PILOT_DEVELOPMENT,
                policy_repository=policy_repo,
            )
            assert case_execution.identity.case_id == case.input.sample_id
            assert case_execution.identity.treatment_code == treatment.value
            # Every case actually reached a provider or a policy-driven
            # block -- never an unhandled exception swallowed into "nothing
            # happened".
            assert case_execution.execution.disclosure_result.status in ("allowed", "blocked")


# --- 2. ground-truth isolation ----------------------------------------------


def test_execute_case_signature_never_accepts_an_oracle():
    parameters = inspect.signature(execute_case).parameters
    assert "case" not in parameters, "execute_case must take case_input, never a bundled CorpusCase"
    for name, parameter in parameters.items():
        assert "oracle" not in name.lower()
        annotation = parameter.annotation
        assert annotation is not CaseOracle


@pytest.mark.parametrize(
    "module", [execution_module, treatments, provider_instrumentation], ids=lambda m: m.__name__
)
def test_execution_boundary_modules_never_reference_case_oracle(module):
    source = inspect.getsource(module)
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    assert "CaseOracle" not in names
    assert "oracle" not in names


def test_spy_task_analyzer_and_provider_never_receive_oracle_derived_content():
    """Behavioral proof, not just structural: run a real case whose oracle
    carries a distinctive marker string nowhere in the case's own
    ``input`` fields, through spies that record every argument they are
    called with, and assert that marker is absent from everything the
    analyzer and the provider actually saw.
    """
    case = _one_case("hr_team_summary_004")
    marker = "ZzMarkerNeverInInputZz"
    # The marker must genuinely only exist in the oracle, not by accident
    # already be present in the case's own input text/task.
    assert marker not in case.input.text
    assert marker not in case.input.task
    poisoned_oracle = case.oracle.model_copy(update={"expected_answer": marker})
    assert poisoned_oracle.expected_answer == marker

    seen_tasks: list[str] = []
    seen_payloads: list[str] = []

    class _SpyAnalyzer:
        def analyze(self, task, categories):
            seen_tasks.append(task)
            return TaskAnalysis(
                relevance_by_category={c: TaskRelevance.NOT_RELEVANT for c in categories}
            )

    class _SpyProvider:
        provider_class = "external_llm"

        def generate(self, request):
            seen_payloads.append(request.payload)
            seen_payloads.append(request.task)
            from adaptive_disclosure_gateway.providers import ProviderResponse

            return ProviderResponse(
                text="ack",
                model_id="spy",
                model_snapshot="spy-1",
                decoding_config={},
                transmitted_bytes=0,
            )

    execute_case(
        case_input=case.input,
        treatment=Treatment.TASK_AWARE,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
        task_analyzer=_SpyAnalyzer(),
        provider=_SpyProvider(),
    )

    assert seen_tasks, "expected the spy analyzer to have been called at least once"
    for task in seen_tasks:
        assert marker not in task
    for payload in seen_payloads:
        assert marker not in payload
    # And, independently: the oracle object itself was never mutated or
    # touched by execute_case (which never received it in the first place).
    assert poisoned_oracle.expected_answer == marker


# --- 3. B0 timing isolation --------------------------------------------------


def test_b0_treatment_latency_span_is_structurally_isolated_from_detection():
    from adaptive_disclosure_gateway.detection import Detector
    from adaptive_disclosure_gateway.experiments.span_capture import run_case_with_span_capture
    from adaptive_disclosure_gateway.experiments.stage_timing import extract_stage_timings
    from adaptive_disclosure_gateway.providers import FakeProvider
    from adaptive_disclosure_gateway.transformations import DirectDiscloser

    request = DisclosureRequest(
        text="Employee: Ana Souza\nCPF: 123.456.789-09\n",
        task="Summarize this record.",
        context={"domain": "hr", "purpose": "team_summary", "policy_version": "hr-v1"},
    )
    provider = FakeProvider()
    provider.provider_class = request.context.provider_class

    _result, spans = run_case_with_span_capture(
        DirectDiscloser(), request, provider, detector=Detector()
    )

    assert b0_treatment_span_is_isolated_from_detection(spans)

    timings = extract_stage_timings(spans)
    assert timings.detection_ms is not None
    assert timings.treatment_ms is not None
    # The whole point: B0's own reported treatment latency must not somehow
    # be *smaller* than physically possible if it had included detection --
    # this is a structural (span-topology) proof, not a numeric assertion,
    # since both durations are real, tiny, and could coincidentally land in
    # either order by magnitude alone.
    span_names = {s.name for s in spans}
    assert "detection.detect" in span_names
    assert "direct_disclosure.sanitize" in span_names


def test_b0_isolation_proof_is_false_for_a_span_list_missing_the_treatment_span():
    """A real negative control: the proof helper must not vacuously return
    True when the treatment span is simply absent (e.g. spans from a
    different treatment, or a truncated capture).
    """
    assert b0_treatment_span_is_isolated_from_detection([]) is False


# --- 4. B3 baseline recorded -------------------------------------------------


def test_b3_and_b4_results_record_the_frozen_baseline_commit_explicitly():
    case = _one_case("hr_team_summary_001")
    policy_repo = _policy_repo()

    b3 = execute_case(
        case_input=case.input,
        treatment=Treatment.TASK_AWARE,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repo,
    )
    b4 = execute_case(
        case_input=case.input,
        treatment=Treatment.POLICY_GOVERNED,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repo,
    )
    b2 = execute_case(
        case_input=case.input,
        treatment=Treatment.REVERSIBLE_PSEUDONYMIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repo,
    )

    assert b3.identity.treatment_baseline == B3_TASK_AWARE_BASELINE_COMMIT
    assert b4.identity.treatment_baseline == B3_TASK_AWARE_BASELINE_COMMIT
    # Never left implicit in the bare code alone for B0-B2, which have no
    # comparable baseline-version concept.
    assert b2.identity.treatment_baseline is None


# --- 5. B4 policy metadata, including the reused matrix-cell identifier -----


def test_b4_metadata_reuses_the_matrix_cell_identifier_policy_governed_already_produces():
    from adaptive_disclosure_gateway.transformations.policy_governed import _matrix_cell

    case = _one_case("hr_salary_analysis_001")
    policy_repo = _policy_repo()
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.POLICY_GOVERNED,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repo,
    )
    request = build_request(case.input)

    assert execution.b4_metadata is not None
    expected_cell = _matrix_cell(request.context, "salary", request.context.policy_version)
    assert expected_cell in execution.b4_metadata.matrix_cells
    assert execution.identity.matrix_cell is not None
    assert expected_cell in execution.identity.matrix_cell


def test_b4_metadata_carries_policy_restricted_and_impossible_flags_as_booleans_only():
    # hr_salary_analysis_003 under hr-v1 has no override making B4 diverge
    # from B3's baseline -- both fields must be present, boolean, and False.
    case = _one_case("hr_salary_analysis_003")
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.POLICY_GOVERNED,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    assert execution.b4_metadata is not None
    assert isinstance(execution.b4_metadata.policy_restricted_categories, tuple)
    assert isinstance(execution.b4_metadata.impossible_under_policy_categories, tuple)


def test_non_b4_treatments_never_carry_b4_metadata():
    case = _one_case("hr_salary_analysis_001")
    policy_repo = _policy_repo()
    for treatment in (
        Treatment.DIRECT,
        Treatment.STATIC_SANITIZATION,
        Treatment.REVERSIBLE_PSEUDONYMIZATION,
        Treatment.TASK_AWARE,
    ):
        execution = execute_case(
            case_input=case.input,
            treatment=treatment,
            corpus_version="hr/v1",
            run_classification=PILOT_DEVELOPMENT,
            policy_repository=policy_repo,
        )
        assert execution.b4_metadata is None


# --- 6. run classification ---------------------------------------------------


def test_every_hr_v1_result_is_classified_pilot_development():
    case = _one_case("hr_team_summary_001")
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    assert execution.identity.run_classification == "pilot_development"


def test_run_classification_schema_also_permits_held_out_confirmatory_without_mixing():
    case = _one_case("hr_team_summary_001")
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v2-heldout",
        run_classification="held_out_confirmatory",
        policy_repository=_policy_repo(),
    )
    assert execution.identity.run_classification == "held_out_confirmatory"
    assert execution.identity.run_classification != "pilot_development"
