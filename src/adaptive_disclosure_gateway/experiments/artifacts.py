"""Artifact serialization for T10's pilot (issue #8): JSON/JSONL results,
aggregated summaries and a run manifest, written to a fresh,
experiment-run-id-named subdirectory so a new run never silently overwrites
a previous one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from adaptive_disclosure_gateway.domain import Treatment

from .aggregation import summarize_b3_to_b4, summarize_pairwise, summarize_treatment
from .case_result import CaseResult, to_safe_dict
from .contextual_matrix import ContextualComparisonResult
from .post_pilot_protocol import CURRENT_PROTOCOL_ID
from .run_identity import SCHEMA_VERSION, RunClassification


class MixedProtocolIdsError(ValueError):
    """Raised when the ``CaseResult`` rows passed to
    ``write_pilot_artifacts`` do not all share one ``RunIdentity.protocol_id``
    (Issue #87 / M3) -- one pilot artifact bundle names exactly one protocol
    id in its manifest, so a mixture would make that field misleading rather
    than merely imprecise.
    """


_PAIRWISE_SEQUENCE: tuple[tuple[Treatment, Treatment], ...] = (
    (Treatment.DIRECT, Treatment.STATIC_SANITIZATION),
    (Treatment.STATIC_SANITIZATION, Treatment.REVERSIBLE_PSEUDONYMIZATION),
    (Treatment.REVERSIBLE_PSEUDONYMIZATION, Treatment.TASK_AWARE),
    (Treatment.TASK_AWARE, Treatment.POLICY_GOVERNED),
)

# Bumped alongside SCHEMA_VERSION for PR #35 review's blockers: the manifest
# gained a "reproducibility" section (blocker 5), summary/contextual-matrix
# artifacts are now wrapped with the shared experiment_run_id (blocker 5),
# and results.jsonl entries gained detector/resource_metrics fields
# (blockers 2, 3). This versions the artifact *bundle* (directory layout and
# file set) independently of SCHEMA_VERSION, which versions one CaseResult's
# own serialized shape.
ARTIFACT_FORMAT_VERSION = "t10-pilot-artifact-bundle-v2"


def write_pilot_artifacts(
    *,
    output_root: Path,
    experiment_run_id: str,
    corpus_version: str,
    run_classification: RunClassification,
    results_by_treatment: dict[Treatment, list[CaseResult]],
    contextual_results: list[ContextualComparisonResult] | None = None,
    reproducibility: Mapping[str, Any] | None = None,
) -> Path:
    """Write one pilot run's artifacts under ``output_root/<experiment_run_id>/``.

    Refuses to write into an existing run directory (``FileExistsError``) --
    a new run must never silently clobber a previous one's results.

    ``experiment_run_id`` (PR #35 review, blocker 5) is written into every
    artifact this function produces -- the manifest, both summary files, the
    B3->B4 summary and the contextual-matrix file -- so every artifact from
    one pilot invocation can be unambiguously tied back to the same run.
    Each ``CaseResult`` in ``results_by_treatment`` is expected to already
    carry this same id in its own ``metadata.experiment_run_id`` (set by
    ``runner.run_pilot``/``run_case_for_treatment``); this function does not
    check that itself (no per-result validation here), but a caller building
    the manifest and the results from the same ``run_pilot(experiment_run_id=...)``
    call gets that consistency by construction -- see
    ``tests/test_experiments_artifacts.py``.

    ``reproducibility`` is an optional, free-form mapping of additional
    reproducibility metadata (frozen treatment implementation commits,
    policy versions, provider identity/decoding config, contextual-matrix
    spec names, ...) merged into the manifest's own ``"reproducibility"``
    key verbatim -- never invented here, and never containing raw task
    text, a sensitive value, ``requester_id`` or vault content (the caller's
    responsibility; see ``scripts/run_hr_v1_pilot.py`` for the pilot's own
    values). Left ``None``, the manifest's ``"reproducibility"`` key is an
    empty mapping.
    """
    run_dir = output_root / experiment_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    all_results: list[CaseResult] = [
        result
        for treatment_results in results_by_treatment.values()
        for result in treatment_results
    ]

    # Issue #87 / M3: the manifest's protocol_id is derived from the rows
    # actually produced, not independently resolved from CURRENT_PROTOCOL_ID
    # -- a run explicitly scored under an older, still-scorable id (e.g.
    # protocol_id="post-pilot-v3" for a historical corpus) must have its
    # manifest agree with what its own rows carry, never silently claim
    # whatever happens to be current. Mixed ids across rows would make this
    # field actively misleading, so that raises rather than picking one
    # arbitrarily. No rows at all (an empty results_by_treatment) falls back
    # to CURRENT_PROTOCOL_ID -- there is nothing to derive it from.
    row_protocol_ids = {result.identity.protocol_id for result in all_results}
    if len(row_protocol_ids) > 1:
        raise MixedProtocolIdsError(
            "write_pilot_artifacts received CaseResult rows with more than one "
            "distinct RunIdentity.protocol_id"
        )
    manifest_protocol_id = next(iter(row_protocol_ids), CURRENT_PROTOCOL_ID)

    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for result in all_results:
            handle.write(json.dumps(to_safe_dict(result), sort_keys=True))
            handle.write("\n")

    per_treatment_summary = {
        "experiment_run_id": experiment_run_id,
        "treatments": {
            treatment.value: asdict(summarize_treatment(results))
            for treatment, results in results_by_treatment.items()
        },
    }
    (run_dir / "summary_by_treatment.json").write_text(
        json.dumps(per_treatment_summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    pairwise_summaries: dict[str, Any] = {}
    for from_treatment, to_treatment in _PAIRWISE_SEQUENCE:
        from_results = results_by_treatment.get(from_treatment)
        to_results = results_by_treatment.get(to_treatment)
        if from_results is None or to_results is None:
            continue
        key = f"{from_treatment.value}_to_{to_treatment.value}"
        pairwise_summaries[key] = asdict(summarize_pairwise(from_results, to_results))
    (run_dir / "summary_pairwise.json").write_text(
        json.dumps(
            {"experiment_run_id": experiment_run_id, "pairwise": pairwise_summaries},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
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
            json.dumps(
                {"experiment_run_id": experiment_run_id, "b3_to_b4": asdict(b3_to_b4)},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    if contextual_results:
        (run_dir / "contextual_matrix.json").write_text(
            json.dumps(
                {
                    "experiment_run_id": experiment_run_id,
                    "comparisons": [asdict(r) for r in contextual_results],
                },
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

    manifest = {
        "experiment_run_id": experiment_run_id,
        "schema_version": SCHEMA_VERSION,
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        # Top-level, alongside schema_version -- never only nested inside the
        # free-form reproducibility mapping -- so it is always present and
        # always agrees with what every row's own RunIdentity.protocol_id
        # actually carries (M3 Gate 6 / issue #38; derivation from the rows
        # themselves added by Issue #87 / M3).
        "protocol_id": manifest_protocol_id,
        "corpus_version": corpus_version,
        "run_classification": run_classification,
        "treatments": sorted(t.value for t in results_by_treatment),
        "case_counts": {t.value: len(r) for t, r in results_by_treatment.items()},
        "reproducibility": dict(reproducibility) if reproducibility is not None else {},
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    return run_dir
