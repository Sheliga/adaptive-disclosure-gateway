"""Development entrypoint for T24 / issue #37's B0-B4 run over the frozen
``corpus/contracts/v1`` second-domain corpus.

Mirrors ``scripts/run_hr_v1_pilot.py`` deliberately: same runner, same
scoring, same artifact writer, same manifest mechanism. The only Contracts
differences are the corpus directory, the corpus version string, the
provenance fields this run records, and the absence of a contextual-matrix
stage (``experiments/contextual_matrix.py``'s specs name HR sample ids and
the ``hr-v2``/``hr-v3`` policy pair; ``contracts-v1`` is the only Contracts
policy version, so there is no second version to compare against and nothing
Contracts-shaped for those specs to run on).

**Run classification: ``pilot_development``.** This was decided by the
project owner before this corpus existed and before any B0-B4 Contracts
result had been produced or inspected -- it is not a reaction to what the
results look like. Concretely, that means: this run is NOT confirmatory
evidence, and a held-out confirmatory Contracts run remains a separate future
step. The corpus and its oracle are nonetheless frozen and versioned exactly
as ``corpus/hr/v1`` is (see ``corpus/contracts/v1/README.md``'s freeze rule),
so that future run has a fixed artifact to be held out *from*.

**Provider scope.** Everything here runs against ``FakeProvider``. Per T22 /
Issue #30 -- open and parallel -- no output of this script supports a claim
about real LLM utility, real token counts, real cost or real provider
behaviour.

This is a dev/reporting script, exactly like ``scripts/run_hr_v1_pilot.py``:
it lives outside ``src/`` and is not production code.

Usage::

    .venv/Scripts/python.exe scripts/run_contracts_v1_pilot.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

from adaptive_disclosure_gateway.corpus.models import CORPUS_SCHEMA_VERSION
from adaptive_disclosure_gateway.experiments.artifacts import (
    ARTIFACT_FORMAT_VERSION,
    write_pilot_artifacts,
)
from adaptive_disclosure_gateway.experiments.post_pilot_protocol import (
    CURRENT_PROTOCOL_ID,
    validate_protocol_id,
)
from adaptive_disclosure_gateway.experiments.run_identity import (
    B3_TASK_AWARE_BASELINE_COMMIT,
    B4_POLICY_GOVERNED_COMMIT,
    PILOT_DEVELOPMENT,
    SCHEMA_VERSION,
    new_experiment_run_id,
)
from adaptive_disclosure_gateway.experiments.runner import ALL_TREATMENTS, run_pilot
from adaptive_disclosure_gateway.providers import FakeProvider

REPO_ROOT = Path(__file__).parents[1]
CORPUS_DIR = REPO_ROOT / "corpus" / "contracts" / "v1" / "cases"
POLICY_DIR = REPO_ROOT / "configs" / "policies"
OUTPUT_ROOT = REPO_ROOT / "artifacts" / "experiments" / "contracts" / "v1"
CORPUS_VERSION = "contracts/v1"

# The oracle lives inside the same versioned corpus directory as the input and
# is versioned one-to-one with it, so `oracle_version` equals `corpus_version`
# today (post-pilot-v1 §13.2). Recorded explicitly rather than left implicit:
# the moment an oracle revision is ever issued without touching `input.text`,
# these two must be able to diverge.
ORACLE_VERSION = "contracts/v1"

# Issue #56 / PR #59's merge commit: the point at which the Contracts
# categories, detector rules, policy actions, B3 action spaces, generalization
# strategies and relation semantics were frozen. This corpus was authored
# against that freeze and must not have moved it.
CONTRACTS_DOMAIN_FREEZE_COMMIT = "5a67c30daab68d06bbd16d1cf06433de97245910"

# The `develop` commit corpus/contracts/v1 was authored on. The corpus's own
# freeze commit is the commit that merges T24 into `develop` -- recorded in
# corpus/contracts/v1/README.md once it exists, since a script cannot name a
# commit that has not been created yet.
CORPUS_FREEZE_BASE_COMMIT = "5a67c30daab68d06bbd16d1cf06433de97245910"
CORPUS_FREEZE_DATE = "2026-09-12"

# Every case in corpus/contracts/v1 is hand-authored plain text: no PDF, DOCX,
# XLSX or Markdown document is ingested, and T12's Docling/normalization path
# is not exercised by this corpus at all. There is therefore no parser stage
# whose provenance could be recorded, and post-pilot-v1 §13.2's
# `parser_ingestion_version` requirement -- which applies "once T12/Docling is
# in use" -- does not apply here. Recorded as an explicit, non-null
# "not applicable" rather than omitted, so a reader can tell the difference
# between "no parser was used" and "nobody wrote the field down". Inventing
# parser/ingestion identifiers for a stage that never ran would be fabricated
# provenance.
PARSER_INGESTION_VERSION = "not_applicable_plain_text_corpus"


def _policy_versions_available(policy_dir: Path) -> list[str]:
    """Every policy version's own declared ``version:`` field, read directly
    from the frozen YAML documents -- never through ``PolicyRepository``'s
    private state (the same rule ``scripts/run_hr_v1_pilot.py`` follows).
    """
    versions = []
    for path in sorted(policy_dir.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        versions.append(document["version"])
    return sorted(versions)


def _reproducibility_manifest(*, results, policy_dir: Path) -> dict[str, object]:
    """The Contracts v1 freeze record, carried in the manifest's existing
    free-form ``reproducibility`` mapping (``artifacts.write_pilot_artifacts``)
    -- the project's established provenance home, not a new mechanism.

    Never contains raw task text, a sensitive value, ``requester_id``, vault
    content, or a publicly reproducible hash of any of those: every value here
    is an identifier, version string, commit, date or classification label.
    """
    validate_protocol_id(CURRENT_PROTOCOL_ID)

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
        # --- corpus / oracle freeze ---
        "corpus_version": CORPUS_VERSION,
        "oracle_version": ORACLE_VERSION,
        "corpus_schema_version": CORPUS_SCHEMA_VERSION,
        "corpus_freeze_date": CORPUS_FREEZE_DATE,
        "corpus_freeze_base_commit": CORPUS_FREEZE_BASE_COMMIT,
        "contracts_domain_freeze_commit": CONTRACTS_DOMAIN_FREEZE_COMMIT,
        # --- protocol ---
        "protocol_id": CURRENT_PROTOCOL_ID,
        "parser_ingestion_version": PARSER_INGESTION_VERSION,
        # --- run classification, and the fact it was fixed in advance ---
        "run_classification": PILOT_DEVELOPMENT,
        "run_classification_decided_before_any_result_existed": True,
        "run_classification_note": (
            "Fixed by the project owner before corpus/contracts/v1 existed and "
            "before any B0-B4 Contracts result was produced or inspected. This "
            "run is not confirmatory evidence; a held-out confirmatory run "
            "remains a separate future step."
        ),
        # --- policy ---
        "policy_versions_available": _policy_versions_available(policy_dir),
        "policy_versions_used": policy_versions_used,
        "contextual_comparison_specs": [],
        "contextual_comparison_note": (
            "Not run: the contextual-matrix specs name HR sample ids and compare "
            "hr-v2 against hr-v3. contracts-v1 is the only Contracts policy "
            "version, so there is no second version to compare against."
        ),
        # --- treatment implementation provenance ---
        "b3_treatment_version": B3_TASK_AWARE_BASELINE_COMMIT,
        "b4_treatment_version": B4_POLICY_GOVERNED_COMMIT,
        "b4_task_aware_baseline_version": B3_TASK_AWARE_BASELINE_COMMIT,
        "treatment_chain": [t.value for t in ALL_TREATMENTS],
        # --- provider ---
        "provider_name": type(fake_provider).__name__,
        "provider_model_id": fake_provider.model_id,
        "provider_model_snapshot": fake_provider.model_snapshot,
        "decoding_config": dict(fake_provider.decoding_config),
        "provider_class_behavior_config": "not_applicable",
        "provider_scope_note": (
            "FakeProvider only. No claim about real LLM utility, token counts, "
            "cost or provider behaviour is supported by this run (T22 / Issue "
            "#30 is open and parallel)."
        ),
        # --- schema/artifact versions ---
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

    reproducibility = _reproducibility_manifest(results=results, policy_dir=POLICY_DIR)

    run_dir = write_pilot_artifacts(
        output_root=OUTPUT_ROOT,
        experiment_run_id=experiment_run_id,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
        results_by_treatment=results,
        reproducibility=reproducibility,
    )

    print(f"Contracts v1 artifacts written to {run_dir}")
    print(f"  run classification: {PILOT_DEVELOPMENT} (fixed in advance; not confirmatory)")
    for treatment, treatment_results in results.items():
        print(f"  {treatment.value}: {len(treatment_results)} cases")


if __name__ == "__main__":
    main()
