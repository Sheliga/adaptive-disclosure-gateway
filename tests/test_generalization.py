"""Pins issue #16's acceptance criteria: GENERALIZE must coarsen a value
while preserving a documented, measurable amount of information, be
deterministic, never leak the original, and fail closed for a category with
no configured strategy (instead of falling back to the original value).
"""

import pytest

from adaptive_disclosure_gateway.transformations.generalization import (
    MIN_NUMERIC_BAND_WIDTH,
    GeneralizationError,
    MonthYearDateStrategy,
    NumericBandStrategy,
    generalize,
    is_configured,
)


def test_salary_band_places_the_true_value_inside_the_emitted_band():
    result = generalize("salary", "R$ 8500.00")

    assert result == "R$ 5000-10000"


def test_salary_band_lower_boundary_belongs_to_the_band_it_starts():
    # Off-by-one is the likely real bug here: an amount exactly on a
    # boundary must fall into the band starting at that boundary, not the
    # one ending there.
    assert generalize("salary", "R$ 5000.00") == "R$ 5000-10000"
    assert generalize("salary", "R$ 4999.99") == "R$ 0-5000"


def test_salary_band_upper_boundary_belongs_to_the_next_band():
    assert generalize("salary", "R$ 10000.00") == "R$ 10000-15000"
    assert generalize("salary", "R$ 9999.99") == "R$ 5000-10000"


def test_generalize_output_never_contains_the_original_value():
    result = generalize("salary", "R$ 8500.00")

    assert "8500" not in result


def test_generalize_is_deterministic_for_the_same_input():
    first = generalize("salary", "R$ 8500.00")
    second = generalize("salary", "R$ 8500.00")

    assert first == second


def test_numeric_band_strategy_rejects_a_band_narrower_than_the_documented_minimum():
    with pytest.raises(ValueError, match="narrower than the documented minimum"):
        NumericBandStrategy(band_width=MIN_NUMERIC_BAND_WIDTH - 1)


def test_numeric_band_strategy_accepts_the_minimum_width_exactly():
    strategy = NumericBandStrategy(band_width=MIN_NUMERIC_BAND_WIDTH)

    assert strategy.generalize("500") == f"0-{int(MIN_NUMERIC_BAND_WIDTH)}"


def test_date_strategy_generalizes_to_month_and_year():
    strategy = MonthYearDateStrategy()

    assert strategy.generalize("2024-03-15") == "2024-03"


def test_date_strategy_first_and_last_day_of_month_produce_the_same_band():
    strategy = MonthYearDateStrategy()

    assert strategy.generalize("2024-03-01") == strategy.generalize("2024-03-31")


def test_date_strategy_boundary_across_month_end_is_distinguished():
    strategy = MonthYearDateStrategy()

    assert strategy.generalize("2024-03-31") != strategy.generalize("2024-04-01")


def test_date_strategy_rejects_unparseable_input_instead_of_returning_it():
    strategy = MonthYearDateStrategy()

    with pytest.raises(GeneralizationError):
        strategy.generalize("not-a-date")


def test_unconfigured_category_fails_closed_instead_of_returning_the_original():
    assert is_configured("bonus") is False
    with pytest.raises(GeneralizationError):
        generalize("bonus", "R$ 500.00")
