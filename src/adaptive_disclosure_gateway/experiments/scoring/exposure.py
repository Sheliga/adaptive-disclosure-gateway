"""Exposure scoring (T10 / issue #8).

Uses the ordered exposure ladder REMOVE < PSEUDONYMIZE < GENERALIZE <
PRESERVE -- reusing ``transformations.relevance_selection.CANONICAL_DISCLOSURE_ORDER``
rather than redefining it, so this scorer cannot silently drift from the
same ladder B3/B4 already use to reason about "least disclosing". Per
docs/experimental-design.md, ``BLOCK_REQUEST`` is a distinct outcome, never
a level on this ladder -- a blocked span is scored ``"block_request"``, not
assigned any exposure rank.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureAction, DisclosureResult, Treatment
from adaptive_disclosure_gateway.transformations.relevance_selection import (
    CANONICAL_DISCLOSURE_ORDER,
)

from .span_matching import resolve_span_records

ExposureOutcome = Literal["exposure_level", "block_request", "unscorable"]


@dataclass(frozen=True)
class SpanExposure:
    index: int
    category: str
    task_necessity: str
    outcome: ExposureOutcome
    level: DisclosureAction | None
    level_rank: int | None


@dataclass(frozen=True)
class ExposureScore:
    spans: tuple[SpanExposure, ...]
    blocked: bool


def score_exposure(
    oracle: CaseOracle, result: DisclosureResult, treatment: Treatment
) -> ExposureScore:
    records = resolve_span_records(oracle, result, treatment)
    spans: list[SpanExposure] = []

    for index, span in enumerate(oracle.expected_spans):
        action = records[index].action
        if action is None:
            outcome: ExposureOutcome = "unscorable"
            level, rank = None, None
        elif action is DisclosureAction.BLOCK_REQUEST:
            outcome = "block_request"
            level, rank = None, None
        else:
            outcome = "exposure_level"
            level = action
            rank = CANONICAL_DISCLOSURE_ORDER.index(action)
        spans.append(
            SpanExposure(
                index=index,
                category=span.category,
                task_necessity=span.task_necessity.value,
                outcome=outcome,
                level=level,
                level_rank=rank,
            )
        )

    return ExposureScore(spans=tuple(spans), blocked=result.status == "blocked")
