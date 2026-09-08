"""Artifact serialization for T10's pilot (issue #8): JSON/JSONL results,
aggregated summaries and a run manifest, written to a fresh, run-id-named
subdirectory so a new run never silently overwrites a previous one.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from adaptive_disclosure_gateway.domain import Treatment

from .aggregation import summarize_b3_to_b4, summarize_pairwise, summarize_treatment
from .case_result import CaseResult, to_safe_dict
from .contextual_matrix import ContextualComparisonResult
from .run_identity import SCHEMA_VERSION, RunClassification

_PAIRWISE_SEQUENCE: tuple[tuple[Treatment, Treatment], ...] = (
    (Treatment.DIRECT, Treatment.STATIC_SANITIZATION),
    (Treatment.STATIC_SANITIZATION, Treatment.REVERSIBLE_PSEUDONYMIZATION),
    (Treatment.REVERSIBLE_PSEUDONYMIZATION, Treatment.TASK_AWARE),
    (Treatment.TASK_AWARE, Treatment.POLICY_GOVERNED),
)


def write_pilot_artifacts(
    *,
    output_root: Path,
    run_id: str,
    corpus_version: str,
    run_classification: RunClassification,
    results_by_treatment: dict[Treatment, list[CaseResult]],
    contextual_results: list[ContextualComparisonResult] | None = None,
) -> Path:
    """Write one pilot run's artifacts under ``output_root/<run_id>/``.

    Refuses to write into an existing run directory (``FileExistsError``) --
    a new run must never silently clobber a previous one's results.
    """
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    all_results: list[CaseResult] = [
        result
        for treatment_results in results_by_treatment.values()
        for result in treatment_results
    ]

    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for result in all_results:
            handle.write(json.dumps(to_safe_dict(result), sort_keys=True))
            handle.write("\n")

    per_treatment_summary = {
        treatment.value: asdict(summarize_treatment(results))
        for treatment, results in results_by_treatment.items()
    }
    (run_dir / "summary_by_treatment.json").write_text(
        json.dumps(per_treatment_summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    pairwise_summaries = {}
    for from_treatment, to_treatment in _PAIRWISE_SEQUENCE:
        from_results = results_by_treatment.get(from_treatment)
        to_results = results_by_treatment.get(to_treatment)
        if from_results is None or to_results is None:
            continue
        key = f"{from_treatment.value}_to_{to_treatment.value}"
        pairwise_summaries[key] = asdict(summarize_pairwise(from_results, to_results))
    (run_dir / "summary_pairwise.json").write_text(
        json.dumps(pairwise_summaries, indent=2, sort_keys=True), encoding="utf-8"
    )

    if (
        Treatment.TASK_AWARE in results_by_treatment
        and Treatment.POLICY_GOVERNED in results_by_treatment
    ):
        b3_to_b4 = summarize_b3_to_b4(
            results_by_treatment[Treatment.TASK_AWARE],
            results_by_treatment[Treatment.POLICY_GOVERNED],
        )
        (run_dir / "summary_b3_to_b4.json").write_text(
            json.dumps(asdict(b3_to_b4), indent=2, sort_keys=True), encoding="utf-8"
        )

    if contextual_results:
        (run_dir / "contextual_matrix.json").write_text(
            json.dumps(
                [asdict(r) for r in contextual_results], indent=2, sort_keys=True, default=str
            ),
            encoding="utf-8",
        )

    manifest = {
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "corpus_version": corpus_version,
        "run_classification": run_classification,
        "treatments": sorted(t.value for t in results_by_treatment),
        "case_counts": {t.value: len(r) for t, r in results_by_treatment.items()},
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    return run_dir
