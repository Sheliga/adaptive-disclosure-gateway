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
from adaptive_disclosure_gateway.providers import Provider

from .case_result import CaseResult
from .corpus_source import load_hr_v1_cases
from .execution import execute_case
from .run_identity import (
    PILOT_DEVELOPMENT,
    RunClassification,
    new_experiment_run_id,
    new_run_metadata,
)
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
    experiment_run_id: str,
    provider: Provider | None = None,
) -> CaseResult:
    """Execute one case through one treatment (ground-truth-isolated --
    ``case.oracle`` is read only *after* ``execute_case`` returns, by
    ``score_case``) and return the combined, scored, serializable result.

    ``experiment_run_id`` (PR #35 review, blocker 5) must be the *same*
    value for every case/treatment call belonging to one pilot invocation --
    callers must generate it once (``run_identity.new_experiment_run_id``)
    and thread it through, never regenerate it per case or per treatment.

    ``provider`` (T22 / issue #30) is the one seam a controlled
    real-provider run needs: left ``None``, ``execute_case`` builds its usual
    deterministic ``FakeProvider``, which is what TDD, CI and every
    regression run get. Passing a real adapter here is the smallest possible
    integration point -- it changes which provider answers, and nothing about
    detection, the treatments, the policies or scoring. A caller doing that
    is responsible for the case contexts' ``provider_class`` matching what
    the adapter declares (``invoke_provider``'s pre-flight check refuses a
    mismatch rather than silently proceeding).
    """
    case_execution = execute_case(
        case_input=case.input,
        treatment=treatment,
        corpus_version=corpus_version,
        run_classification=run_classification,
        policy_repository=policy_repository,
        provider=provider,
    )
    score = score_case(case.input, case.oracle, case_execution)
    metadata = new_run_metadata(experiment_run_id)
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
    experiment_run_id: str | None = None,
    provider: Provider | None = None,
) -> dict[Treatment, list[CaseResult]]:
    """Run every case in ``corpus_dir`` through every treatment in
    ``treatments``, using the policy documents in ``policy_dir``. Each
    treatment gets its own list of ``CaseResult``, one per case, in corpus
    (file name) order.

    Every ``CaseResult`` this call produces shares one ``experiment_run_id``
    (PR #35 review, blocker 5) -- pass one explicitly to tie this pilot run
    to the same id used elsewhere (e.g. the contextual matrix comparisons
    and ``artifacts.write_pilot_artifacts``' manifest for the same
    invocation); left ``None``, a fresh one is generated for this call alone.

    ``provider`` (T22 / issue #30) is threaded verbatim into every case
    execution of this run, so one batch is answered by exactly one provider
    configuration -- the comparability requirement in
    ``docs/research/post-pilot-protocol-v1.md`` section 9.3. Left ``None``,
    every case uses the deterministic ``FakeProvider`` default, unchanged.
    """
    active_experiment_run_id = (
        experiment_run_id if experiment_run_id is not None else new_experiment_run_id()
    )
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
                    experiment_run_id=active_experiment_run_id,
                    provider=provider,
                )
            )
    return results
