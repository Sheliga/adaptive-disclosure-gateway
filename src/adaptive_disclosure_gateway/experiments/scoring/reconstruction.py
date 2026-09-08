"""Reconstruction scoring (T10 / issue #8): round-trip pseudonym->original
correctness against ``CaseOracle.reconstruction``.

Reads ``ExecutionResult.reconstructed_text`` -- necessarily a raw value at
this point, since it may contain a recovered original -- but only to
compute a boolean per category. The raw text itself is never part of this
module's output and must never be threaded further into any serialized
result (``experiments/case_result.py``'s safe serialization excludes it by
construction -- see ``tests/test_experiments_no_leak.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureAction, DisclosureResult

ReconstructionOutcome = Literal["correct", "incorrect", "not_applicable"]


@dataclass(frozen=True)
class CategoryReconstruction:
    category: str
    expected_reconstructable: bool
    outcome: ReconstructionOutcome


@dataclass(frozen=True)
class ReconstructionScore:
    by_category: tuple[CategoryReconstruction, ...]


def score_reconstruction(
    oracle: CaseOracle,
    result: DisclosureResult,
    reconstructed_text: str | None,
) -> ReconstructionScore:
    """Score every ``oracle.reconstruction`` expectation.

    ``reconstructed_text`` is ``None`` whenever reconstruction never ran at
    all (B0/B1, which implement no ``reconstruct``; or a blocked request) --
    every expectation resolves ``"not_applicable"`` in that case, never
    silently to ``"incorrect"``, since there is nothing to have gotten
    wrong.
    """
    scores: list[CategoryReconstruction] = []
    for expectation in oracle.reconstruction:
        category = expectation.category
        if reconstructed_text is None:
            scores.append(
                CategoryReconstruction(
                    category, expectation.expected_reconstructable, "not_applicable"
                )
            )
            continue

        pseudonymized_values = [
            transformation.original
            for transformation in result.transformations
            if transformation.category == category
            and transformation.action is DisclosureAction.PSEUDONYMIZE
        ]
        if not pseudonymized_values:
            scores.append(
                CategoryReconstruction(
                    category, expectation.expected_reconstructable, "not_applicable"
                )
            )
            continue

        recovered = all(value in reconstructed_text for value in pseudonymized_values)
        if expectation.expected_reconstructable:
            outcome: ReconstructionOutcome = "correct" if recovered else "incorrect"
        else:
            outcome = "incorrect" if recovered else "correct"
        scores.append(
            CategoryReconstruction(category, expectation.expected_reconstructable, outcome)
        )

    return ReconstructionScore(by_category=tuple(scores))
