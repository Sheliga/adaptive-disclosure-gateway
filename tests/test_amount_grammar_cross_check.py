"""Issue #93 / M3 -- ``post-pilot-v5`` numeric amount format contract.

Two independent parsers exist for the same closed amount grammar (spec
``amount-grammar-v1``, ``docs/research/post-pilot-protocol-v5.md`` section 2):

- A (the treatment), ``transformations/generalization.py``'s
  ``_parse_amount`` -- one alternation regex with named groups, used by
  ``NumericBandStrategy.generalize`` to actually band a detected value;
- B (the scorer), ``experiments/scoring/utility.py``'s
  ``_parse_original_amount_v5`` -- two patterns (dotted, then Brazilian)
  tried in order, a different technique, used by the ``post-pilot-v5``
  fidelity rule to independently re-derive the same oracle value.

Deliberately two different implementations of the same closed grammar (never
one shared canonicalizer): if a shared helper had a bug, both the treatment
and the scorer would agree on a wrong value, and no test would ever catch
it. This module is the literal table both must agree with, transcribed from
the protocol document rather than either module's own source, so it cannot
silently drift into merely re-testing whatever the code currently does.

Every string here is small, synthetic literal data -- never real corpus
content.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from adaptive_disclosure_gateway.experiments.scoring.utility import (
    _parse_original_amount_v5,
)
from adaptive_disclosure_gateway.transformations.generalization import (
    GeneralizationError,
    _parse_amount,
)

NBSP = " "

# Arabic-Indic digits for "125000.00" -- non-ASCII digits with a "." that a
# `\d`-based grammar would still accept (Issue #91).
_ARABIC_INDIC_AMOUNT = "R$ ١٢٥٠٠٠.٠٠"

# Fullwidth digits for "125000.00" (Issue #91's other non-ASCII-digit shape).
_FULLWIDTH_AMOUNT = "R$ １２５０００.００"

# One ASCII digit, then an Arabic-Indic digit, in the same literal -- a
# partially non-ASCII string a naive "starts with an ASCII digit" check could
# still miss.
_MIXED_DIGITS_AMOUNT = "R$ 1250٠00.00"

# (input, expected Decimal string, or None for "must be rejected")
AMOUNT_GRAMMAR_CASES: tuple[tuple[str, str | None], ...] = (
    # --- accepted: dotted-decimal ---
    ("R$ 125000.00", "125000.00"),
    ("R$ 1.00", "1.00"),
    ("R$ 0.00", "0.00"),
    ("R$ 999999999999999.99", "999999999999999.99"),
    # --- accepted: Brazilian, grouped ---
    ("R$ 125.000,00", "125000.00"),
    ("R$ 1.275.000,00", "1275000.00"),
    ("R$ 1.000,00", "1000.00"),
    ("R$ 999.999.999.999.999,99", "999999999999999.99"),
    # --- accepted: Brazilian, ungrouped (orchestrator decision) ---
    ("R$ 125000,00", "125000.00"),
    ("R$ 1275000,00", "1275000.00"),
    ("R$ 999,99", "999.99"),
    ("R$ 1,00", "1.00"),
    ("R$ 0,00", "0.00"),
    ("R$ 999999999999999,99", "999999999999999.99"),
    # --- accepted: NBSP separator (orchestrator decision) ---
    (f"R${NBSP}125000.00", "125000.00"),
    (f"R${NBSP}125.000,00", "125000.00"),
    # --- rejected: integer without cents ---
    ("R$ 1.000", None),
    ("R$ 1.234", None),
    ("R$ 125.000", None),
    ("R$ 125000", None),
    # --- rejected: locale-ambiguous / wrong decimal mark placement ---
    ("R$ 1,000.00", None),
    # --- rejected: wrong cents digit count ---
    ("R$ 125.000,0", None),
    ("R$ 125.000,000", None),
    # --- rejected: malformed grouping ---
    ("R$ 1.2345,00", None),
    ("R$ 12.75.000,00", None),
    ("R$ 1.27.500,00", None),
    ("R$ 1.000000,00", None),
    # --- rejected: negatives ---
    ("R$ -5000.00", None),
    # --- rejected: leading zeros ---
    ("R$ 0125000.00", None),
    ("R$ 0.000,00", None),
    ("R$ 01,00", None),
    # --- rejected: non-ASCII digits ---
    (_ARABIC_INDIC_AMOUNT, None),
    (_FULLWIDTH_AMOUNT, None),
    (_MIXED_DIGITS_AMOUNT, None),
    # --- rejected: separator/spacing defects ---
    ("R$125.000,00", None),
    ("R$  125000.00", None),
    ("R$\t1.00", None),
    ("R$ 125000.00\n", None),
    ("R$ 125000.00\r", None),
    # --- rejected: trailing prose ---
    ("R$ 125000.00 was paid", None),
    # --- rejected: over the 15-digit integer-part bound ---
    ("R$ 1.000.000.000.000.000,00", None),
    ("R$ 1000000000000000.00", None),
    # --- rejected: wrong currency / no currency ---
    ("US$ 1.00", None),
    ("1.00", None),
    # --- rejected: degenerate ---
    ("", None),
    (None, None),
)


@pytest.mark.parametrize(("raw", "expected"), AMOUNT_GRAMMAR_CASES)
def test_treatment_parser_matches_the_literal_table(raw, expected):
    if expected is None:
        with pytest.raises(GeneralizationError):
            _parse_amount(raw)
    else:
        assert _parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize(("raw", "expected"), AMOUNT_GRAMMAR_CASES)
def test_scorer_parser_matches_the_literal_table(raw, expected):
    result = _parse_original_amount_v5(raw)
    if expected is None:
        assert result is None
    else:
        assert result == Decimal(expected)


@pytest.mark.parametrize(
    ("raw", "expected"), [case for case in AMOUNT_GRAMMAR_CASES if case[1] is not None]
)
def test_both_parsers_agree_on_every_accepted_value(raw, expected):
    """The two independent parsers must never merely both be present --
    they must derive the identical Decimal from the identical string, or a
    fidelity check comparing the treatment's own output against the scorer's
    independently-reparsed original would not actually be independent."""
    assert _parse_amount(raw) == _parse_original_amount_v5(raw) == Decimal(expected)
