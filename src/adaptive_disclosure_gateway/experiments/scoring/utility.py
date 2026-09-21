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
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import DisclosureAction, DisclosureResult, Treatment

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


def _reference_values(text: str, exclude_spans: list[tuple[int, int]]) -> list[float]:
    """Numeric amounts in ``text`` that fall entirely outside every detected
    span's own offsets -- candidate reference figures (SCHEMA.md's "appended
    line the detector does not match against any of the five frozen
    categories").
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


def classify_generalized_band(
    original: str | None, transformed: str | None, references: list[float]
) -> tuple[UtilityOutcome, str]:
    """Classify one GENERALIZE outcome for a numeric-band category
    (Issue #85 / ``post-pilot-v3``).

    ``original`` is the oracle span's own value (never
    ``Transformation.original`` -- the same ground-truth discipline
    ``classify_generalized_date`` already follows, for the same reason: a
    detector misread or a span-matching mismatch must never let a wrong
    transformed band validate against its own wrong original).
    ``transformed`` is what the treatment actually produced. ``references``
    are the candidate reference figures ``_reference_values`` found stated
    elsewhere in the case text.

    Checked in this order, first match wins -- **fidelity before
    sufficiency**: whether the band is even a correct representation of the
    original value is checked before whether it can be resolved against a
    stated reference, so a wrong band can never be rescued into
    ``answerable`` merely because no reference happens to fall inside it
    (the defect this rule replaces):

    1. an unparseable ``original`` -> unscorable_original, evaluated before
       the band's own shape is even examined (an unscorable original makes
       the transformed value unevaluable regardless of its own shape);
    2. a ``transformed`` outside the closed grammar, or with ``lower >=
       upper`` (inverted or degenerate) -> invalid;
    3. a validly-shaped band that does not contain ``original`` at the
       half-open ``[lower, upper)`` interval ``NumericBandStrategy`` itself
       produces -> excludes_original;
    4. no reference figure at all -> indeterminate, no_reference (never
       vacuously ``answerable`` -- ``all([])`` being ``True`` is exactly the
       defect this rule replaces);
    5. every reference falls strictly outside the band -> answerable,
       decidable; otherwise -> indeterminate, ambiguous (unchanged
       comparison semantics from the pre-``v3`` rule).
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

    if not references:
        return "indeterminate", "generalized_band_no_reference"

    if all(reference < lower or reference >= upper for reference in references):
        return "answerable", "generalized_band_decidable"
    return "indeterminate", "generalized_band_ambiguous"


def score_utility(
    case_input: CorpusCaseInput,
    oracle: CaseOracle,
    result: DisclosureResult,
    treatment: Treatment,
) -> UtilityScore:
    if oracle.expected_block_request:
        # A case whose oracle expects a block never has an expected_answer
        # to score at all (CaseOracle's own validator forbids the
        # combination) -- utility is not applicable, not a failure.
        return UtilityScore(overall="not_applicable", by_category=())

    depends_on = oracle.answer_depends_on_categories or []

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
    references = _reference_values(case_input.text, exclude_spans)
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
                    outcomes.append(
                        classify_generalized_band(
                            span.value,
                            transformation.transformed,
                            references,
                        )
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
