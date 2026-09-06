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
