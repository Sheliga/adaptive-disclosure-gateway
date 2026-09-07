import pytest

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.detection.overlap import resolve_overlaps
from adaptive_disclosure_gateway.domain import SensitiveSpan


def test_nested_overlap_between_labeled_and_structured_rule_keeps_longest_span():
    # The medical_data label captures the whole remainder of the line, which
    # here genuinely overlaps (fully contains) a structured CPF match produced
    # by an independent rule. Resolution must keep exactly one of them.
    text = "Medical notes: Patient CPF 123.456.789-09 requires leave.\n"

    spans = Detector().detect(text)

    categories = [span.category for span in spans]
    assert categories == ["medical_data"]
    assert spans[0].value == "Patient CPF 123.456.789-09 requires leave."


def test_resolve_overlaps_breaks_ties_by_category_precedence_regardless_of_input_order():
    cpf_span = SensitiveSpan(category="cpf", value="1234567890", start=0, end=10)
    phone_span = SensitiveSpan(category="phone", value="9876543210", start=0, end=10)

    forward = resolve_overlaps([cpf_span, phone_span])
    reversed_order = resolve_overlaps([phone_span, cpf_span])

    assert forward == [cpf_span]
    assert reversed_order == [cpf_span]


def test_resolve_overlaps_keeps_longer_span_on_partial_overlap():
    short_span = SensitiveSpan(category="phone", value="x" * 10, start=0, end=10)
    long_span = SensitiveSpan(category="email", value="y" * 15, start=5, end=20)

    resolved = resolve_overlaps([short_span, long_span])

    assert resolved == [long_span]


def test_resolve_overlaps_is_total_for_non_overlapping_spans():
    first = SensitiveSpan(category="cpf", value="a", start=0, end=5)
    second = SensitiveSpan(category="email", value="b", start=10, end=15)

    resolved = resolve_overlaps([second, first])

    assert resolved == [first, second]


def test_resolve_overlaps_does_not_silently_normalize_missing_offsets_to_zero_length():
    # Before issue #17, `_span_bounds` coerced `start=None, end=None` to
    # `(0, 0)`: a degenerate zero-length interval that never overlaps
    # anything, so the malformed span was silently accepted into the
    # resolved output instead of being flagged. `model_construct` bypasses
    # `SensitiveSpan`'s own offset validation (it skips Pydantic validators
    # entirely), which is the only way to get such a span past the domain
    # model at all.
    #
    # `resolve_overlaps` must fail closed with an explicit `ValueError`
    # rather than an incidental `TypeError` raised by arithmetic on `None`
    # inside `_sort_key` -- the guard is a deliberate contract, not a side
    # effect of subtraction order.
    malformed = SensitiveSpan.model_construct(
        category="cpf", value="secret-value-123", start=None, end=None, confidence=None
    )
    valid = SensitiveSpan(category="email", value="a@b.com", start=0, end=7)

    with pytest.raises(ValueError) as exc_info:
        resolve_overlaps([malformed, valid])

    message = str(exc_info.value)
    assert "cpf" in message
    assert "start=None" in message
    assert "end=None" in message
    # The sensitive `value` must never leak into an exception message: it
    # would end up in logs and tracebacks.
    assert malformed.value not in message
