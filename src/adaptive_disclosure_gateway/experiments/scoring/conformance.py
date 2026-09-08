"""Conformance scoring (T10 / issue #8): per-span, against
``CaseOracle.expected_spans[*].expected_actions`` -- the conformance oracle,
independent of ``expected_answer``/``answer_depends_on_categories`` (the
utility oracle, scored separately in ``utility.py``). See
``corpus/hr/v1/SCHEMA.md``'s "Conformance and utility are independent
oracles" section, which this module and ``utility.py`` jointly implement as
two separately-computed scores rather than one collapsed metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureAction, DisclosureResult, Treatment

from .span_matching import resolve_span_records

ConformanceOutcome = Literal["conformant", "nonconformant", "unscorable"]


@dataclass(frozen=True)
class SpanConformance:
    index: int
    category: str
    task_necessity: str
    resolved_action: DisclosureAction | None
    expected_actions: tuple[DisclosureAction, ...]
    outcome: ConformanceOutcome


@dataclass(frozen=True)
class ConformanceScore:
    spans: tuple[SpanConformance, ...]
    conformant_count: int
    nonconformant_count: int
    unscorable_count: int
    total: int


def score_conformance(
    oracle: CaseOracle, result: DisclosureResult, treatment: Treatment
) -> ConformanceScore:
    records = resolve_span_records(oracle, result, treatment)
    spans: list[SpanConformance] = []
    conformant = nonconformant = unscorable = 0

    for index, span in enumerate(oracle.expected_spans):
        action = records[index].action
        expected = tuple(span.expected_actions)
        if action is None:
            outcome: ConformanceOutcome = "unscorable"
            unscorable += 1
        elif action in expected:
            outcome = "conformant"
            conformant += 1
        else:
            outcome = "nonconformant"
            nonconformant += 1
        spans.append(
            SpanConformance(
                index=index,
                category=span.category,
                task_necessity=span.task_necessity.value,
                resolved_action=action,
                expected_actions=expected,
                outcome=outcome,
            )
        )

    return ConformanceScore(
        spans=tuple(spans),
        conformant_count=conformant,
        nonconformant_count=nonconformant,
        unscorable_count=unscorable,
        total=len(oracle.expected_spans),
    )
