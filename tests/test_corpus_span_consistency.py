"""Offset self-consistency for the frozen HR pilot corpus (T09 / issue #4,
Phase A): every annotated span's offsets must be valid against its own
case's ``input.text``, and the text they name must equal the annotated
``value`` exactly.

Reuses ``transformations/span_validation.py`` (the same boundary check
every treatment runs before slicing) rather than reimplementing offset
arithmetic here -- this is deliberate: a bug in a hand-rolled duplicate
checker would prove nothing about whether the corpus is safe for the real
pipeline to consume.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.corpus import load_corpus
from adaptive_disclosure_gateway.domain import SensitiveSpan
from adaptive_disclosure_gateway.transformations.span_validation import (
    span_matches_text,
    spans_are_valid,
)

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"


def _as_sensitive_spans(expected_spans) -> list[SensitiveSpan]:
    return [
        SensitiveSpan(
            category=span.category,
            value=span.value,
            start=span.start,
            end=span.end,
        )
        for span in expected_spans
    ]


def test_every_frozen_case_has_offsets_valid_against_its_own_text():
    cases = load_corpus(REAL_CORPUS_DIR)
    assert cases, "expected at least one corpus case to check"

    failures = []
    for case in cases:
        spans = _as_sensitive_spans(case.oracle.expected_spans)
        if not spans_are_valid(spans, case.input.text):
            failures.append(case.input.sample_id)

    assert not failures, f"corpus cases with inconsistent span offsets: {failures}"


def test_span_matches_text_detects_a_genuinely_wrong_offset():
    # Not a check on the real corpus: this pins that the reused validator
    # actually rejects a wrong annotation, so a passing corpus-wide check
    # above means something. An off-by-one start would slice one character
    # short of "Duarte", which must not equal the annotated value.
    text = "Employee: Marina Duarte\n"
    correct = SensitiveSpan(category="employee_name", value="Marina Duarte", start=10, end=23)
    off_by_one = SensitiveSpan(category="employee_name", value="Marina Duarte", start=11, end=23)

    assert span_matches_text(correct, text)
    assert not span_matches_text(off_by_one, text)


def test_span_matches_text_detects_a_value_that_does_not_match_the_slice():
    # A span whose offsets are structurally valid and in-bounds, but whose
    # claimed value does not equal the text at that position -- the
    # annotation-drift defect this check exists to catch (e.g. the text was
    # edited but the value field was not).
    text = "Department: Engineering\n"
    stale_value = SensitiveSpan(category="department", value="Marketing", start=12, end=23)

    assert not span_matches_text(stale_value, text)
