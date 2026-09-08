"""Development entrypoint for T10 / issue #8's first B0-B4 pilot over the
frozen ``corpus/hr/v1`` corpus.

Runs every case through every treatment with ``FakeProvider``, scores the
result against each case's oracle, evaluates the B4 contextual-matrix
comparisons (``docs/hr-policy-matrix.md``), and writes machine-readable
artifacts under ``artifacts/experiments/hr/v1/<experiment_run_id>/`` -- a
fresh directory per run, never overwriting a previous run's results.

This is a dev/reporting script, exactly like
``scripts/report_b3_corpus_divergence.py`` -- it lives outside ``src/`` and
is not production code. It is not the T20 CLI (out of scope for T10).

Usage::

    python scripts/run_hr_v1_pilot.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

from adaptive_disclosure_gateway.experiments.artifacts import (
    ARTIFACT_FORMAT_VERSION,
    write_pilot_artifacts,
)
from adaptive_disclosure_gateway.experiments.contextual_matrix import (
    CONTEXTUAL_MATRIX_SPECS,
    CONTEXTUAL_MATRIX_VERSION,
    evaluate_contextual_comparison,
    run_contextual_comparison,
)
from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.run_identity import (
    B3_TASK_AWARE_BASELINE_COMMIT,
    B4_POLICY_GOVERNED_COMMIT,
    PILOT_DEVELOPMENT,
    SCHEMA_VERSION,
    new_experiment_run_id,
)
from adaptive_disclosure_gateway.experiments.runner import ALL_TREATMENTS, run_pilot
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import FakeProvider

REPO_ROOT = Path(__file__).parents[1]
CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = REPO_ROOT / "configs" / "policies"
OUTPUT_ROOT = REPO_ROOT / "artifacts" / "experiments" / "hr" / "v1"
CORPUS_VERSION = "hr/v1"


def _policy_versions_available(policy_dir: Path) -> list[str]:
    """Every policy version's own declared ``version:`` field, read directly
    from the frozen YAML documents in ``policy_dir`` -- never through
    ``PolicyRepository``'s private ``_policies`` mapping, which is
    production-internal state this dev script has no business reaching into.
    """
    versions = []
    for path in sorted(policy_dir.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        versions.append(document["version"])
    return sorted(versions)


def _reproducibility_manifest(*, results, policy_dir: Path) -> dict[str, object]:
    """Everything ``artifacts.write_pilot_artifacts`` needs to make this
    pilot run reproducible (PR #35 review, blocker 5) -- never raw task
    text, a sensitive value, ``requester_id`` or vault content.
    """
    policy_versions_used = sorted(
        {
            result.identity.policy_version
            for treatment_results in results.values()
            for result in treatment_results
            if result.identity.policy_version is not None
        }
    )
    fake_provider = FakeProvider()

    return {
        "b3_treatment_version": B3_TASK_AWARE_BASELINE_COMMIT,
        "b4_treatment_version": B4_POLICY_GOVERNED_COMMIT,
        "b4_task_aware_baseline_version": B3_TASK_AWARE_BASELINE_COMMIT,
        "policy_versions_available": _policy_versions_available(policy_dir),
        "policy_versions_used": policy_versions_used,
        "b4_contextual_matrix_versions": ["hr-v2", "hr-v3"],
        "provider_name": type(fake_provider).__name__,
        "provider_model_id": fake_provider.model_id,
        "provider_model_snapshot": fake_provider.model_snapshot,
        "decoding_config": dict(fake_provider.decoding_config),
        # FakeProvider has no separately configurable provider-class
        # behavior beyond mirroring whatever provider_class the case under
        # test declares (see experiments/execution.py's docstring) -- there
        # is no additional config to name here.
        "provider_class_behavior_config": "not_applicable",
        "treatment_chain": [t.value for t in ALL_TREATMENTS],
        "contextual_comparison_matrix_version": CONTEXTUAL_MATRIX_VERSION,
        "contextual_comparison_specs": [spec.name for spec in CONTEXTUAL_MATRIX_SPECS],
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def main() -> None:
    experiment_run_id = new_experiment_run_id()

    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
        experiment_run_id=experiment_run_id,
    )

    cases_by_id = {case.input.sample_id: case for case in load_hr_v1_cases(CORPUS_DIR)}
    policy_repository = PolicyRepository.from_directory(POLICY_DIR)
    contextual_results = []
    for spec in CONTEXTUAL_MATRIX_SPECS:
        case = cases_by_id[spec.base_sample_id]
        execution_a, execution_b = run_contextual_comparison(
            spec,
            case.input,
            policy_repository=policy_repository,
            corpus_version=CORPUS_VERSION,
            run_classification=PILOT_DEVELOPMENT,
        )
        contextual_results.append(evaluate_contextual_comparison(spec, execution_a, execution_b))

    reproducibility = _reproducibility_manifest(results=results, policy_dir=POLICY_DIR)

    run_dir = write_pilot_artifacts(
        output_root=OUTPUT_ROOT,
        experiment_run_id=experiment_run_id,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
        results_by_treatment=results,
        contextual_results=contextual_results,
        reproducibility=reproducibility,
    )

    print(f"Pilot artifacts written to {run_dir}")
    for treatment, treatment_results in results.items():
        print(f"  {treatment.value}: {len(treatment_results)} cases")
    print(f"  contextual matrix comparisons: {len(contextual_results)}")


if __name__ == "__main__":
    main()
