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
from decimal import Decimal

# Documented information-preservation floor for numeric bands (issue #16's
# "no leakage through over-narrow bands" requirement): a band narrower than
# this is close enough to a point estimate that it defeats the purpose of
# generalizing rather than removing the value outright. Expressed in the
# same unit as the generalized quantity (BRL for salary today).
MIN_NUMERIC_BAND_WIDTH = 1000.0

# Identifies the closed amount grammar `_AMOUNT_PATTERN` below implements
# (Issue #93 / M3, `post-pilot-v5`) -- recorded in run-script manifests'
# `reproducibility` block so a result can be tied back to exactly which
# amount-format contract its treatment ran under. Bumping this grammar
# (accepting or rejecting a different set of strings) requires a new id
# here, mirroring how `post_pilot_protocol.py` versions the scoring
# methodology: this constant versions the *treatment*-side parsing contract,
# which is a separate axis (a treatment-behavior change, not a scoring-only
# one -- see Issue #88).
NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"


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


# Closed, fullmatch-only, ASCII-digit grammar for a supported monetary
# amount (Issue #88 / #91 / #93, M3, `post-pilot-v5`, `NUMERIC_AMOUNT_GRAMMAR_ID`
# above). Formally:
#
#   AMOUNT  := "R$" SEP ( DOTTED | BRAZIL )
#   SEP     := exactly one of U+0020 (space) or U+00A0 (NBSP)
#   DOTTED  := (0|[1-9][0-9]{0,14}) "." [0-9]{2}
#   BRAZIL  := ( 0 | [1-9][0-9]{0,2}(\.[0-9]{3}){0,4} | [1-9][0-9]{3,14} ) "," [0-9]{2}
#
# Deliberately `[0-9]`, never `\d` (Issue #91: `\d` also matches non-ASCII
# Unicode decimal digits under Python's default, non-`re.ASCII` `re` module
# semantics), and matched with `fullmatch` only, never `search`/`match`+`$`
# (a `$` anchor alone still accepts one trailing `\n`).
#
# Both alternatives require exactly two cents digits -- an integer amount
# with no cents (`R$ 1.000`, `R$ 125000`) is rejected outright rather than
# guessed, and so is a grouped-but-cent-less Brazilian amount (`R$ 125.000`)
# because it is ambiguous with a dotted-decimal integer amount one order of
# magnitude smaller. `DOTTED` and `BRAZIL` are otherwise disjoint by
# construction: every `BRAZIL` string has exactly one `,` and no `DOTTED`
# string has one, so a string is never valid under both readings.
#
# `BRAZIL`'s three integer-part alternatives, in order: a bare `0`; 1-3
# leading digits followed by zero to four canonically-grouped `.ddd` triples
# (`999`, `1.000`, `999.999.999.999.999`); or, per the orchestrator's
# decision recorded in Issue #93, an *ungrouped* 4-15 digit Brazilian amount
# (`R$ 125000,00`) -- unambiguous because the comma unambiguously marks the
# decimal point regardless of grouping. No leading zero is accepted in
# either family (`0` alone is the only string starting with `0`), and no
# negative sign exists in the grammar at all (Issue #93: rejected outright,
# not merely undocumented -- there is no protocol need for one, and the
# pre-#93 `-?` prefix predates any rationale or test for it). The integer
# part is capped at 15 digits in both families, safely below 2^53, so no
# amount this grammar accepts can ever motivate a float round-trip.
_AMOUNT_PATTERN = re.compile(
    r"R\$[  ]"
    r"(?:(?P<dotted>(?:0|[1-9][0-9]{0,14})\.[0-9]{2})"
    r"|(?P<brazil>(?:0|[1-9][0-9]{0,2}(?:\.[0-9]{3}){0,4}|[1-9][0-9]{3,14}),[0-9]{2}))"
)


def _parse_amount(value: str) -> Decimal:
    """Parse ``value`` under the closed amount grammar above into an exact
    ``Decimal`` -- never a ``float`` (Issue #88's mis-banding/inf-NaN
    defects both trace to a float round-trip; ``Decimal`` has no rounding
    error and no overflow for any amount this grammar can accept).

    ``value`` is typed as ``str`` for callers (a detected span's value is
    always a string), but a non-``str`` input (a defensive case this
    grammar's own cross-check table exercises, e.g. ``None``) is rejected
    the same way as any other unparseable string, rather than raising
    ``TypeError`` from deep inside ``re``.
    """
    if not isinstance(value, str):
        # Never interpolate the raw value here: this message can reach logs
        # and OTel exception recording (issue #16 / 2a). The category and
        # failure kind are named by the caller (``generalize()``), which has
        # the category and wraps this into a category-scoped message.
        raise GeneralizationError("Could not parse a numeric amount from the supplied value")
    match = _AMOUNT_PATTERN.fullmatch(value)
    if match is None:
        raise GeneralizationError("Could not parse a numeric amount from the supplied value")
    dotted = match.group("dotted")
    if dotted is not None:
        return Decimal(dotted)
    brazil = match.group("brazil")
    integer_part, _, cents = brazil.partition(",")
    return Decimal(f"{integer_part.replace('.', '')}.{cents}")


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
        if self.band_width != int(self.band_width):
            # Issue #93 / M3: banding is done in exact integer arithmetic
            # (see generalize() below) now that amounts are parsed as
            # Decimal rather than float -- a fractional band_width has no
            # meaning under integer floor-division and would silently
            # truncate. Both registered widths today (5000.0, 50000.0) are
            # already integral; this only guards against a future
            # misconfiguration.
            raise ValueError(
                f"band_width={self.band_width!r} must be an integral value "
                "(e.g. 5000.0, not 5000.5) -- banding uses exact integer arithmetic"
            )

    def generalize(self, value: str) -> str:
        amount = _parse_amount(value)
        width = int(self.band_width)
        # `amount` is guaranteed non-negative by the closed amount grammar
        # (no `-` sign exists in it at all), so truncation (`int()`) and
        # floor are the same operation here.
        units = int(amount)
        lower = (units // width) * width
        upper = lower + width
        return f"{self.prefix}{lower}-{upper}"


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
        except ValueError:
            # `from None` (not `from exc`) is deliberate: datetime.strptime's
            # own ValueError embeds the raw offending string in its message
            # (e.g. "time data 'xyz' does not match format ..."). Chaining it
            # -- even just as __context__ -- would let that string resurface
            # through a full traceback dump (logging.exception, OTel
            # exception recording) even though this message never mentions
            # it. Never interpolate the value here (issue #16 / 2a); the
            # category is added by the caller (``generalize()``).
            raise GeneralizationError("Could not parse the supplied value as a date") from None
        return f"{parsed.year:04d}-{parsed.month:02d}"


# Configured, not hardcoded per call site: adding a category means adding an
# entry here.
GENERALIZATION_STRATEGIES: dict[str, GeneralizationStrategy] = {
    "salary": NumericBandStrategy(band_width=5000.0, prefix="R$ "),
    "birth_date": MonthYearDateStrategy(),
    # --- Contracts domain (Issue #56). Registry entries only: no new
    # strategy class was needed, which is the point of this module existing.
    #
    # Band widths are authored from the MAGNITUDE of each information type,
    # and were fixed before any Contracts case existed -- they are not tuned
    # against any outcome. A contract's total value and a penalty differ by
    # orders of magnitude, so one shared width cannot serve both: a R$ 5.000
    # band around a R$ 2.400.000 contract is a point estimate wearing a
    # range, while a R$ 50.000 band around a R$ 12.000 penalty discloses
    # nothing at all. Both sit far above MIN_NUMERIC_BAND_WIDTH.
    "contract_value": NumericBandStrategy(band_width=50000.0, prefix="R$ "),
    "penalty_amount": NumericBandStrategy(band_width=5000.0, prefix="R$ "),
    # A contractual deadline coarsens to month-and-year, the same fixed,
    # non-configurable floor birth_date uses. See
    # transformations/task_aware.py for why GENERALIZE is offered for
    # deadline at all even though `contracts-v1` itself prefers PRESERVE.
    "deadline": MonthYearDateStrategy(),
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
    try:
        result = strategy.generalize(value)
    except GeneralizationError:
        # Re-raised with the category added and `from None`: the inner
        # exception's own message is already value-free (see
        # `_parse_amount`/`MonthYearDateStrategy.generalize` above), but
        # discarding it here too means no future strategy can reintroduce a
        # value-bearing message or chained context through this entrypoint
        # without a test catching it (see tests/test_generalization.py and
        # the codebase-wide invariant in
        # tests/test_no_sensitive_value_in_raises.py).
        raise GeneralizationError(
            f"Generalization strategy for category {category!r} could not parse the supplied value"
        ) from None
    if result == value:
        raise GeneralizationError(
            f"Generalization strategy for {category!r} returned the original value unchanged"
        )
    return result
