"""Development entrypoint for T10 / issue #8's first B0-B4 pilot over the
frozen ``corpus/hr/v1`` corpus.

Runs every case through every treatment with ``FakeProvider``, scores the
result against each case's oracle, evaluates the B4 contextual-matrix
comparisons (``docs/hr-policy-matrix.md``), and writes machine-readable
artifacts under ``artifacts/experiments/hr/v1/<run_id>/`` -- a fresh
directory per run, never overwriting a previous run's results.

This is a dev/reporting script, exactly like
``scripts/report_b3_corpus_divergence.py`` -- it lives outside ``src/`` and
is not production code. It is not the T20 CLI (out of scope for T10).

Usage::

    python scripts/run_hr_v1_pilot.py
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.experiments.artifacts import write_pilot_artifacts
from adaptive_disclosure_gateway.experiments.contextual_matrix import (
    CONTEXTUAL_MATRIX_SPECS,
    evaluate_contextual_comparison,
    run_contextual_comparison,
)
from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT, new_run_metadata
from adaptive_disclosure_gateway.experiments.runner import run_pilot
from adaptive_disclosure_gateway.policies import PolicyRepository

REPO_ROOT = Path(__file__).parents[1]
CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = REPO_ROOT / "configs" / "policies"
OUTPUT_ROOT = REPO_ROOT / "artifacts" / "experiments" / "hr" / "v1"
CORPUS_VERSION = "hr/v1"


def main() -> None:
    run_id = new_run_metadata().run_id

    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
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

    run_dir = write_pilot_artifacts(
        output_root=OUTPUT_ROOT,
        run_id=run_id,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
        results_by_treatment=results,
        contextual_results=contextual_results,
    )

    print(f"Pilot artifacts written to {run_dir}")
    for treatment, treatment_results in results.items():
        print(f"  {treatment.value}: {len(treatment_results)} cases")
    print(f"  contextual matrix comparisons: {len(contextual_results)}")


if __name__ == "__main__":
    main()
