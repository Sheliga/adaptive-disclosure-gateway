"""Unnecessary-disclosure scoring (T10 / issue #8).

Historical M2 binary metric, preserved as a secondary metric by the T23
post-pilot protocol (docs/experimental-design.md):

    transmitted sensitive units labeled NOT_REQUIRED / total sensitive units
    labeled NOT_REQUIRED present in the case

``HELPFUL`` never participates -- ``ExpectedSpan.task_necessity`` is
strictly binary (``TaskNecessity.REQUIRED``/``NOT_REQUIRED``) by schema
construction, so there is no third value this module could accidentally
mix in.

"Transmitted" means any exposure level other than none at all:
PSEUDONYMIZE, GENERALIZE or PRESERVE all count as transmitted (the
information left the boundary in some representation); REMOVE does not
(nothing left); BLOCK_REQUEST means nothing in the whole case was
transmitted and is excluded from the rate's numerator by construction (its
denominator membership is unaffected -- a NOT_REQUIRED span in a
correctly-blocked case still counts toward the denominator, just not the
numerator).
"""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_disclosure_gateway.corpus.models import TaskNecessity
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureAction, DisclosureResult, Treatment

from .exposure import score_exposure


@dataclass(frozen=True)
class UnnecessaryDisclosureScore:
    not_required_total: int
    not_required_transmitted: int
    rate: float | None
    transmitted_bytes: int


def score_unnecessary_disclosure(
    oracle: CaseOracle, result: DisclosureResult, treatment: Treatment
) -> UnnecessaryDisclosureScore:
    exposure = score_exposure(oracle, result, treatment)
    from .span_matching import resolve_span_records  # local import: avoids a cycle with exposure.py

    records = resolve_span_records(oracle, result, treatment)

    not_required_indices = [
        i
        for i, span in enumerate(oracle.expected_spans)
        if span.task_necessity is TaskNecessity.NOT_REQUIRED
    ]
    total = len(not_required_indices)

    transmitted_indices = [
        i
        for i in not_required_indices
        if exposure.spans[i].outcome == "exposure_level"
        and exposure.spans[i].level is not DisclosureAction.REMOVE
    ]
    transmitted = len(transmitted_indices)
    transmitted_bytes = sum(records[i].transmitted_byte_length for i in transmitted_indices)

    rate = (transmitted / total) if total else None
    return UnnecessaryDisclosureScore(
        not_required_total=total,
        not_required_transmitted=transmitted,
        rate=rate,
        transmitted_bytes=transmitted_bytes,
    )
