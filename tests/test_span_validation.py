"""Unit coverage for the shared transformation-boundary span validator
(issue #17). Static Sanitization (B1)'s own tests (tests/test_static_sanitization.py) cover it
through `StaticSanitizer.sanitize`; these pin the helper directly since later treatments (B2-B4)
are expected to import it too.
"""

from adaptive_disclosure_gateway.domain import SensitiveSpan
from adaptive_disclosure_gateway.transformations.span_validation import (
    span_matches_text,
    spans_are_valid,
)

TEXT = "CPF: 123.456.789-09 recorded."


def test_span_matches_text_accepts_offsets_that_match_the_claimed_value():
    span = SensitiveSpan(category="cpf", value="123.456.789-09", start=5, end=19)

    assert span_matches_text(span, TEXT) is True


def test_span_matches_text_rejects_out_of_bounds_end():
    span = SensitiveSpan(category="cpf", value="123.456.789-09", start=5, end=1000)

    assert span_matches_text(span, TEXT) is False


def test_span_matches_text_rejects_value_offset_mismatch():
    # In-bounds and well-formed, but the offsets point at "CPF:" rather than
    # the CPF value the span claims.
    span = SensitiveSpan(category="cpf", value="123.456.789-09", start=0, end=4)

    assert span_matches_text(span, TEXT) is False


def test_span_matches_text_rejects_missing_offsets_bypassing_the_model():
    # model_construct skips SensitiveSpan's own validator, so this is the
    # only way to produce a span with missing offsets to test against.
    span = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=None, end=None, confidence=None
    )

    assert span_matches_text(span, TEXT) is False


def test_span_matches_text_rejects_negative_start_bypassing_the_model():
    span = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=-1, end=19, confidence=None
    )

    assert span_matches_text(span, TEXT) is False


def test_span_matches_text_rejects_inverted_offsets_bypassing_the_model():
    span = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=19, end=5, confidence=None
    )

    assert span_matches_text(span, TEXT) is False


def test_spans_are_valid_is_false_when_any_span_fails():
    good = SensitiveSpan(category="cpf", value="123.456.789-09", start=5, end=19)
    bad = SensitiveSpan(category="cpf", value="123.456.789-09", start=5, end=1000)

    assert spans_are_valid([good, bad], TEXT) is False


def test_spans_are_valid_is_true_when_all_spans_pass():
    first = SensitiveSpan(category="cpf", value="123.456.789-09", start=5, end=19)

    assert spans_are_valid([first], TEXT) is True
