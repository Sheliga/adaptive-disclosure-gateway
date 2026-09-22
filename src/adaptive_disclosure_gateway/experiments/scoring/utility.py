"""Utility scoring (T10 / issue #8).

Scored against ``CaseOracle.expected_answer``/``answer_depends_on_categories``
-- the utility oracle -- deliberately independent of ``expected_actions``
(the conformance oracle scored in ``conformance.py``). See
``corpus/hr/v1/SCHEMA.md``'s "Conformance and utility are independent
oracles": an action can be a fully conformant member of ``expected_actions``
and still destroy the information ``expected_answer`` depends on (the
documented ``hr_department_aggregation_003``/``hr_salary_analysis_003``
GENERALIZE-band case), and the reverse also holds -- a nonconformant action
can still happen to preserve enough information to answer.

Pilot-scoped measurement choice, documented here because it drives every
utility outcome this module produces: ``FakeProvider`` never computes a
real answer (it returns a fixed acknowledgement string -- see
``providers/fake.py``), so utility cannot be scored from the provider's
*response* text at all in this pilot. Instead this module scores whether
the *disclosure-controlled payload* retains enough information, per
category, for a competent provider to have answered -- an information-
sufficiency proxy, not a literal-answer-correctness check. This must be
re-scored against real provider output once T22's real-provider work lands;
until then this proxy is the only thing FakeProvider makes measurable, and
docs/experimental-design.md's own provider-strategy section already
anticipates this split (FakeProvider valid for the pilot, a real provider
required before authoritative utility claims).

Numeric-band GENERALIZE fidelity rule (M3 / Issue #85, ``post-pilot-v3``):
a generalized numeric band is scored **fidelity-first, then
sufficiency**. Fidelity is checked by ``classify_generalized_band`` below,
against the oracle span's own value (never a transformation's
self-reported ``original``): the band must be a validly-shaped,
non-degenerate half-open interval that actually contains the original
value, or the case is ``not_answerable`` outright -- a wrong band no
longer scores ``answerable`` merely because no reference figure happens to
fall inside it. Only once fidelity holds does sufficiency apply: a
generalized band is "decidable" against a reference figure stated
elsewhere in ``input.text`` (outside any detected span) only if the
reference falls strictly outside the band -- if it falls inside, the band
alone cannot tell whether the original value was above or below the
reference, exactly the ambiguity ``corpus/hr/v1/SCHEMA.md`` documents for
``hr_salary_analysis_003`` and ``hr_department_aggregation_003``. With no
stated reference at all, the outcome is ``indeterminate`` (never vacuously
``answerable`` -- ``docs/research/post-pilot-protocol-v3.md`` section 2).
This replaces the pre-``v3`` rule (``_band_is_decidable``), which checked
sufficiency only and never fidelity -- see
``docs/research/post-pilot-protocol-v3.md`` for the audit, the minimal
reproduction and the anti-tuning provenance of this rule.

Date-aware GENERALIZE rule (M3 Gate 6 / Issue #38, ``post-pilot-v2``):
the numeric-band rule above is a type error when applied to a
``MonthYearDateStrategy`` output (a month-year date, e.g. ``"2026-02"``) --
a numeric-band regex happily matches ``2026-02`` as a "band" from 2026 down
to 2, which every reference value trivially falls outside of, so every
month-year GENERALIZE was scored ``answerable`` regardless of whether the
generalization actually served the task. ``DATE_UTILITY_REQUIRED_GRANULARITY``
and ``classify_generalized_date`` below replace that for the categories
registered here; every other numeric GENERALIZE category is routed through
the fidelity-first rule above instead. See
``docs/research/post-pilot-protocol-v2.md`` section 6.1a for the full
rationale and ``docs/contracts-policy-matrix.md``'s "deadline as a hard
preserve" section / commit 66e4677 (2026-09-12, Issue #56) for the
pre-result provenance of the day-granularity requirement below.

A GENERALIZE on any category that is neither a registered date category nor
a registered numeric category is rejected outright
(``generalized_category_unregistered``) rather than silently falling into
either existing rule -- unreachable today (every registered category is one
or the other), but named so a future category addition cannot silently
inherit the wrong semantics by omission (Issue #85).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import CorpusCase
from adaptive_disclosure_gateway.corpus.models import NumericUtilityReference, ReferenceOperator
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureAction, DisclosureResult, Treatment
from adaptive_disclosure_gateway.transformations.generalization import NUMERIC_AMOUNT_GRAMMAR_ID

from ..post_pilot_protocol import UnsupportedScoringProtocolError, validate_scorable_protocol_id
from .span_matching import resolve_span_transformations

UtilityOutcome = Literal["answerable", "not_answerable", "indeterminate", "not_applicable"]

_AMOUNT_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

# The categories the numeric-band GENERALIZE fidelity rule
# (``classify_generalized_band``) governs -- every registered category whose
# ``transformations/generalization.py`` strategy is ``NumericBandStrategy``.
# Disjoint from ``DATE_UTILITY_REQUIRED_GRANULARITY`` by construction (pinned
# by a drift guard in
# ``tests/test_experiments_scoring_numeric_band_utility.py``): a category is
# routed through exactly one of the two rules, never both, never neither
# (Issue #85's third out-of-scope finding).
NUMERIC_BAND_UTILITY_CATEGORIES: frozenset[str] = frozenset(
    {"salary", "contract_value", "penalty_amount"}
)

# The strict grammar a numeric GENERALIZE band's oracle *original* value must
# take: ``R$ <digits>.<2 digits>`` exactly, matching every numeric oracle
# span value across both registered corpora. Deliberately not the generator's
# own ``_parse_amount`` (``transformations/generalization.py``) -- reusing it
# would make this fidelity check circular (it would inherit that parser's own
# Brazilian-thousands-format misparse; see the separate issue this ticket
# files) and would accept shapes (bare numbers, no currency prefix) this
# scorer has no basis to treat as a real oracle amount.
_ORIGINAL_AMOUNT_PATTERN = re.compile(r"^R\$ (\d+\.\d{2})$")

# The strict grammar a numeric GENERALIZE band's *transformed* value must
# take: ``R$ <lower>-<upper>``, both non-negative integers with no leading
# zero (matching ``NumericBandStrategy.generalize``'s own
# ``f"{prefix}{int(lower)}-{int(upper)}"`` output exactly). Lower/upper
# ordering (``lower < upper``) is checked separately below, not by this
# pattern, so an inverted or degenerate band can be named with its own
# reason rather than silently failing to match.
_BAND_STRING_PATTERN = re.compile(r"^R\$ (0|[1-9]\d*)-(0|[1-9]\d*)$")

# The closed set of reasons ``classify_generalized_band`` can return --
# CLAUDE.md's no-leak invariant: every reason names a category of outcome,
# never a value. Exists as a real constant (not just literals scattered
# through the function body) so tests can assert closure without having to
# enumerate the function's own control flow.
NUMERIC_BAND_UTILITY_REASONS: frozenset[str] = frozenset(
    {
        "generalized_band_unscorable_original",
        "generalized_band_invalid",
        "generalized_band_excludes_original",
        "generalized_band_no_reference",
        "generalized_band_decidable",
        "generalized_band_ambiguous",
    }
)

# --- post-pilot-v5 original-amount grammar (Issue #88 / #91 / #93, M3) -----
#
# The scorer's own, independent re-derivation of
# ``transformations/generalization.py``'s closed amount grammar
# (``NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"``). Deliberately a
# *different* implementation technique from the treatment's single
# alternation regex with named groups: two separate patterns (dotted, then
# Brazilian), each `fullmatch`-ed in turn, so a bug shared between the two
# parsers cannot make this fidelity check circularly agree with a wrong
# treatment output (see this module's own historical
# ``_ORIGINAL_AMOUNT_PATTERN`` docstring for why that circularity would be a
# real defect, not merely inelegant). ASCII ``[0-9]`` only, never ``\d``
# (Issue #91); ``fullmatch`` only, never ``match``+``$`` (which still accepts
# one trailing ``\n``) -- unlike ``_ORIGINAL_AMOUNT_PATTERN`` above, which is
# frozen ``post-pilot-v3`` code and keeps both of those defects on purpose.
_V5_DOTTED_ORIGINAL_PATTERN = re.compile(r"R\$[  ](0|[1-9][0-9]{0,14})\.([0-9]{2})")
_V5_BRAZIL_ORIGINAL_PATTERN = re.compile(
    r"R\$[  ]((?:0)|(?:[1-9][0-9]{0,2}(?:\.[0-9]{3}){0,4})|(?:[1-9][0-9]{3,14})),([0-9]{2})"
)

# The v5 transformed-band grammar: identical shape to ``_BAND_STRING_PATTERN``
# (``NumericBandStrategy`` always emits ``R$ <lower>-<upper>`` in ASCII with a
# plain space, regardless of which original-amount family produced it --
# Issue #93's canonical band representation is unchanged), but matched with
# ``fullmatch`` rather than ``match``+``$`` so a trailing ``\n`` is rejected.
_V5_BAND_PATTERN = re.compile(r"R\$ (0|[1-9][0-9]*)-(0|[1-9][0-9]*)")


def _parse_original_amount_v5(original: str | None) -> Decimal | None:
    """The oracle span's own numeric value under the ``post-pilot-v5``
    grammar: dotted-decimal or Brazilian, tried in that order. Returns
    ``None`` for anything outside the closed grammar -- callers treat that
    as ``generalized_band_unscorable_original``, exactly like
    ``_parse_strict_original_amount``.
    """
    if not isinstance(original, str):
        return None
    match = _V5_DOTTED_ORIGINAL_PATTERN.fullmatch(original)
    if match is not None:
        return Decimal(f"{match.group(1)}.{match.group(2)}")
    match = _V5_BRAZIL_ORIGINAL_PATTERN.fullmatch(original)
    if match is not None:
        integer_part = match.group(1).replace(".", "")
        return Decimal(f"{integer_part}.{match.group(2)}")
    return None


def _parse_band_v5(transformed: str | None) -> tuple[int, int] | None:
    """The v5 counterpart of ``_parse_band``: same closed band grammar,
    matched with ``fullmatch``."""
    if not isinstance(transformed, str):
        return None
    match = _V5_BAND_PATTERN.fullmatch(transformed)
    if match is None:
        return None
    lower, upper = int(match.group(1)), int(match.group(2))
    if lower >= upper:
        return None
    return lower, upper


def _check_band_fidelity_v5(
    original: str | None, transformed: str | None
) -> tuple[UtilityOutcome, str] | tuple[int, int]:
    """The ``post-pilot-v5`` counterpart of ``_check_band_fidelity``, using
    the v5 original/band parsers above. Same three sub-cases, same closed
    reason set.
    """
    original_amount = _parse_original_amount_v5(original)
    if original_amount is None:
        return "not_answerable", "generalized_band_unscorable_original"

    band = _parse_band_v5(transformed)
    if band is None:
        return "not_answerable", "generalized_band_invalid"

    lower, upper = band
    if not (lower <= original_amount < upper):
        return "not_answerable", "generalized_band_excludes_original"

    return lower, upper


def _classify_structured_sufficiency(
    lower: int, upper: int, references: Sequence[NumericUtilityReference]
) -> tuple[UtilityOutcome, str]:
    """Steps 4-5 of the structured-reference numeric-band rule (Issue #87 /
    M3, extracted for Issue #93 / M3 so ``post-pilot-v4``'s
    ``classify_generalized_band_against_references`` and ``post-pilot-v5``'s
    ``classify_generalized_band_against_references_v5`` share this exact
    sufficiency step rather than risking the two silently drifting apart --
    mirroring why ``_check_band_fidelity`` itself is already shared for
    fidelity. Takes an already-fidelity-checked ``(lower, upper)`` pair, never
    a raw original/transformed string.

    No behavior change versus the v4 code this was extracted from: an empty
    ``references`` -> ``("indeterminate", "generalized_band_no_reference")``;
    otherwise ``("answerable", "generalized_band_decidable")`` iff every
    reference is individually decidable (``_reference_is_decidable``),
    else ``("indeterminate", "generalized_band_ambiguous")``.
    """
    if not references:
        return "indeterminate", "generalized_band_no_reference"

    if all(
        _reference_is_decidable(reference.operator, reference.amount, lower, upper)
        for reference in references
    ):
        return "answerable", "generalized_band_decidable"
    return "indeterminate", "generalized_band_ambiguous"


# Per-category required GENERALIZE granularity for date-shaped categories
# (M3 Gate 6 / Issue #38). "day" is the finest granularity this registry
# ever names (a day-precision GENERALIZE is never actually a generalization
# -- see classify_generalized_date's "excess precision" outcome -- so a
# category can never *require* "day" as a coarsened target, only as the
# floor below which coarsening stops serving the task).
#
# ``deadline: "day"`` is fixed by pre-result provenance, not tuned against
# any Contracts result: commit 66e4677 (2026-09-12 02:23 -03, Issue #56)
# wrote in docs/contracts-policy-matrix.md, before corpus/contracts/v1
# existed, that "a legal deadline coarsened to a month is not a term of a
# contract" -- independently, every required-deadline expected_answer in
# corpus/contracts/v1 already cites the full ISO day (pinned by
# tests/test_experiments_scoring_date_utility.py's coherence guard).
#
# Limitation: granularity is per category, not per task -- a future task
# that only needs a month-level deadline would require a new protocol
# version's own registry, not a change to this one (see
# docs/research/post-pilot-protocol-v2.md section 6.1a).
DATE_UTILITY_REQUIRED_GRANULARITY: dict[str, str] = {"deadline": "day"}

# Ordinal order of the three grammar granularities classify_generalized_date
# recognizes, finest first. Used only to compare a parsed granularity
# against a category's required one -- never to compute a distance between
# them (there is no numeric-band-style width here).
_DATE_GRANULARITY_ORDER: dict[str, int] = {"day": 0, "month": 1, "year": 2}

_ORIGINAL_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR_ONLY_PATTERN = re.compile(r"^(\d{4})$")
_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR_MONTH_DAY_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _parse_original_date(original: str | None) -> tuple[int, int, int] | None:
    """The oracle span's own date value, parsed strictly: ``YYYY-MM-DD``
    only, and a real calendar date. Returns ``None`` for anything else --
    callers treat that as ``generalized_date_unscorable_original``, never as
    a parse the rest of the classification could recover from.
    """
    if original is None or not _ORIGINAL_DATE_PATTERN.match(original):
        return None
    year, month, day = (int(part) for part in original.split("-"))
    try:
        date(year, month, day)
    except ValueError:
        return None
    return (year, month, day)


def _parse_transformed_date(
    transformed: str | None,
) -> tuple[str, int, int | None, int | None] | None:
    """The closed grammar a GENERALIZE date output may take: ``YYYY-MM-DD``
    (day), ``YYYY-MM`` (month) or ``YYYY`` (year). Any other shape --
    including a locale-formatted date, a day-first date, or a malformed
    month/day -- is not a protocol-produced form and returns ``None``
    (``generalized_date_invalid``); the protocol defines no locale or
    day-month-order rule, so no such string can be recovered as valid.
    """
    if not transformed:
        return None
    if match := _YEAR_MONTH_DAY_PATTERN.match(transformed):
        year, month, day = (int(part) for part in match.groups())
        try:
            date(year, month, day)
        except ValueError:
            return None
        return ("day", year, month, day)
    if match := _YEAR_MONTH_PATTERN.match(transformed):
        year, month = (int(part) for part in match.groups())
        if not 1 <= month <= 12:
            return None
        return ("month", year, month, None)
    if match := _YEAR_ONLY_PATTERN.match(transformed):
        return ("year", int(match.group(1)), None, None)
    return None


def classify_generalized_date(
    original: str | None, transformed: str | None, required: str
) -> tuple[UtilityOutcome, str]:
    """Classify one GENERALIZE outcome for a date-shaped category.

    ``original`` is the oracle span's own value; ``transformed`` is what the
    treatment actually produced. ``required`` is the category's own required
    granularity from ``DATE_UTILITY_REQUIRED_GRANULARITY`` (``"day"``,
    ``"month"`` or ``"year"``). The outcome set is deliberately closed --
    ``answerable``/``not_answerable`` only, never a "partial" outcome --
    and the reason is always one of the fixed constants below, never a
    string built from either date value (CLAUDE.md's no-leak invariant: a
    date is disclosure-sensitive content, not safe telemetry).

    Evaluated in this order, first match wins:

    1. an unparseable/impossible ``original`` -> unscorable_original;
    2. a ``transformed`` outside the closed grammar -> invalid;
    3. parsed components disagreeing with ``original`` at the parsed
       granularity -> wrong_value;
    4. day-granularity ``transformed`` -> excess_precision (never credited,
       even though it is technically "correct" -- a day-precision output
       never actually generalized anything, which breaks the GENERALIZE
       contract, so this fails closed rather than rewarding it);
    5. a granularity coarser than ``required`` -> insufficient_granularity;
    6. otherwise -> sufficient_granularity (answerable).
    """
    parsed_original = _parse_original_date(original)
    if parsed_original is None:
        return "not_answerable", "generalized_date_unscorable_original"

    parsed_transformed = _parse_transformed_date(transformed)
    if parsed_transformed is None:
        return "not_answerable", "generalized_date_invalid"

    granularity, t_year, t_month, t_day = parsed_transformed
    o_year, o_month, o_day = parsed_original

    if t_year != o_year:
        return "not_answerable", "generalized_date_wrong_value"
    if granularity in ("month", "day") and t_month != o_month:
        return "not_answerable", "generalized_date_wrong_value"
    if granularity == "day" and t_day != o_day:
        return "not_answerable", "generalized_date_wrong_value"

    if granularity == "day":
        return "not_answerable", "generalized_date_excess_precision"

    if _DATE_GRANULARITY_ORDER[granularity] > _DATE_GRANULARITY_ORDER[required]:
        return "not_answerable", "generalized_date_insufficient_granularity"

    return "answerable", "generalized_date_sufficient_granularity"


@dataclass(frozen=True)
class CategoryUtility:
    category: str
    outcome: UtilityOutcome
    reason: str


@dataclass(frozen=True)
class UtilityScore:
    overall: UtilityOutcome
    by_category: tuple[CategoryUtility, ...]


def _legacy_v3_reference_values(text: str, exclude_spans: list[tuple[int, int]]) -> list[float]:
    """Numeric amounts in ``text`` that fall entirely outside every detected
    span's own offsets -- candidate reference figures (SCHEMA.md's "appended
    line the detector does not match against any of the five frozen
    categories").

    Renamed from ``_reference_values`` (Issue #87 / M3, ``post-pilot-v4``):
    this free-text extraction is the ``post-pilot-v3`` scoring path's own
    mechanism, kept byte-for-byte for historical-corpus scoring under that
    frozen protocol id, and reachable **only** from the v3 branch of
    ``score_utility`` -- pinned by an AST test in
    ``tests/test_experiments_scoring_utility_references_v4.py``. The v4 path
    (``classify_generalized_band_against_references``) never calls this
    function and never reads ``case_input.text`` at all: v4's references
    come exclusively from the oracle's structured
    ``CaseOracle.utility_references``.
    """
    values: list[float] = []
    for match in _AMOUNT_PATTERN.finditer(text):
        start, end = match.span()
        if any(span_start <= start and end <= span_end for span_start, span_end in exclude_spans):
            continue
        values.append(float(match.group()))
    return values


def _parse_strict_original_amount(original: str | None) -> Decimal | None:
    """The oracle span's own numeric value, parsed strictly:
    ``R$ <digits>.<2 digits>`` only. Returns ``None`` for anything else --
    including a Brazilian-formatted amount (``R$ 9.200,00``), a bare number
    with no currency prefix, or an amount with a different decimal
    precision -- callers treat that as
    ``generalized_band_unscorable_original``, never as a parse the rest of
    the classification could recover from (mirrors
    ``_parse_original_date``'s own strictness above).
    """
    if original is None:
        return None
    match = _ORIGINAL_AMOUNT_PATTERN.match(original)
    if match is None:
        return None
    return Decimal(match.group(1))


def _parse_band(transformed: str | None) -> tuple[int, int] | None:
    """The closed grammar a numeric GENERALIZE band may take:
    ``R$ <lower>-<upper>``, both non-negative integers, with ``lower``
    strictly less than ``upper``. Anything else -- a malformed shape, a
    Brazilian-formatted amount, a different currency, an inverted band, or a
    degenerate (zero-width) band -- returns ``None``
    (``generalized_band_invalid``); the strategy that actually produces a
    band (``NumericBandStrategy``) never emits an inverted or degenerate one,
    but this grammar must still be total over every string shape a corrupted
    or future treatment could emit.
    """
    if transformed is None:
        return None
    match = _BAND_STRING_PATTERN.match(transformed)
    if match is None:
        return None
    lower, upper = int(match.group(1)), int(match.group(2))
    if lower >= upper:
        return None
    return lower, upper


def _check_band_fidelity(
    original: str | None, transformed: str | None
) -> tuple[UtilityOutcome, str] | tuple[int, int]:
    """Steps 1-3 of the numeric-band GENERALIZE rule (Issue #85 /
    ``post-pilot-v3``), extracted verbatim so both the frozen v3 sufficiency
    rule (``classify_generalized_band``) and the v4 structured-reference
    rule (``classify_generalized_band_against_references``, Issue #87 / M3)
    share the exact same fidelity check rather than risking the two
    silently drifting apart:

    1. an unparseable ``original`` -> ``("not_answerable",
       "generalized_band_unscorable_original")``, evaluated before the
       band's own shape is even examined;
    2. a ``transformed`` outside the closed grammar, or with ``lower >=
       upper`` (inverted or degenerate) -> ``("not_answerable",
       "generalized_band_invalid")``;
    3. a validly-shaped band that does not contain ``original`` at the
       half-open ``[lower, upper)`` interval ``NumericBandStrategy`` itself
       produces -> ``("not_answerable", "generalized_band_excludes_original")``;
    4. otherwise, the parsed ``(lower, upper)`` pair.

    Callers distinguish a failure from success by the type of the first
    element (a ``str`` outcome vs. an ``int`` bound) -- both are 2-tuples,
    so this is the cheapest total discriminator without inventing a
    dataclass this internal helper does not otherwise need.
    """
    original_amount = _parse_strict_original_amount(original)
    if original_amount is None:
        return "not_answerable", "generalized_band_unscorable_original"

    band = _parse_band(transformed)
    if band is None:
        return "not_answerable", "generalized_band_invalid"

    lower, upper = band
    if not (lower <= original_amount < upper):
        return "not_answerable", "generalized_band_excludes_original"

    return lower, upper


def classify_generalized_band(
    original: str | None, transformed: str | None, references: list[float]
) -> tuple[UtilityOutcome, str]:
    """Classify one GENERALIZE outcome for a numeric-band category under the
    frozen ``post-pilot-v3`` rule (Issue #85).

    ``original`` is the oracle span's own value (never
    ``Transformation.original`` -- the same ground-truth discipline
    ``classify_generalized_date`` already follows, for the same reason: a
    detector misread or a span-matching mismatch must never let a wrong
    transformed band validate against its own wrong original).
    ``transformed`` is what the treatment actually produced. ``references``
    are the candidate reference figures ``_legacy_v3_reference_values``
    found stated elsewhere in the case text.

    **Historical pin (Issue #87 / M3):** this function's signature and
    behavior are frozen exactly as ``post-pilot-v3`` defined them --
    unchanged by the v4 structured-reference rule below, which is a
    separate function (``classify_generalized_band_against_references``),
    not a variant of this one. Every ``post-pilot-v3`` test in
    ``tests/test_experiments_scoring_numeric_band_utility.py`` continues to
    exercise this exact function with these exact semantics.

    Checked in this order, first match wins -- **fidelity before
    sufficiency**: whether the band is even a correct representation of the
    original value is checked before whether it can be resolved against a
    stated reference, so a wrong band can never be rescued into
    ``answerable`` merely because no reference happens to fall inside it
    (the defect this rule replaces):

    1.-3. fidelity, delegated to ``_check_band_fidelity`` (see its own
    docstring for the three sub-cases);
    4. no reference figure at all -> indeterminate, no_reference (never
       vacuously ``answerable`` -- ``all([])`` being ``True`` is exactly the
       defect this rule replaces);
    5. every reference falls strictly outside the band -> answerable,
       decidable; otherwise -> indeterminate, ambiguous (unchanged
       comparison semantics from the pre-``v3`` rule).
    """
    fidelity = _check_band_fidelity(original, transformed)
    if isinstance(fidelity[0], str):
        return fidelity
    lower, upper = fidelity

    if not references:
        return "indeterminate", "generalized_band_no_reference"

    if all(reference < lower or reference >= upper for reference in references):
        return "answerable", "generalized_band_decidable"
    return "indeterminate", "generalized_band_ambiguous"


def _reference_is_decidable(
    operator: ReferenceOperator, amount: Decimal, lower: int, upper: int
) -> bool:
    """Whether one structured reference resolves a numeric band [lower,
    upper) to a single decidable answer (Issue #87 / M3, ``post-pilot-v4``,
    spec section 2's formal rule).

    The band is treated as a half-open interval over the reals; ``operator``
    names the relation the task's real question asks about the original
    value ``x`` against ``amount`` (``r``): ``x > r``, ``x >= r``, ``x < r``
    or ``x <= r``. The question is decidable over the whole band iff every
    ``x`` in ``[lower, upper)`` gives the same answer to that relation --
    equivalently, iff ``r`` never falls strictly inside the *open* interval
    the relation's own boundary would otherwise straddle:

    - ``greater_than``/``less_than_or_equal`` share ``r < lower or r >=
      upper`` -- ``r == lower`` is still ambiguous (some ``x`` in the band
      equal ``lower`` too, so both a "yes" and a "no" occur for these two
      strict-vs-non-strict operators at that exact boundary);
    - ``greater_than_or_equal``/``less_than`` share ``r <= lower or r >=
      upper`` -- ``r == lower`` is already decidable for these two, because
      every ``x >= lower`` in the half-open band satisfies ``x >= r`` (resp.
      fails ``x < r``) uniformly.

    This is exhaustive over ``ReferenceOperator``'s four members (pinned by
    a drift-guard test enumerating every member); no other branch exists,
    so a fifth operator value could only reach here if the enum itself grew
    a member no test updated for.
    """
    if operator in (ReferenceOperator.GREATER_THAN, ReferenceOperator.LESS_THAN_OR_EQUAL):
        return amount < lower or amount >= upper
    if operator in (ReferenceOperator.GREATER_THAN_OR_EQUAL, ReferenceOperator.LESS_THAN):
        return amount <= lower or amount >= upper
    raise AssertionError("unreachable: ReferenceOperator is exhaustively handled above")


def classify_generalized_band_against_references(
    original: str | None,
    transformed: str | None,
    references: Sequence[NumericUtilityReference],
) -> tuple[UtilityOutcome, str]:
    """Classify one GENERALIZE outcome for a numeric-band category under
    ``post-pilot-v4`` (Issue #87 / M3), using structured oracle references
    instead of free-text extraction.

    Shares steps 1-3 (fidelity) byte-for-byte with ``classify_generalized_band``
    via ``_check_band_fidelity``. Step 4: an empty ``references`` sequence
    (no reference stated for this category, or the case never named one at
    all) -> ``("indeterminate", "generalized_band_no_reference")`` -- never
    vacuously ``answerable``, exactly like v3. Step 5: the band is
    ``answerable``/``generalized_band_decidable`` iff *every* reference is
    individually decidable against it (``_reference_is_decidable``);
    otherwise ``indeterminate``/``generalized_band_ambiguous``.

    ``references`` must already be filtered to this call's own category by
    the caller (``score_utility``'s v4 arm passes only
    ``[r for r in oracle.utility_references or [] if r.category == category]``)
    -- this function does not itself filter by category, so a caller that
    passes an unfiltered list would silently contaminate one category's
    decidability with another's reference, which is exactly the "category-
    blind" defect (b) this ticket fixes; the AST/behavioral tests in
    ``tests/test_experiments_scoring_utility_references_v4.py`` pin that
    ``score_utility`` never does that.
    """
    fidelity = _check_band_fidelity(original, transformed)
    if isinstance(fidelity[0], str):
        return fidelity
    lower, upper = fidelity
    return _classify_structured_sufficiency(lower, upper, references)


def classify_generalized_band_against_references_v5(
    original: str | None,
    transformed: str | None,
    references: Sequence[NumericUtilityReference],
) -> tuple[UtilityOutcome, str]:
    """Classify one GENERALIZE outcome for a numeric-band category under
    ``post-pilot-v5`` (Issue #93 / M3): identical structured-reference
    sufficiency rule as ``classify_generalized_band_against_references``
    (``post-pilot-v4``, reused unchanged via ``_classify_structured_sufficiency``
    -- Issue #93's spec: "v5 reuses v4 reference semantics unchanged"), but
    fidelity is checked with the v5 original/band grammar
    (``_check_band_fidelity_v5``), which additionally accepts a
    Brazilian-formatted original amount (Issue #88) and rejects the ASCII/
    trailing-newline defects Issue #91 found in the v3/v4 grammar.
    """
    fidelity = _check_band_fidelity_v5(original, transformed)
    if isinstance(fidelity[0], str):
        return fidelity
    lower, upper = fidelity
    return _classify_structured_sufficiency(lower, upper, references)


class MissingUtilityReferencesError(ValueError):
    """Raised (Issue #87 / M3, ``post-pilot-v4``) when a case whose oracle
    depends on a registered numeric category has a legacy oracle
    (``utility_references is None``) and is scored under a protocol that
    requires structured references. A legacy corpus (``corpus/hr/v1``,
    ``corpus/contracts/v1``) is refused under ``post-pilot-v4`` for exactly
    this reason -- those frozen files are never edited to add the field;
    they are scored under ``post-pilot-v3`` instead (see
    ``scripts/run_hr_v1_pilot.py``/``run_contracts_v1_pilot.py``).
    """


class UnsupportedOriginalAmountFormatError(ValueError):
    """Raised (Issue #93 / M3, ``post-pilot-v5`` only) by the pre-run check
    below when any numeric-category oracle span in a corpus -- **including a
    span belonging to an ``expected_block_request`` case** -- has a value
    outside the closed ``post-pilot-v5`` amount grammar
    (``NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"``,
    ``transformations/generalization.py``).

    Raised before any treatment or provider call, over the *whole* corpus
    (mirroring ``check_corpus_protocol_compatibility``'s own "fail fast, zero
    provider calls" contract): Gate 7 must not author a confirmatory corpus
    against an amount format the treatment/scorer contract does not actually
    support, and a blocked case's own oracle value is exactly as much a part
    of that contract as a disclosed one -- the case's block status has no
    bearing on whether its annotation is well-formed.

    Names only the case id and the category (CLAUDE.md's no-leak invariant)
    -- never the offending value.
    """


class StructuredReferencesRequireV4Error(ValueError):
    """Raised (Issue #87 / M3) when a case whose oracle has opted in to the
    structured ``utility_references`` mechanism -- ``utility_references is
    not None``, an empty list ``[]`` included -- is scored under
    ``post-pilot-v3``, whose scorer has no mechanism to honor declared
    operator/value semantics.

    ``None`` and ``[]`` are not interchangeable here (PR #92 review,
    blocker 1): ``None`` means the oracle never opted in at all (legacy,
    schema-v2) and is compatible with v3's own free-text mechanism. ``[]``
    is an explicit opt-in that declares *no* reference for any category --
    scoring it under v3 would silently fall back to
    ``_legacy_v3_reference_values`` and infer references from free text the
    case author explicitly chose not to declare structurally, exactly the
    text-coupled behavior this opt-in exists to opt out of. Any non-``None``
    ``utility_references`` therefore requires ``post-pilot-v4``, regardless
    of whether the list is empty.
    """


def _check_case_protocol_compatibility(
    oracle: CaseOracle, protocol_id: str, *, case_id: str | None = None
) -> None:
    """The per-case half of Issue #87 / M3's compatibility matrix between a
    corpus case's oracle and a scoring protocol id -- shared by
    ``score_utility`` (one case, post-execution) and
    ``check_corpus_protocol_compatibility`` (a whole corpus, pre-execution)
    so the two can never silently drift apart. Caller must already have
    validated ``protocol_id`` via ``validate_scorable_protocol_id`` -- this
    function assumes it is one of ``SCORABLE_PROTOCOL_IDS``.

    A case whose oracle expects a block never reaches either branch below:
    nothing is ever disclosed for such a case, so no numeric-reference
    semantics are ever exercised regardless of protocol id.
    """
    if oracle.expected_block_request:
        return
    depends_on = set(oracle.answer_depends_on_categories or [])
    numeric_depends_on = depends_on & NUMERIC_BAND_UTILITY_CATEGORIES
    location = f"case {case_id!r}: " if case_id is not None else ""
    if protocol_id in ("post-pilot-v4", "post-pilot-v5"):
        # v5 shares v4's opted-in-oracle requirement verbatim (Issue #93's
        # spec: "same MissingUtilityReferencesError ... rules; keep class
        # name, broaden message to 'v4+'") -- the message below is the only
        # thing that changed for the v4 case versus before this ticket.
        if oracle.utility_references is None and numeric_depends_on:
            raise MissingUtilityReferencesError(
                f"{location}oracle depends on a numeric category but has no "
                "utility_references (legacy schema) -- post-pilot-v4+ requires an "
                "opted-in oracle for a numeric-dependent case"
            )
    elif protocol_id == "post-pilot-v3":
        if oracle.utility_references is not None:
            # `is not None`, never a truthiness check (PR #92 review, blocker
            # 1): an opted-in but empty list ([]) is still an explicit opt-in
            # into the structured mechanism, not "no opinion" -- it must be
            # refused exactly like a non-empty list, never silently treated
            # as legacy and fall back to _legacy_v3_reference_values.
            raise StructuredReferencesRequireV4Error(
                f"{location}oracle has opted in to utility_references (empty or not), "
                "which post-pilot-v3's scorer cannot honor"
            )
    else:
        # Defensive exhaustiveness (Issue #93 / M3 review finding: this used
        # to be an `if/elif` with no `else`, silently treating any future
        # scorable id exactly like v3). Unreachable today -- the caller
        # already validated protocol_id is one of SCORABLE_PROTOCOL_IDS,
        # currently {v3, v4, v5} -- but guards a future id added there
        # without a matching branch here.
        raise UnsupportedScoringProtocolError(
            "protocol_id is a scorable post-pilot protocol id, but "
            "_check_case_protocol_compatibility has no rule registered for it"
        )


def _check_v5_original_amount_formats(cases: Sequence[CorpusCase]) -> None:
    """The ``post-pilot-v5``-only pre-run check (Issue #93 / M3): every
    numeric-category ``ExpectedSpan`` value, in **every** case -- including a
    case whose oracle expects a block -- must parse under the v5 amount
    grammar (``_parse_original_amount_v5``). Raises
    ``UnsupportedOriginalAmountFormatError`` naming only the case id and
    category (never the value) for the first offending span found, in case
    order then span order.

    This is deliberately not folded into ``_check_case_protocol_compatibility``
    above: that function returns immediately for a blocked case (nothing is
    ever disclosed for one, so no *reference* semantics are exercised), but a
    blocked case's oracle span is still an annotation that must be
    well-formed under the grammar the whole pre-Gate-7 checkpoint exists to
    close -- see ``UnsupportedOriginalAmountFormatError``'s own docstring.
    """
    for case in cases:
        for span in case.oracle.expected_spans:
            if span.category not in NUMERIC_BAND_UTILITY_CATEGORIES:
                continue
            if _parse_original_amount_v5(span.value) is None:
                raise UnsupportedOriginalAmountFormatError(
                    f"case {case.input.sample_id!r}: category {span.category!r} has an "
                    "oracle span value outside the post-pilot-v5 supported amount grammar "
                    f"({NUMERIC_AMOUNT_GRAMMAR_ID})"
                )


def check_corpus_protocol_compatibility(cases: Sequence[CorpusCase], protocol_id: str) -> None:
    """Fail-fast, whole-corpus compatibility check (Issue #87 / M3, extended
    by Issue #93 / M3 for ``post-pilot-v5``) between every case in ``cases``
    and ``protocol_id``, called by ``experiments.runner.run_pilot``
    immediately after loading a corpus and before any treatment/provider
    call -- an incompatible corpus/protocol pairing costs zero provider
    calls, not a partial run that fails midway.

    Raises ``UnknownProtocolIdError``/``UnsupportedScoringProtocolError``
    (via ``validate_scorable_protocol_id``) if ``protocol_id`` itself is not
    a frozen, currently-scorable id, before looking at any case at all.
    Otherwise raises the first ``MissingUtilityReferencesError``/
    ``StructuredReferencesRequireV4Error`` any case in ``cases`` would raise
    at score time (``_check_case_protocol_compatibility``) -- so a
    caller never needs to execute a single case to discover the corpus is
    incompatible with the protocol it asked for. Under ``post-pilot-v5``
    only, additionally raises ``UnsupportedOriginalAmountFormatError`` if any
    case's numeric-category oracle span value is outside the v5 amount
    grammar (``_check_v5_original_amount_formats``), blocked cases included.
    """
    validate_scorable_protocol_id(protocol_id)
    for case in cases:
        _check_case_protocol_compatibility(case.oracle, protocol_id, case_id=case.input.sample_id)
    if protocol_id == "post-pilot-v5":
        _check_v5_original_amount_formats(cases)


def score_utility(
    case_input: CorpusCaseInput,
    oracle: CaseOracle,
    result: DisclosureResult,
    treatment: Treatment,
    *,
    protocol_id: str,
) -> UtilityScore:
    """Score utility for one case execution under ``protocol_id`` (Issue #87
    / M3, ``post-pilot-v4``: ``protocol_id`` is a required keyword-only
    argument, with no default -- a caller must always say which frozen
    scoring protocol it wants, never inherit one implicitly).

    ``protocol_id`` must be one of ``SCORABLE_PROTOCOL_IDS``
    (``post-pilot-v3``/``post-pilot-v4``/``post-pilot-v5`` today); anything
    else raises via ``validate_scorable_protocol_id`` before any scoring
    happens. v3 extracts free-text reference figures from ``case_input.text``
    (``_legacy_v3_reference_values``, frozen, historical-corpus-compatible);
    v4 reads the oracle's own structured ``utility_references`` and never
    touches ``case_input.text`` for this purpose at all (Issue #87's fix for
    the category-blind, text-coupled v3 mechanism); v5 keeps v4's structured
    reference semantics and changes only the numeric amount/band grammar.
    """
    validate_scorable_protocol_id(protocol_id)

    if oracle.expected_block_request:
        # A case whose oracle expects a block never has an expected_answer
        # to score at all (CaseOracle's own validator forbids the
        # combination) -- utility is not applicable, not a failure.
        return UtilityScore(overall="not_applicable", by_category=())

    depends_on = oracle.answer_depends_on_categories or []
    _check_case_protocol_compatibility(oracle, protocol_id, case_id=oracle.sample_id)

    if result.status == "blocked":
        # The oracle did not expect this case to block, but this run
        # produced one anyway: nothing was transmitted, so every dependent
        # category is unanswerable -- and this is reported distinctly
        # ("unexpected_block"), not folded into "removed"/"pseudonymized".
        by_category = tuple(
            CategoryUtility(category=category, outcome="not_answerable", reason="unexpected_block")
            for category in depends_on
        )
        return UtilityScore(
            overall="not_answerable" if by_category else "not_applicable", by_category=by_category
        )

    if treatment is Treatment.DIRECT:
        by_category = tuple(
            CategoryUtility(category=category, outcome="answerable", reason="direct_disclosure")
            for category in depends_on
        )
        return UtilityScore(
            overall="answerable" if by_category else "not_applicable", by_category=by_category
        )

    transformations = resolve_span_transformations(oracle, result, treatment)
    exclude_spans = [(span.start, span.end) for span in oracle.expected_spans]
    # v3-only: free-text reference extraction, computed unconditionally here
    # exactly as the frozen post-pilot-v3 scorer always did (whether or not
    # a numeric-band GENERALIZE is actually present in this case) -- kept
    # byte-for-byte for historical-corpus scoring. v4 never computes or
    # reads this; it takes its references from the oracle's own
    # ``utility_references`` instead, filtered by category at the point of
    # use below.
    legacy_references = (
        _legacy_v3_reference_values(case_input.text, exclude_spans)
        if protocol_id == "post-pilot-v3"
        else None
    )
    reconstructable_categories = {
        expectation.category
        for expectation in oracle.reconstruction
        if expectation.expected_reconstructable
    }

    # Pairs the oracle span alongside its matched transformation (rather than
    # the transformation alone) so a category's ground-truth *value* --
    # never a transformation's own, treatment-reported `original` field --
    # is what any oracle-value-dependent rule (classify_generalized_date
    # below) is judged against. `transformation.original` reflects whatever
    # the detector/treatment actually read, which is exactly the value this
    # scorer must NOT trust as ground truth (Gate 6 review finding, PR #86):
    # a detector misread or a span-matching mismatch would otherwise let a
    # wrong transformed date validate against its own wrong original,
    # silently passing the oracle<->scorer coherence this scorer exists to
    # check.
    by_category_span_transformations: dict[str, list] = {}
    for span, transformation in zip(oracle.expected_spans, transformations):
        by_category_span_transformations.setdefault(span.category, []).append(
            (span, transformation)
        )

    category_scores: list[CategoryUtility] = []
    for category in depends_on:
        entries = by_category_span_transformations.get(category, [])
        if not entries or any(transformation is None for _, transformation in entries):
            category_scores.append(
                CategoryUtility(category=category, outcome="not_answerable", reason="unscorable")
            )
            continue

        outcomes: list[tuple[str, str]] = []
        for span, transformation in entries:
            action = transformation.action
            if action is DisclosureAction.PRESERVE:
                outcomes.append(("answerable", "preserved"))
            elif action is DisclosureAction.GENERALIZE:
                required_granularity = DATE_UTILITY_REQUIRED_GRANULARITY.get(category)
                if required_granularity is not None:
                    outcomes.append(
                        classify_generalized_date(
                            span.value,
                            transformation.transformed,
                            required_granularity,
                        )
                    )
                elif category in NUMERIC_BAND_UTILITY_CATEGORIES:
                    if protocol_id == "post-pilot-v3":
                        outcomes.append(
                            classify_generalized_band(
                                span.value,
                                transformation.transformed,
                                legacy_references,
                            )
                        )
                    elif protocol_id in ("post-pilot-v4", "post-pilot-v5"):
                        # Structured references only, this category's own --
                        # never an unfiltered list -- so a reference stated
                        # for a different numeric category can never
                        # contaminate this category's decidability (Issue
                        # #87 finding (b)). Shared by v4 and v5 (Issue #93's
                        # spec: "v5 reuses v4 reference semantics
                        # unchanged"); only the fidelity/grammar underneath
                        # differs (Issue #88/#91).
                        category_references = [
                            reference
                            for reference in (oracle.utility_references or [])
                            if reference.category == category
                        ]
                        band_classifier = (
                            classify_generalized_band_against_references_v5
                            if protocol_id == "post-pilot-v5"
                            else classify_generalized_band_against_references
                        )
                        outcomes.append(
                            band_classifier(
                                span.value,
                                transformation.transformed,
                                category_references,
                            )
                        )
                    else:
                        # Defensive exhaustiveness (Issue #93 / M3 review
                        # finding: this used to be an unconditional `else`
                        # treating any non-v3 id exactly like v4, which would
                        # have silently reused v4 semantics for a future
                        # scorable id added without a matching branch here).
                        # Unreachable today: the caller already validated
                        # protocol_id is one of SCORABLE_PROTOCOL_IDS,
                        # currently {v3, v4, v5}.
                        raise UnsupportedScoringProtocolError(
                            "protocol_id is a scorable post-pilot protocol id, but "
                            "the numeric-band GENERALIZE outcome dispatch has no rule "
                            "registered for it"
                        )
                else:
                    # Fail closed (Issue #85's third out-of-scope finding):
                    # a category with neither a date nor a numeric-band
                    # registry entry must never silently inherit either
                    # rule's semantics. Unreachable today -- every
                    # registered category is one or the other, pinned by
                    # this module's drift guard test.
                    outcomes.append(("not_answerable", "generalized_category_unregistered"))
            elif action is DisclosureAction.PSEUDONYMIZE:
                if category in reconstructable_categories and result.reconstruction_required:
                    outcomes.append(("answerable", "pseudonymized_but_reconstructable"))
                else:
                    outcomes.append(("not_answerable", "pseudonymized_not_reconstructable"))
            elif action is DisclosureAction.REMOVE:
                outcomes.append(("not_answerable", "removed"))
            else:
                outcomes.append(("not_answerable", "unscorable_action"))

        if any(outcome == "not_answerable" for outcome, _ in outcomes):
            final: UtilityOutcome = "not_answerable"
        elif any(outcome == "indeterminate" for outcome, _ in outcomes):
            final = "indeterminate"
        else:
            final = "answerable"
        reason = ";".join(sorted({reason for _, reason in outcomes}))
        category_scores.append(CategoryUtility(category=category, outcome=final, reason=reason))

    if not category_scores:
        overall: UtilityOutcome = "not_applicable"
    elif any(c.outcome == "not_answerable" for c in category_scores):
        overall = "not_answerable"
    elif any(c.outcome == "indeterminate" for c in category_scores):
        overall = "indeterminate"
    else:
        overall = "answerable"

    return UtilityScore(overall=overall, by_category=tuple(category_scores))
