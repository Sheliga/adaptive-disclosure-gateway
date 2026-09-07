"""Semantic GENERALIZE strategies (issue #16).

``DisclosureAction.GENERALIZE`` must coarsen a value while preserving a
documented, measurable amount of information -- unlike a fixed
``[REDACTED:{category}]`` placeholder, which discloses nothing and is
therefore informationally equivalent to ``REMOVE``. This module is the
single place a category's generalization strategy is configured; adding a
category means adding an entry to ``GENERALIZATION_STRATEGIES`` here, not
editing a sanitizer call site.

Both Static Sanitization (B1) and Reversible Pseudonymization (B2) import
this module for their GENERALIZE handling; it has no dependency on policy,
vault, or task-awareness, so importing it does not affect either
treatment's isolation contract (see tests/test_treatment_isolation.py).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# Documented information-preservation floor for numeric bands (issue #16's
# "no leakage through over-narrow bands" requirement): a band narrower than
# this is close enough to a point estimate that it defeats the purpose of
# generalizing rather than removing the value outright. Expressed in the
# same unit as the generalized quantity (BRL for salary today).
MIN_NUMERIC_BAND_WIDTH = 1000.0


class GeneralizationError(Exception):
    """Raised when a value cannot be generalized: either no strategy is
    configured for its category, or the strategy could not parse the value.

    Callers MUST treat this as fail-closed (block the whole request for that
    category), never as "fall back to emitting the original value" -- see
    issue #16's acceptance criteria.
    """


class GeneralizationStrategy(ABC):
    """A deterministic, category-specific coarsening rule.

    Implementations must never return the exact original value, and must
    guarantee the original value is only recoverable as "falls somewhere in
    this band/period" -- never pinpointed.
    """

    @abstractmethod
    def generalize(self, value: str) -> str:
        raise NotImplementedError


_AMOUNT_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_amount(value: str) -> float:
    match = _AMOUNT_PATTERN.search(value)
    if match is None:
        raise GeneralizationError(f"Could not parse a numeric amount out of {value!r}")
    return float(match.group())


@dataclass(frozen=True)
class NumericBandStrategy(GeneralizationStrategy):
    """Bins a numeric value into a fixed-width, half-open ``[lower, upper)``
    band, e.g. salary ``R$ 8500.00`` with ``band_width=5000`` becomes
    ``"R$ 5000-10000"``.

    A value exactly on a boundary belongs to the band it starts, not the one
    it ends (floor division): ``5000.00`` lands in ``5000-10000``, not
    ``0-5000``. That edge is the off-by-one this strategy is most likely to
    get wrong, so it is pinned by tests at both boundaries.
    """

    band_width: float
    prefix: str = ""

    def __post_init__(self) -> None:
        if self.band_width < MIN_NUMERIC_BAND_WIDTH:
            raise ValueError(
                f"band_width={self.band_width!r} is narrower than the documented minimum "
                f"({MIN_NUMERIC_BAND_WIDTH}); a tighter band risks identifying the original value"
            )

    def generalize(self, value: str) -> str:
        amount = _parse_amount(value)
        band_index = amount // self.band_width
        lower = band_index * self.band_width
        upper = lower + self.band_width
        return f"{self.prefix}{int(lower)}-{int(upper)}"


@dataclass(frozen=True)
class MonthYearDateStrategy(GeneralizationStrategy):
    """Coarsens an ISO ``YYYY-MM-DD`` date down to its month and year, e.g.
    ``2024-03-15`` and ``2024-03-31`` both become ``"2024-03"``. The day of
    month is never disclosed -- this is the strategy's fixed, non-configurable
    minimum granularity, so there is no narrower setting to misconfigure the
    way a numeric band's width can be.
    """

    date_format: str = "%Y-%m-%d"

    def generalize(self, value: str) -> str:
        try:
            # Calendar date only, deliberately: no time component is parsed
            # or retained, so there is no timezone to attach (DTZ007 does
            # not apply -- the result is truncated to year/month regardless).
            parsed = datetime.strptime(value, self.date_format).date()  # noqa: DTZ007
        except ValueError as exc:
            raise GeneralizationError(f"Could not parse {value!r} as a date") from exc
        return f"{parsed.year:04d}-{parsed.month:02d}"


# Configured, not hardcoded per call site: adding a category means adding an
# entry here.
GENERALIZATION_STRATEGIES: dict[str, GeneralizationStrategy] = {
    "salary": NumericBandStrategy(band_width=5000.0, prefix="R$ "),
    "birth_date": MonthYearDateStrategy(),
}


def is_configured(category: str) -> bool:
    """True if ``category`` has a registered generalization strategy.

    Sanitizers use this to decide, before slicing any text, whether a
    GENERALIZE-mapped category can actually be generalized or must instead
    fail closed (BLOCK_REQUEST) -- see issue #16's fail-closed requirement.
    """
    return category in GENERALIZATION_STRATEGIES


def generalize(category: str, value: str) -> str:
    """Generalize ``value`` for ``category`` using the registered strategy.

    Raises ``GeneralizationError`` -- never silently returns ``value`` --
    if no strategy is configured for ``category``, or if the configured
    strategy cannot parse ``value``.
    """
    strategy = GENERALIZATION_STRATEGIES.get(category)
    if strategy is None:
        raise GeneralizationError(
            f"No generalization strategy configured for category {category!r}"
        )
    result = strategy.generalize(value)
    if result == value:
        raise GeneralizationError(
            f"Generalization strategy for {category!r} returned the original value unchanged"
        )
    return result
