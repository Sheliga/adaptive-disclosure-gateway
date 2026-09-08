"""Top-level pilot orchestration for T10 (issue #8).

Ties together corpus loading, treatment execution and scoring for every
case/treatment pair -- the only module callers (a dev script, a future
notebook, ``tests/``) need to run the whole B0-B4 pilot over one corpus
directory. Never invents statistics or writes artifacts itself -- see
``experiments/artifacts.py`` for serialization to disk, kept separate so
this module stays testable without touching the filesystem.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from adaptive_disclosure_gateway.corpus.loader import CorpusCase
from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.policies import PolicyRepository

from .case_result import CaseResult
from .corpus_source import load_hr_v1_cases
from .execution import execute_case
from .run_identity import PILOT_DEVELOPMENT, RunClassification, new_run_metadata
from .scoring import score_case

ALL_TREATMENTS: tuple[Treatment, ...] = (
    Treatment.DIRECT,
    Treatment.STATIC_SANITIZATION,
    Treatment.REVERSIBLE_PSEUDONYMIZATION,
    Treatment.TASK_AWARE,
    Treatment.POLICY_GOVERNED,
)


def run_case_for_treatment(
    case: CorpusCase,
    treatment: Treatment,
    *,
    corpus_version: str,
    run_classification: RunClassification,
    policy_repository: PolicyRepository,
) -> CaseResult:
    """Execute one case through one treatment (ground-truth-isolated --
    ``case.oracle`` is read only *after* ``execute_case`` returns, by
    ``score_case``) and return the combined, scored, serializable result.
    """
    case_execution = execute_case(
        case_input=case.input,
        treatment=treatment,
        corpus_version=corpus_version,
        run_classification=run_classification,
        policy_repository=policy_repository,
    )
    score = score_case(case.input, case.oracle, case_execution)
    metadata = new_run_metadata()
    return CaseResult(
        identity=case_execution.identity,
        metadata=metadata,
        score=score,
        case_execution=case_execution,
    )


def run_pilot(
    *,
    corpus_dir: Path,
    policy_dir: Path,
    corpus_version: str = "hr/v1",
    run_classification: RunClassification = PILOT_DEVELOPMENT,
    treatments: Iterable[Treatment] = ALL_TREATMENTS,
) -> dict[Treatment, list[CaseResult]]:
    """Run every case in ``corpus_dir`` through every treatment in
    ``treatments``, using the policy documents in ``policy_dir``. Each
    treatment gets its own list of ``CaseResult``, one per case, in corpus
    (file name) order.
    """
    cases = load_hr_v1_cases(corpus_dir)
    policy_repository = PolicyRepository.from_directory(policy_dir)

    results: dict[Treatment, list[CaseResult]] = {treatment: [] for treatment in treatments}
    for treatment in treatments:
        for case in cases:
            results[treatment].append(
                run_case_for_treatment(
                    case,
                    treatment,
                    corpus_version=corpus_version,
                    run_classification=run_classification,
                    policy_repository=policy_repository,
                )
            )
    return results
