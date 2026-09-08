"""Scoring for T10's experiment runner (issue #8): everything that compares
a treatment's real execution output against a corpus case's ``CaseOracle``.

Scoring runs strictly *after* treatment execution and never feeds anything
back into it -- ``score_case`` below is the only entry point most callers
need, combining conformance, exposure, unnecessary disclosure, utility,
reconstruction and outcome classification into one ``CaseScore``.
"""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle

from ..execution import CaseExecution
from .conformance import ConformanceScore, SpanConformance, score_conformance
from .exposure import ExposureScore, SpanExposure, score_exposure
from .outcomes import CaseOutcomeFlags, classify_case_outcomes, classify_ordinary_utility_failure
from .reconstruction import CategoryReconstruction, ReconstructionScore, score_reconstruction
from .unnecessary_disclosure import UnnecessaryDisclosureScore, score_unnecessary_disclosure
from .utility import CategoryUtility, UtilityScore, score_utility

__all__ = [
    "CaseOutcomeFlags",
    "CaseScore",
    "CategoryReconstruction",
    "CategoryUtility",
    "ConformanceScore",
    "ExposureScore",
    "ReconstructionScore",
    "SpanConformance",
    "SpanExposure",
    "UnnecessaryDisclosureScore",
    "UtilityScore",
    "classify_case_outcomes",
    "classify_ordinary_utility_failure",
    "score_case",
    "score_conformance",
    "score_exposure",
    "score_reconstruction",
    "score_unnecessary_disclosure",
    "score_utility",
]


@dataclass(frozen=True)
class CaseScore:
    conformance: ConformanceScore
    exposure: ExposureScore
    unnecessary_disclosure: UnnecessaryDisclosureScore
    utility: UtilityScore
    reconstruction: ReconstructionScore
    outcomes: CaseOutcomeFlags
    ordinary_utility_failure: bool


def score_case(
    case_input: CorpusCaseInput, oracle: CaseOracle, case_execution: CaseExecution
) -> CaseScore:
    """Score one ``CaseExecution`` against ``oracle``. The only function in
    this package that combines every scorer; callers that need just one
    dimension may call the individual ``score_*`` functions directly.
    """
    result = case_execution.execution.disclosure_result
    treatment = case_execution.treatment

    conformance = score_conformance(oracle, result, treatment)
    exposure = score_exposure(oracle, result, treatment)
    unnecessary = score_unnecessary_disclosure(oracle, result, treatment)
    utility = score_utility(case_input, oracle, result, treatment)
    reconstruction = score_reconstruction(
        oracle, result, case_execution.payload_echo_reconstructed_text
    )
    outcomes = classify_case_outcomes(case_execution)
    ordinary_utility_failure = classify_ordinary_utility_failure(utility, outcomes)

    return CaseScore(
        conformance=conformance,
        exposure=exposure,
        unnecessary_disclosure=unnecessary,
        utility=utility,
        reconstruction=reconstruction,
        outcomes=outcomes,
        ordinary_utility_failure=ordinary_utility_failure,
    )
