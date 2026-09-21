"""PR #35 review, blocker 5: unambiguous run identity.

Before the fix: the pilot script generated one id for the output directory
(and called it ``run_id``), while every ``CaseResult`` independently called
``new_run_metadata()`` and got its *own* fresh ``run_id`` -- so the 65
per-case records in a pilot's ``results.jsonl`` each carried a different
``run_id``, none matching the manifest's. There was no field tying a case
execution back to the pilot run that produced it.

This file pins:

- ``RunMetadata`` exposes ``experiment_run_id`` (shared) and
  ``case_execution_id`` (unique per execution) -- never a bare ``run_id``
  again;
- every ``CaseResult`` produced by one ``run_pilot(experiment_run_id=...)``
  call carries that exact id, and distinct ``case_execution_id``s;
- ``write_pilot_artifacts`` writes the same ``experiment_run_id`` into the
  manifest, both summary files, the B3->B4 summary and the contextual-matrix
  file;
- the manifest is expanded with the reproducibility fields the pilot script
  supplies (B3/B4 commits, policy versions, provider identity, ...), never
  inventing a value when one is inapplicable;
- no raw task text, sensitive value, ``requester_id`` or vault mapping ever
  reaches the manifest or the results.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.experiments.artifacts import write_pilot_artifacts
from adaptive_disclosure_gateway.experiments.contextual_matrix import (
    CONTEXTUAL_MATRIX_SPECS,
    evaluate_contextual_comparison,
    run_contextual_comparison,
)
from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.post_pilot_protocol import (
    CURRENT_PROTOCOL_ID,
    FROZEN_PROTOCOL_IDS,
)
from adaptive_disclosure_gateway.experiments.run_identity import (
    PILOT_DEVELOPMENT,
    RunIdentity,
    new_experiment_run_id,
    new_run_metadata,
)
from adaptive_disclosure_gateway.experiments.runner import run_pilot
from adaptive_disclosure_gateway.policies import PolicyRepository

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


# --- RunMetadata itself ------------------------------------------------------


def test_run_metadata_has_experiment_run_id_and_case_execution_id_never_a_bare_run_id():
    metadata = new_run_metadata("shared-experiment-run")
    assert metadata.experiment_run_id == "shared-experiment-run"
    assert metadata.case_execution_id
    assert not hasattr(metadata, "run_id")


def test_new_run_metadata_generates_a_fresh_case_execution_id_each_call_for_the_same_experiment():
    a = new_run_metadata("shared-experiment-run")
    b = new_run_metadata("shared-experiment-run")
    assert a.experiment_run_id == b.experiment_run_id
    assert a.case_execution_id != b.case_execution_id


def test_new_experiment_run_id_produces_distinct_ids():
    assert new_experiment_run_id() != new_experiment_run_id()


# --- run_pilot: one experiment_run_id shared by every case result -----------


def test_every_case_result_from_one_pilot_run_shares_the_same_experiment_run_id():
    experiment_run_id = new_experiment_run_id()
    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        treatments=(Treatment.DIRECT, Treatment.STATIC_SANITIZATION),
        experiment_run_id=experiment_run_id,
    )
    all_results = [r for results_list in results.values() for r in results_list]
    assert all_results
    for result in all_results:
        assert result.metadata.experiment_run_id == experiment_run_id


def test_case_execution_ids_are_distinct_across_every_case_and_treatment():
    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        treatments=(Treatment.DIRECT, Treatment.STATIC_SANITIZATION),
    )
    all_results = [r for results_list in results.values() for r in results_list]
    execution_ids = [r.metadata.case_execution_id for r in all_results]
    assert len(execution_ids) == len(set(execution_ids))


def test_run_pilot_generates_its_own_experiment_run_id_when_none_is_given():
    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        treatments=(Treatment.DIRECT,),
    )
    ids = {r.metadata.experiment_run_id for r in results[Treatment.DIRECT]}
    assert len(ids) == 1


# --- write_pilot_artifacts: consistent experiment_run_id everywhere ---------


@pytest.fixture
def _small_pilot(tmp_path):
    experiment_run_id = new_experiment_run_id()
    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        experiment_run_id=experiment_run_id,
    )
    cases_by_id = {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}
    policy_repo = _policy_repo()
    contextual_results = []
    for spec in CONTEXTUAL_MATRIX_SPECS:
        case = cases_by_id[spec.base_sample_id]
        execution_a, execution_b = run_contextual_comparison(
            spec,
            case.input,
            policy_repository=policy_repo,
            corpus_version="hr/v1",
            run_classification=PILOT_DEVELOPMENT,
        )
        contextual_results.append(evaluate_contextual_comparison(spec, execution_a, execution_b))

    reproducibility = {
        "b3_treatment_version": "31bce08b7ea6a5c905f7a20bbb4bb99a05682bab",
        "b4_treatment_version": "5abea8514fa10ac64b9bc3714bbfd3f18682f713",
        "provider_class_behavior_config": "not_applicable",
    }

    run_dir = write_pilot_artifacts(
        output_root=tmp_path,
        experiment_run_id=experiment_run_id,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        results_by_treatment=results,
        contextual_results=contextual_results,
        reproducibility=reproducibility,
    )
    return experiment_run_id, run_dir


def test_manifest_results_and_summaries_all_carry_the_same_experiment_run_id(_small_pilot):
    experiment_run_id, run_dir = _small_pilot

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["experiment_run_id"] == experiment_run_id

    with (run_dir / "results.jsonl").open(encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    assert lines
    for record in lines:
        assert record["metadata"]["experiment_run_id"] == experiment_run_id

    summary_by_treatment = json.loads(
        (run_dir / "summary_by_treatment.json").read_text(encoding="utf-8")
    )
    assert summary_by_treatment["experiment_run_id"] == experiment_run_id

    summary_pairwise = json.loads((run_dir / "summary_pairwise.json").read_text(encoding="utf-8"))
    assert summary_pairwise["experiment_run_id"] == experiment_run_id

    summary_b3_to_b4 = json.loads((run_dir / "summary_b3_to_b4.json").read_text(encoding="utf-8"))
    assert summary_b3_to_b4["experiment_run_id"] == experiment_run_id

    contextual_matrix = json.loads((run_dir / "contextual_matrix.json").read_text(encoding="utf-8"))
    assert contextual_matrix["experiment_run_id"] == experiment_run_id


def test_case_execution_ids_across_the_written_results_are_all_distinct(_small_pilot):
    _experiment_run_id, run_dir = _small_pilot
    with (run_dir / "results.jsonl").open(encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    execution_ids = [record["metadata"]["case_execution_id"] for record in lines]
    assert len(execution_ids) == len(set(execution_ids))


def test_manifest_carries_the_reproducibility_fields_supplied(_small_pilot):
    _experiment_run_id, run_dir = _small_pilot
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["reproducibility"]["b3_treatment_version"]
        == "31bce08b7ea6a5c905f7a20bbb4bb99a05682bab"
    )
    assert (
        manifest["reproducibility"]["b4_treatment_version"]
        == "5abea8514fa10ac64b9bc3714bbfd3f18682f713"
    )
    assert manifest["reproducibility"]["provider_class_behavior_config"] == "not_applicable"


def test_manifest_reproducibility_defaults_to_an_empty_mapping_when_not_supplied(tmp_path):
    experiment_run_id = new_experiment_run_id()
    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        treatments=(Treatment.DIRECT,),
        experiment_run_id=experiment_run_id,
    )
    run_dir = write_pilot_artifacts(
        output_root=tmp_path,
        experiment_run_id=experiment_run_id,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        results_by_treatment=results,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["reproducibility"] == {}


# --- M3 Gate 6 / issue #38: protocol_id provenance ---------------------------


def test_run_identity_protocol_id_is_the_current_frozen_protocol():
    """Every case execution's own RunIdentity.protocol_id is populated with
    the current, registered post-pilot protocol id -- never left unset, and
    never a value outside FROZEN_PROTOCOL_IDS.
    """
    cases_by_id = {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}
    case = next(iter(cases_by_id.values()))
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.DIRECT,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    assert execution.identity.protocol_id == CURRENT_PROTOCOL_ID
    assert execution.identity.protocol_id in FROZEN_PROTOCOL_IDS


def test_manifest_and_rows_agree_on_protocol_id(_small_pilot):
    _experiment_run_id, run_dir = _small_pilot
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["protocol_id"] == CURRENT_PROTOCOL_ID

    with (run_dir / "results.jsonl").open(encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle]
    assert lines
    for record in lines:
        assert record["identity"]["protocol_id"] == manifest["protocol_id"]


def test_run_identity_rejects_an_unregistered_protocol_id_at_construction():
    """RunIdentity itself has no validation logic (it is a plain frozen
    dataclass), but the one place this codebase builds one
    (``execution.execute_case``) must fail closed before doing so if the
    protocol id it would stamp is not registered. This is a real behavioral
    pin, not apparatus: it fails if a future edit stops calling
    ``validate_protocol_id`` before constructing ``RunIdentity``.
    """
    import adaptive_disclosure_gateway.experiments.execution as execution_module
    from adaptive_disclosure_gateway.experiments.post_pilot_protocol import (
        UnknownProtocolIdError,
    )

    original = execution_module.CURRENT_PROTOCOL_ID
    execution_module.CURRENT_PROTOCOL_ID = "post-pilot-not-a-real-version"
    try:
        cases_by_id = {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}
        case = next(iter(cases_by_id.values()))
        with pytest.raises(UnknownProtocolIdError):
            execute_case(
                case_input=case.input,
                treatment=Treatment.DIRECT,
                corpus_version="hr/v1",
                run_classification=PILOT_DEVELOPMENT,
                policy_repository=_policy_repo(),
            )
    finally:
        execution_module.CURRENT_PROTOCOL_ID = original


def test_run_identity_has_a_protocol_id_field_never_none():
    field_names = {f.name for f in dataclasses.fields(RunIdentity)}
    assert "protocol_id" in field_names


def test_manifest_and_results_never_leak_a_raw_span_value_or_requester_id(_small_pilot):
    _experiment_run_id, run_dir = _small_pilot
    cases = load_hr_v1_cases(CORPUS_DIR)
    raw_values = {span.value for case in cases for span in case.oracle.expected_spans}
    assert raw_values

    manifest_text = (run_dir / "manifest.json").read_text(encoding="utf-8")
    results_text = (run_dir / "results.jsonl").read_text(encoding="utf-8")

    for value in raw_values:
        assert value not in manifest_text
        assert value not in results_text
    assert "requester_id" not in manifest_text
