"""PR #35 review, blocker 3: CPU-time and peak-memory measurement.

Covers:

- ``measure_resources`` returns non-negative CPU time and peak memory, with
  the caller-supplied ``measurement_scope`` recorded verbatim;
- it composes safely with an already-active ``tracemalloc`` trace (as
  pytest-cov or another tool might have started) without stopping it out
  from under the caller;
- ``execute_case`` populates ``CaseExecution.resource_metrics`` for both
  blocked and allowed cases, always serializable;
- the measurement never mixes into ``stage_timings``/``treatment_ms``;
- ``to_safe_dict``/``deterministic_key`` treat it exactly like the other
  wall-clock measurements: present in the safe dict, stripped from the
  deterministic key;
- per-treatment aggregation reports a mean CPU time/peak memory and a single
  ``resource_measurement_scope``.
"""

from __future__ import annotations

import json
import tracemalloc
from pathlib import Path

from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.experiments.aggregation import summarize_treatment
from adaptive_disclosure_gateway.experiments.case_result import deterministic_key, to_safe_dict
from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.resource_metrics import measure_resources
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.runner import run_case_for_treatment
from adaptive_disclosure_gateway.policies import PolicyRepository

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def _cases():
    return {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}


# --- measure_resources itself ------------------------------------------------


def test_measure_resources_reports_non_negative_values_and_the_given_scope():
    def _work():
        return sum(i * i for i in range(10_000))

    result, metrics = measure_resources("unit-test-scope", _work)

    assert result == sum(i * i for i in range(10_000))
    assert metrics.cpu_time_ms >= 0.0
    assert metrics.peak_memory_bytes >= 0
    assert metrics.measurement_scope == "unit-test-scope"


def test_measure_resources_never_stops_a_trace_it_did_not_start():
    tracemalloc.start()
    try:
        _, metrics = measure_resources("nested-scope", lambda: [0] * 1000)
        assert tracemalloc.is_tracing(), (
            "measure_resources must not stop a tracemalloc trace it did not start itself"
        )
        assert metrics.peak_memory_bytes >= 0
    finally:
        tracemalloc.stop()


def test_measure_resources_starts_and_stops_its_own_trace_when_none_was_active():
    assert not tracemalloc.is_tracing()
    measure_resources("standalone-scope", lambda: None)
    assert not tracemalloc.is_tracing(), (
        "measure_resources must leave tracemalloc stopped if it started it itself"
    )


# --- execute_case wiring: allowed and blocked cases -------------------------


def test_resource_metrics_present_and_non_negative_for_an_allowed_case():
    case = _cases()["hr_team_summary_001"]
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    assert execution.execution.disclosure_result.status == "allowed"
    assert execution.resource_metrics.cpu_time_ms >= 0.0
    assert execution.resource_metrics.peak_memory_bytes >= 0
    assert execution.resource_metrics.measurement_scope


def test_resource_metrics_present_and_non_negative_for_a_blocked_case():
    case = _cases()["hr_medical_block_001"]
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    assert execution.execution.disclosure_result.status == "blocked"
    assert execution.resource_metrics.cpu_time_ms >= 0.0
    assert execution.resource_metrics.peak_memory_bytes >= 0


def test_resource_measurement_scope_documents_it_covers_more_than_just_sanitize():
    case = _cases()["hr_team_summary_001"]
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    scope = execution.resource_metrics.measurement_scope
    assert "detection" in scope
    assert "treatment" in scope
    assert "provider" in scope


def test_resource_metrics_never_mixed_into_stage_timings():
    case = _cases()["hr_team_summary_001"]
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    stage_timing_fields = vars(execution.stage_timings).keys()
    assert "cpu_time_ms" not in stage_timing_fields
    assert "peak_memory_bytes" not in stage_timing_fields


# --- serialization: present in safe dict, stripped from deterministic key --


def test_resource_metrics_appear_in_the_safe_dict_and_are_serializable():
    case = _cases()["hr_team_summary_001"]
    result = run_case_for_treatment(
        case,
        Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
        experiment_run_id="test-experiment-run",
    )
    safe = to_safe_dict(result)
    assert "resource_metrics" in safe
    assert safe["resource_metrics"]["cpu_time_ms"] >= 0.0
    assert safe["resource_metrics"]["peak_memory_bytes"] >= 0
    json.dumps(safe)  # must not raise


def test_resource_metrics_excluded_from_deterministic_key():
    case = _cases()["hr_team_summary_001"]
    result = run_case_for_treatment(
        case,
        Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
        experiment_run_id="test-experiment-run",
    )
    key = deterministic_key(result)
    assert "resource_metrics" not in key


def test_resource_metrics_never_carry_sensitive_data():
    case = _cases()["hr_team_summary_001"]
    raw_values = {span.value for span in case.oracle.expected_spans}
    result = run_case_for_treatment(
        case,
        Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
        experiment_run_id="test-experiment-run",
    )
    serialized = json.dumps(to_safe_dict(result)["resource_metrics"])
    for value in raw_values:
        assert value not in serialized


# --- aggregation --------------------------------------------------------------


def test_treatment_summary_reports_mean_cpu_and_memory_and_a_single_scope():
    case = _cases()["hr_team_summary_001"]
    results = [
        run_case_for_treatment(
            case,
            Treatment.STATIC_SANITIZATION,
            corpus_version="hr/v1",
            run_classification=PILOT_DEVELOPMENT,
            policy_repository=_policy_repo(),
            experiment_run_id="test-experiment-run",
        )
        for _ in range(3)
    ]
    summary = summarize_treatment(results)
    assert summary.mean_cpu_time_ms is not None
    assert summary.mean_cpu_time_ms >= 0.0
    assert summary.mean_peak_memory_bytes is not None
    assert summary.mean_peak_memory_bytes >= 0.0
    assert (
        summary.resource_measurement_scope
        == results[0].case_execution.resource_metrics.measurement_scope
    )
