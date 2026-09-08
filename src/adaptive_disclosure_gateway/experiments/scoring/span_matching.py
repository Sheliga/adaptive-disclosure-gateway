"""Shared oracle-span <-> transformation matching for T10's scorers.

Every scorer (conformance, exposure, unnecessary disclosure, utility) needs
the same thing first: for each ``CaseOracle.expected_spans`` entry, which
``Transformation`` (if any) the treatment actually produced for it. This
module computes that once, so the matching rule lives in exactly one place.

Matching strategy: oracle spans and ``DisclosureResult.transformations`` are
both grouped by ``category`` and matched positionally, in ``start``-offset
order for the oracle side and emission order (already text order, per
``decision_application._allowed_result``) for the transformations side. This
relies on detection recall being complete for ``corpus/hr/v1`` (documented
as 71/71 with no false positives in ``corpus/hr/v1/README.md``) -- if a
future corpus version's detector misses or over-detects a span, the
category's transformation pool runs out and the remaining oracle spans for
that category are reported ``unscorable`` (a distinct, visible scoring
outcome) rather than silently mismatched against the wrong transformation.

This module is scoring-only: it runs strictly after treatment execution and
is never imported by ``transformations/``, ``detection/``, ``policies.py``
or ``pipeline.py`` (see ``tests/test_corpus_oracle_isolation.py``, which
already forbids any production module from importing anything under
``adaptive_disclosure_gateway.corpus`` at all -- this module lives outside
that boundary, alongside the rest of ``experiments/scoring``).
"""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureResult,
    Transformation,
    Treatment,
)


@dataclass(frozen=True)
class ResolvedSpanRecord:
    """One oracle span's resolved outcome: the action actually applied, and
    the byte length of whatever representation was transmitted for it
    (never the representation itself beyond what ``Transformation.transformed``
    already carries -- for GENERALIZE that is the safe generalized band
    string, never a raw value). ``action`` is ``None`` only when no matching
    transformation could be found at all (an "unscorable" span).
    """

    action: DisclosureAction | None
    transmitted_byte_length: int


def resolve_span_transformations(
    oracle: CaseOracle, result: DisclosureResult, treatment: Treatment
) -> list[Transformation | None]:
    """The ``Transformation`` matched to each ``oracle.expected_spans`` entry,
    in oracle order. ``None`` for a blocked result (no transformations exist
    at all), for B0 -- Direct (which never produces a per-category
    breakdown -- see ``resolve_span_records`` for how B0 is scored instead),
    or for a span whose category's transformation pool ran out.
    """
    if result.status == "blocked" or treatment is Treatment.DIRECT:
        return [None for _ in oracle.expected_spans]

    ordered_indices = sorted(
        range(len(oracle.expected_spans)), key=lambda i: oracle.expected_spans[i].start
    )
    pools: dict[str, list[Transformation]] = {}
    for transformation in result.transformations:
        pools.setdefault(transformation.category, []).append(transformation)
    consumed: dict[str, int] = {}

    matched: list[Transformation | None] = [None] * len(oracle.expected_spans)
    for index in ordered_indices:
        span = oracle.expected_spans[index]
        pool = pools.get(span.category, [])
        position = consumed.get(span.category, 0)
        if position < len(pool):
            matched[index] = pool[position]
            consumed[span.category] = position + 1
    return matched


def resolve_span_records(
    oracle: CaseOracle, result: DisclosureResult, treatment: Treatment
) -> list[ResolvedSpanRecord]:
    """The resolved action/transmitted-length for each oracle span, in
    oracle order.

    Blocked results resolve every span to ``BLOCK_REQUEST`` with zero
    transmitted bytes (nothing left the boundary). B0 -- Direct resolves
    every span to ``PRESERVE`` -- its payload is the raw text unchanged, so
    every annotated unit is, by construction, fully exposed -- with the
    transmitted length taken from the oracle span's own value length (a
    length is metadata, never the value itself).
    """
    if result.status == "blocked":
        return [
            ResolvedSpanRecord(DisclosureAction.BLOCK_REQUEST, 0) for _ in oracle.expected_spans
        ]
    if treatment is Treatment.DIRECT:
        return [
            ResolvedSpanRecord(DisclosureAction.PRESERVE, len(span.value.encode("utf-8")))
            for span in oracle.expected_spans
        ]

    transformations = resolve_span_transformations(oracle, result, treatment)
    records: list[ResolvedSpanRecord] = []
    for transformation in transformations:
        if transformation is None:
            records.append(ResolvedSpanRecord(None, 0))
            continue
        transmitted_length = (
            len(transformation.transformed.encode("utf-8"))
            if transformation.transformed is not None
            else 0
        )
        records.append(ResolvedSpanRecord(transformation.action, transmitted_length))
    return records
