"""Detector precision/recall/F1 scoring (PR #35 review, blocker 2).

Compares the real spans the ``Detector`` produced during a case's actual
execution (captured by ``experiments.detector_capture.RecordingDetector`` --
never a second, independently re-run detection pass) against
``CaseOracle.expected_spans``. Runs strictly after treatment execution,
exactly like every other scorer in this package (ground truth never reaches
``execute_case`` -- see ``execution.py``'s module docstring).

Matching rule (documented, exact-match only -- no partial-overlap credit,
no fuzzy category matching): a detected span counts as a true positive for
exactly one oracle span sharing an identical ``(category, start, end)``
triple. Every oracle span left unmatched after every detected span has had
a chance to claim it is a false negative; every detected span left
unmatched is a false positive. Duplicate ``(category, start, end)`` keys on
either side are resolved by position (oracle order for the oracle side,
detection order for the leftover side), so a case with repeated identical
spans still produces a determinate, reproducible count rather than an
ambiguous one.

Every field on ``DetectorSpanResult``/``DetectorCaseScore``/
``DetectorAggregateScore`` is a category name, an offset, a count or a rate
-- never the detected/expected span's own text (CLAUDE.md's no-leak
invariant).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean
from typing import Literal

from adaptive_disclosure_gateway.corpus.models import ExpectedSpan

from ..detector_capture import DetectedSpanRef

DetectorSpanOutcome = Literal["true_positive", "false_positive", "false_negative"]


@dataclass(frozen=True)
class DetectorSpanResult:
    category: str
    start: int
    end: int
    outcome: DetectorSpanOutcome


@dataclass(frozen=True)
class DetectorCaseScore:
    """One case's detector performance against its oracle.

    ``precision``/``recall``/``f1`` are ``None`` (never ``0.0`` or any other
    invented number) whenever their denominator is zero -- e.g. ``precision``
    is ``None`` when the detector produced no spans at all for this case, and
    ``recall`` is ``None`` only if the oracle itself has no expected spans
    (never true for this codebase's corpora, which require at least one, but
    kept correct rather than assumed). ``f1`` is ``None`` whenever either of
    ``precision``/``recall`` is ``None``; otherwise ``0.0`` if the two are
    both zero (no true positives, but at least one false positive or false
    negative existed) rather than an undefined division.
    """

    spans: tuple[DetectorSpanResult, ...]
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float | None
    recall: float | None
    f1: float | None


@dataclass(frozen=True)
class DetectorAggregateScore:
    """Corpus-wide detector performance.

    ``micro_*`` sums true/false positive/negative counts across every case
    first, then computes one rate -- weighting every span equally regardless
    of which case it came from. ``macro_*`` instead averages each case's own
    already-computed rate, skipping cases where that rate is undefined
    (``None``) -- weighting every *case* equally regardless of how many
    spans it has. Both are reported; neither is treated as more "correct"
    than the other.
    """

    case_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    micro_precision: float | None
    micro_recall: float | None
    micro_f1: float | None
    macro_precision: float | None
    macro_recall: float | None
    macro_f1: float | None


def _safe_divide(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_detector_case(
    expected_spans: Sequence[ExpectedSpan], detected_spans: Sequence[DetectedSpanRef]
) -> DetectorCaseScore:
    """Score one case's real, captured detector output against its oracle's
    ``expected_spans``. See the module docstring for the exact-match rule.
    """
    remaining = list(detected_spans)
    consumed = [False] * len(remaining)
    results: list[DetectorSpanResult] = []
    true_positive = 0
    false_negative = 0

    for span in expected_spans:
        match_index = None
        for index, detected in enumerate(remaining):
            if consumed[index]:
                continue
            if (
                detected.category == span.category
                and detected.start == span.start
                and detected.end == span.end
            ):
                match_index = index
                break
        if match_index is not None:
            consumed[match_index] = True
            true_positive += 1
            results.append(DetectorSpanResult(span.category, span.start, span.end, "true_positive"))
        else:
            false_negative += 1
            results.append(
                DetectorSpanResult(span.category, span.start, span.end, "false_negative")
            )

    false_positive = 0
    for index, detected in enumerate(remaining):
        if not consumed[index]:
            false_positive += 1
            results.append(
                DetectorSpanResult(
                    detected.category, detected.start, detected.end, "false_positive"
                )
            )

    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)

    return DetectorCaseScore(
        spans=tuple(results),
        true_positive_count=true_positive,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
    )


def aggregate_detector_scores(scores: Sequence[DetectorCaseScore]) -> DetectorAggregateScore:
    """Micro and macro precision/recall/F1 over every case's
    ``DetectorCaseScore`` -- see ``DetectorAggregateScore`` for the
    distinction. ``scores`` may be empty (every rate is then ``None``,
    every count ``0``) -- never invented as ``0.0``/``1.0``.
    """
    true_positive = sum(s.true_positive_count for s in scores)
    false_positive = sum(s.false_positive_count for s in scores)
    false_negative = sum(s.false_negative_count for s in scores)

    micro_precision = _safe_divide(true_positive, true_positive + false_positive)
    micro_recall = _safe_divide(true_positive, true_positive + false_negative)

    precisions = [s.precision for s in scores if s.precision is not None]
    recalls = [s.recall for s in scores if s.recall is not None]
    f1s = [s.f1 for s in scores if s.f1 is not None]

    return DetectorAggregateScore(
        case_count=len(scores),
        true_positive_count=true_positive,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=_f1(micro_precision, micro_recall),
        macro_precision=mean(precisions) if precisions else None,
        macro_recall=mean(recalls) if recalls else None,
        macro_f1=mean(f1s) if f1s else None,
    )
