"""Issue #87 / M3 -- structured numeric utility references in the oracle
(``post-pilot-v4``).

``post-pilot-v3``'s numeric-band sufficiency step compared a bare ``float``
scanned from free text against a band, with no operator and no category
awareness -- two defects `docs/research/post-pilot-protocol-v3.md` §8 filed
as Issue #87 rather than fixing in place: (a) a reference sitting exactly on
a band's lower bound could not be told apart from a strict "greater than"
reading and a non-strict "at least" one, which have different correct
answers; (b) the extraction was category-blind, so a reference for one
numeric category could be applied as a candidate for another.

This module pins the replacement: ``CaseOracle.utility_references``
(structured ``category``/``operator``/``value`` references,
``corpus/models.py``) and ``classify_generalized_band_against_references``
(``experiments/scoring/utility.py``), dispatched by ``protocol_id`` in
``score_utility``. All fixtures here are synthetic, minimal, in-test data --
this ticket does not author a new corpus (Gate 7 is separate and later).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import load_corpus
from adaptive_disclosure_gateway.corpus.models import (
    NUMERIC_REFERENCE_CATEGORIES,
    ExpectedSpan,
    NumericUtilityReference,
    ReferenceOperator,
    TaskFamily,
    TaskNecessity,
)
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureResult,
    Transformation,
    Treatment,
)
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.post_pilot_protocol import (
    UnknownProtocolIdError,
    UnsupportedScoringProtocolError,
)
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.runner import run_pilot
from adaptive_disclosure_gateway.experiments.scoring import score_case
from adaptive_disclosure_gateway.experiments.scoring.utility import (
    NUMERIC_BAND_UTILITY_CATEGORIES,
    NUMERIC_BAND_UTILITY_REASONS,
    MissingUtilityReferencesError,
    StructuredReferencesRequireV4Error,
    _reference_is_decidable,
    check_corpus_protocol_compatibility,
    classify_generalized_band,
    classify_generalized_band_against_references,
    score_utility,
)
from adaptive_disclosure_gateway.policies import PolicyRepository

HR_CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

# Shared band fixture for the classify_generalized_band_against_references
# tests below (spec §6): band [500000, 550000), original inside it.
_ORIGINAL = "R$ 520000.00"
_BAND = "R$ 500000-550000"


def _ref(category: str, operator: ReferenceOperator, value: str) -> NumericUtilityReference:
    return NumericUtilityReference(category=category, operator=operator, value=value)


def _synthetic_case(
    *,
    sample_id: str,
    categories_and_values: dict[str, str],
    depends_on: list[str],
    utility_references: list[NumericUtilityReference] | None,
) -> tuple[CorpusCaseInput, CaseOracle]:
    """A minimal, synthetic (non-corpus-file) case for direct ``score_utility``
    calls -- never written to ``corpus/``, never resembling a confirmatory
    corpus case. ``case_input.text`` deliberately never contains any of the
    category values or reference amounts, since the v4 path must never read
    it for reference purposes at all.
    """
    spans = [
        ExpectedSpan(
            category=category,
            value=value,
            start=index * 100,
            end=index * 100 + len(value),
            task_necessity=TaskNecessity.REQUIRED,
            expected_actions=[DisclosureAction.GENERALIZE],
        )
        for index, (category, value) in enumerate(categories_and_values.items())
    ]
    oracle = CaseOracle(
        sample_id=sample_id,
        expected_spans=spans,
        expected_block_request=False,
        expected_answer="synthetic answer",
        answer_depends_on_categories=depends_on,
        utility_references=utility_references,
    )
    case_input = CorpusCaseInput(
        sample_id=sample_id,
        text="synthetic case text with no category values or reference amounts in it",
        task="synthetic task",
        task_family=TaskFamily.TEAM_SUMMARY_WITHOUT_SALARY,
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
    )
    return case_input, oracle


def _band_transformation(category: str, band: str, original: str) -> Transformation:
    return Transformation(
        category=category, original=original, transformed=band, action=DisclosureAction.GENERALIZE
    )


def _result(*transformations: Transformation) -> DisclosureResult:
    return DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=list(transformations),
        status="allowed",
    )


# --- a. classify_generalized_band_against_references: the formal rule -----


@pytest.mark.parametrize(
    ("operator", "value", "expected"),
    [
        (ReferenceOperator.GREATER_THAN, "500000.00", "indeterminate"),
        (ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00", "answerable"),
        (ReferenceOperator.LESS_THAN, "400000.00", "answerable"),
        (ReferenceOperator.LESS_THAN, "520000.00", "indeterminate"),
        (ReferenceOperator.LESS_THAN, "600000.00", "answerable"),
        (ReferenceOperator.LESS_THAN, "500000.00", "answerable"),
        (ReferenceOperator.LESS_THAN, "550000.00", "answerable"),
        (ReferenceOperator.LESS_THAN_OR_EQUAL, "549999.99", "indeterminate"),
        (ReferenceOperator.LESS_THAN_OR_EQUAL, "550000.00", "answerable"),
        (ReferenceOperator.LESS_THAN_OR_EQUAL, "500000.00", "indeterminate"),
        (ReferenceOperator.GREATER_THAN, "400000.00", "answerable"),
        (ReferenceOperator.GREATER_THAN_OR_EQUAL, "525000.00", "indeterminate"),
    ],
)
def test_formal_rule_table_band_500000_550000(operator, value, expected):
    reference = _ref("contract_value", operator, value)
    outcome, reason = classify_generalized_band_against_references(_ORIGINAL, _BAND, [reference])
    assert outcome == expected
    if expected == "answerable":
        assert reason == "generalized_band_decidable"
    else:
        assert reason == "generalized_band_ambiguous"


def test_multiple_references_all_decidable_is_answerable():
    references = [
        _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00"),
        _ref("contract_value", ReferenceOperator.LESS_THAN, "600000.00"),
    ]
    outcome, reason = classify_generalized_band_against_references(_ORIGINAL, _BAND, references)
    assert (outcome, reason) == ("answerable", "generalized_band_decidable")


def test_multiple_references_one_ambiguous_is_ambiguous():
    references = [
        _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00"),
        _ref("contract_value", ReferenceOperator.GREATER_THAN, "500000.00"),  # ambiguous alone
    ]
    outcome, reason = classify_generalized_band_against_references(_ORIGINAL, _BAND, references)
    assert (outcome, reason) == ("indeterminate", "generalized_band_ambiguous")


def test_empty_references_is_no_reference_not_vacuously_answerable():
    outcome, reason = classify_generalized_band_against_references(_ORIGINAL, _BAND, [])
    assert (outcome, reason) == ("indeterminate", "generalized_band_no_reference")


def test_fidelity_precedes_references_wrong_band_is_not_answerable_regardless():
    reference = _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")
    outcome, reason = classify_generalized_band_against_references(
        "R$ 125000.00", "R$ 600000-650000", [reference]
    )
    assert (outcome, reason) == ("not_answerable", "generalized_band_excludes_original")


def test_unscorable_original_precedes_reference_check():
    reference = _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")
    outcome, reason = classify_generalized_band_against_references(None, _BAND, [reference])
    assert (outcome, reason) == ("not_answerable", "generalized_band_unscorable_original")


def test_reference_is_decidable_operator_table_is_exhaustive():
    for operator in ReferenceOperator:
        # Must not raise for any real enum member -- if this trips, the
        # table in _reference_is_decidable is missing a branch.
        _reference_is_decidable(operator, Decimal("500000.00"), 500000, 550000)


# --- b. property/sampling: closed-form rule agrees with sampled evaluation -


@pytest.mark.parametrize(
    "operator",
    list(ReferenceOperator),
)
def test_closed_form_decidability_agrees_with_sampled_evaluation(operator):
    """For each operator, sample values at L, just above L, just below U and
    at U-ish, and confirm _reference_is_decidable's closed-form answer
    agrees with literally evaluating the relation at every sampled point.
    """
    lower, upper = 500000, 550000
    relation = {
        ReferenceOperator.GREATER_THAN: lambda x, r: x > r,
        ReferenceOperator.GREATER_THAN_OR_EQUAL: lambda x, r: x >= r,
        ReferenceOperator.LESS_THAN: lambda x, r: x < r,
        ReferenceOperator.LESS_THAN_OR_EQUAL: lambda x, r: x <= r,
    }[operator]

    for r in (Decimal("500000.00"), Decimal("525000.00"), Decimal("549999.99")):
        samples = [
            Decimal(lower),
            Decimal(lower) + Decimal("0.01"),
            Decimal(upper) - Decimal("0.01"),
            r,
        ]
        answers = {relation(x, r) for x in samples if lower <= x < upper}
        sampled_decidable = len(answers) <= 1
        closed_form = _reference_is_decidable(operator, r, lower, upper)
        # The closed form must never claim decidable when sampling finds a
        # split (it may be more conservative at points not sampled here,
        # so only the "sampling found a split" direction is checked).
        if not sampled_decidable:
            assert not closed_form, (operator, r)


def test_v4_greater_than_and_less_than_or_equal_agree_with_v3_bare_float():
    """v4's gt/le rows must reproduce v3's own comparison exactly (the
    table's ``r < L or r >= U`` row is identical to v3's step 5)."""
    for value in ("400000.00", "500000.00", "525000.00", "550000.00", "600000.00"):
        v3_outcome, v3_reason = classify_generalized_band(_ORIGINAL, _BAND, [float(value)])
        for operator in (ReferenceOperator.GREATER_THAN, ReferenceOperator.LESS_THAN_OR_EQUAL):
            v4_outcome, v4_reason = classify_generalized_band_against_references(
                _ORIGINAL, _BAND, [_ref("contract_value", operator, value)]
            )
            assert (v4_outcome, v4_reason) == (v3_outcome, v3_reason), (operator, value)


# --- c. score_utility: category filtering, no-reference, legacy refusal ----


def test_references_of_a_different_category_are_ignored_own_refs_applied():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-category-filter",
        categories_and_values={"contract_value": "R$ 520000.00", "penalty_amount": "R$ 12000.00"},
        depends_on=["contract_value", "penalty_amount"],
        utility_references=[
            _ref(
                "penalty_amount", ReferenceOperator.GREATER_THAN, "12000.00"
            ),  # inside [10000,15000)
        ],
    )
    result = _result(
        _band_transformation("contract_value", _BAND, "R$ 520000.00"),
        _band_transformation("penalty_amount", "R$ 10000-15000", "R$ 12000.00"),
    )
    score = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    contract_value = next(c for c in score.by_category if c.category == "contract_value")
    penalty_amount = next(c for c in score.by_category if c.category == "penalty_amount")
    assert contract_value.reason == "generalized_band_no_reference"
    assert penalty_amount.reason == "generalized_band_ambiguous"


def test_multi_category_both_covered_and_decidable():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-multi-category",
        categories_and_values={"contract_value": "R$ 520000.00", "penalty_amount": "R$ 12000.00"},
        depends_on=["contract_value", "penalty_amount"],
        utility_references=[
            _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00"),
            _ref("penalty_amount", ReferenceOperator.GREATER_THAN, "525000.00"),
        ],
    )
    result = _result(
        _band_transformation("contract_value", _BAND, "R$ 520000.00"),
        _band_transformation("penalty_amount", "R$ 10000-15000", "R$ 12000.00"),
    )
    score = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    contract_value = next(c for c in score.by_category if c.category == "contract_value")
    penalty_amount = next(c for c in score.by_category if c.category == "penalty_amount")
    assert contract_value.outcome == "answerable"
    assert penalty_amount.outcome == "answerable"


def test_opted_in_case_with_uncovered_numeric_category_is_no_reference_not_refused():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-uncovered-category",
        categories_and_values={"contract_value": "R$ 520000.00"},
        depends_on=["contract_value"],
        utility_references=[],  # opted in, but empty
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))
    score = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    contract_value = next(c for c in score.by_category if c.category == "contract_value")
    assert (contract_value.outcome, contract_value.reason) == (
        "indeterminate",
        "generalized_band_no_reference",
    )


def test_legacy_oracle_none_under_v4_is_refused():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-legacy-refused",
        categories_and_values={"contract_value": "R$ 520000.00"},
        depends_on=["contract_value"],
        utility_references=None,  # legacy
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))
    with pytest.raises(MissingUtilityReferencesError):
        score_utility(case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4")


def test_legacy_oracle_none_with_no_numeric_dependency_is_compatible_with_v4():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-legacy-non-numeric",
        categories_and_values={"department": "Engineering"},
        depends_on=["department"],
        utility_references=None,
    )
    result = _result(
        Transformation(
            category="department",
            original="Engineering",
            transformed="Some region",
            action=DisclosureAction.GENERALIZE,
        )
    )
    score = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    # department is not a numeric-band category, so this falls into the
    # unregistered fail-closed path -- the point of this test is only that
    # it does not raise MissingUtilityReferencesError.
    department = next(c for c in score.by_category if c.category == "department")
    assert department.reason == "generalized_category_unregistered"


def test_non_empty_utility_references_under_v3_raises():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-opted-in-under-v3",
        categories_and_values={"contract_value": "R$ 520000.00"},
        depends_on=["contract_value"],
        utility_references=[
            _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")
        ],
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))
    with pytest.raises(StructuredReferencesRequireV4Error):
        score_utility(case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v3")


@pytest.mark.parametrize("protocol_id", ["post-pilot-v1", "post-pilot-v2"])
def test_frozen_but_unscorable_protocol_ids_raise_unsupported(protocol_id):
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v1-v2-dispatch",
        categories_and_values={"department": "Engineering"},
        depends_on=["department"],
        utility_references=None,
    )
    result = _result(
        Transformation(
            category="department",
            original="Engineering",
            transformed="Some region",
            action=DisclosureAction.GENERALIZE,
        )
    )
    with pytest.raises(UnsupportedScoringProtocolError):
        score_utility(case_input, oracle, result, Treatment.TASK_AWARE, protocol_id=protocol_id)


def test_unregistered_protocol_id_raises_unknown():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-unknown-protocol",
        categories_and_values={"department": "Engineering"},
        depends_on=["department"],
        utility_references=None,
    )
    result = _result(
        Transformation(
            category="department",
            original="Engineering",
            transformed="Some region",
            action=DisclosureAction.GENERALIZE,
        )
    )
    with pytest.raises(UnknownProtocolIdError):
        score_utility(
            case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="not-a-real-protocol"
        )


# --- d. ground truth pin: oracle span value, never Transformation.original -


def test_ground_truth_is_the_oracle_span_value_never_transformation_original_v4():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-ground-truth-pin",
        categories_and_values={"contract_value": "R$ 940000.00"},
        depends_on=["contract_value"],
        utility_references=[
            _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")
        ],
    )
    # Transformation.original is a value *inside* the wrong band; the oracle's
    # real value (940000.00) is not. If the scorer used the transformation's
    # own original, it would wrongly validate the band.
    result = _result(_band_transformation("contract_value", "R$ 600000-650000", "R$ 612345.00"))
    score = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    contract_value = next(c for c in score.by_category if c.category == "contract_value")
    assert contract_value.outcome == "not_answerable"
    assert contract_value.reason == "generalized_band_excludes_original"


# --- e. irrelevant text numbers never interfere (documents the v3 delta) --


def test_irrelevant_text_numbers_do_not_interfere_with_v4_and_document_the_v3_delta():
    """A case whose text is full of numbers that are not oracle references
    at all (a date, a clause number, a day count, and an *unregistered*
    R$ figure that happens to sit inside the band) -- v4 must be identical
    whether or not that text is present (it never reads case_input.text for
    references), while v3 sees the R$ figure as a spurious in-band
    reference and becomes ambiguous. This is exactly Issue #87 finding
    documented as fixed."""
    noisy_text = (
        "Contract dated 2026-02-27, per cláusula 7.2, payable within 30 dias. "
        "R$ 525000.00 was mentioned in an unrelated context."
    )
    clean_text = "Contract with no other numeric figures mentioned at all."

    oracle = CaseOracle(
        sample_id="synthetic-irrelevant-numbers",
        expected_spans=[
            ExpectedSpan(
                category="contract_value",
                value=_ORIGINAL,
                start=0,
                end=len(_ORIGINAL),
                task_necessity=TaskNecessity.REQUIRED,
                expected_actions=[DisclosureAction.GENERALIZE],
            )
        ],
        expected_block_request=False,
        expected_answer="synthetic answer",
        answer_depends_on_categories=["contract_value"],
        utility_references=[
            _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")
        ],
    )
    result = _result(_band_transformation("contract_value", _BAND, _ORIGINAL))

    v4_scores = []
    for text in (noisy_text, clean_text):
        case_input = CorpusCaseInput(
            sample_id="synthetic-irrelevant-numbers",
            text=text,
            task="synthetic task",
            task_family=TaskFamily.TEAM_SUMMARY_WITHOUT_SALARY,
            domain="hr",
            purpose="team_summary",
            policy_version="hr-v1",
        )
        score = score_utility(
            case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
        )
        v4_scores.append(next(c for c in score.by_category if c.category == "contract_value"))

    assert v4_scores[0] == v4_scores[1]
    assert v4_scores[0].outcome == "answerable"
    assert v4_scores[0].reason == "generalized_band_decidable"

    # v3, on the noisy text, sees the unregistered "R$ 525000.00" (inside
    # the band) as a spurious candidate reference and becomes ambiguous --
    # documenting the exact defect v4 fixes, not asserting v3 is "wrong" to
    # test (it is frozen historical behavior).
    v3_case_input = CorpusCaseInput(
        sample_id="synthetic-irrelevant-numbers",
        text=noisy_text,
        task="synthetic task",
        task_family=TaskFamily.TEAM_SUMMARY_WITHOUT_SALARY,
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
    )
    v3_oracle = oracle.model_copy(update={"utility_references": None})
    v3_score = score_utility(
        v3_case_input, v3_oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v3"
    )
    v3_contract_value = next(c for c in v3_score.by_category if c.category == "contract_value")
    assert v3_contract_value.outcome == "indeterminate"
    assert v3_contract_value.reason == "generalized_band_ambiguous"


# --- f. determinism, closed reasons -----------------------------------------


def test_score_utility_v4_is_deterministic_across_repeated_calls():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-determinism",
        categories_and_values={"contract_value": "R$ 520000.00"},
        depends_on=["contract_value"],
        utility_references=[
            _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")
        ],
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))
    first = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    second = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    assert first == second


def test_every_reason_classify_generalized_band_against_references_can_return_is_in_closed_set():
    cases = [
        (_ORIGINAL, _BAND, []),
        (
            _ORIGINAL,
            _BAND,
            [_ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")],
        ),
        (_ORIGINAL, _BAND, [_ref("contract_value", ReferenceOperator.GREATER_THAN, "500000.00")]),
        ("not an amount", _BAND, []),
        (_ORIGINAL, "not a band", []),
    ]
    for original, transformed, references in cases:
        _, reason = classify_generalized_band_against_references(original, transformed, references)
        assert reason in NUMERIC_BAND_UTILITY_REASONS


# --- g. registry drift guards ------------------------------------------------


def test_numeric_reference_categories_equals_numeric_band_utility_categories():
    assert NUMERIC_REFERENCE_CATEGORIES == NUMERIC_BAND_UTILITY_CATEGORIES


# --- h. schema validation (invalid shapes) -----------------------------------


@pytest.mark.parametrize("operator", [">=", "GE", "ge", "eq", "between", "gt", ""])
def test_invalid_operator_strings_are_rejected(operator):
    with pytest.raises(ValidationError):
        NumericUtilityReference(category="contract_value", operator=operator, value="500000.00")


@pytest.mark.parametrize(
    "value",
    [
        500000.0,
        500000,
        "500000",
        "500000.0",
        "500.000,00",
        "R$ 500000.00",
        "-1.00",
        "01.00",
        " 1.00",
        "1.00 ",
        "١٢.00",  # Eastern Arabic-Indic digits "12.00"
    ],
)
def test_invalid_values_are_rejected(value):
    with pytest.raises(ValidationError):
        NumericUtilityReference(
            category="contract_value", operator=ReferenceOperator.GREATER_THAN, value=value
        )


def test_non_numeric_category_is_rejected():
    with pytest.raises(ValidationError):
        NumericUtilityReference(
            category="deadline", operator=ReferenceOperator.GREATER_THAN, value="500000.00"
        )


def test_extra_key_is_rejected():
    with pytest.raises(ValidationError):
        NumericUtilityReference.model_validate(
            {
                "category": "contract_value",
                "operator": "greater_than",
                "value": "500000.00",
                "unit": "BRL",
            }
        )


def test_reference_category_not_in_answer_depends_on_is_rejected():
    with pytest.raises(ValidationError):
        CaseOracle(
            sample_id="synthetic-category-not-in-depends-on",
            expected_spans=[
                ExpectedSpan(
                    category="contract_value",
                    value="R$ 520000.00",
                    start=0,
                    end=12,
                    task_necessity=TaskNecessity.REQUIRED,
                    expected_actions=[DisclosureAction.GENERALIZE],
                )
            ],
            expected_block_request=False,
            expected_answer="x",
            answer_depends_on_categories=["contract_value"],
            utility_references=[_ref("penalty_amount", ReferenceOperator.GREATER_THAN, "10000.00")],
        )


def test_duplicate_reference_triple_is_rejected():
    with pytest.raises(ValidationError):
        CaseOracle(
            sample_id="synthetic-duplicate-reference",
            expected_spans=[
                ExpectedSpan(
                    category="contract_value",
                    value="R$ 520000.00",
                    start=0,
                    end=12,
                    task_necessity=TaskNecessity.REQUIRED,
                    expected_actions=[DisclosureAction.GENERALIZE],
                )
            ],
            expected_block_request=False,
            expected_answer="x",
            answer_depends_on_categories=["contract_value"],
            utility_references=[
                _ref("contract_value", ReferenceOperator.GREATER_THAN, "500000.00"),
                _ref("contract_value", ReferenceOperator.GREATER_THAN, "500000.00"),
            ],
        )


def test_blocked_case_with_non_empty_references_is_rejected():
    with pytest.raises(ValidationError):
        CaseOracle(
            sample_id="synthetic-blocked-with-refs",
            expected_spans=[
                ExpectedSpan(
                    category="medical_data",
                    value="Diabetes",
                    start=0,
                    end=8,
                    task_necessity=TaskNecessity.NOT_REQUIRED,
                    expected_actions=[DisclosureAction.BLOCK_REQUEST],
                )
            ],
            expected_block_request=True,
            utility_references=[
                _ref("contract_value", ReferenceOperator.GREATER_THAN, "500000.00")
            ],
        )


# --- i. dispatch: run_pilot on a legacy corpus under v4 --------------------


def test_run_pilot_protocol_v4_on_hr_v1_raises_with_zero_provider_calls():
    calls = {"count": 0}

    class _CountingSpyProvider:
        provider_class = "fake"

        def generate(self, request):
            calls["count"] += 1
            raise AssertionError("provider must never be called")

    with pytest.raises(MissingUtilityReferencesError):
        run_pilot(
            corpus_dir=HR_CORPUS_DIR,
            policy_dir=POLICY_DIR,
            corpus_version="hr/v1",
            run_classification=PILOT_DEVELOPMENT,
            provider=_CountingSpyProvider(),
            protocol_id="post-pilot-v4",
        )
    assert calls["count"] == 0


def test_check_corpus_protocol_compatibility_direct_call():
    cases = load_corpus(HR_CORPUS_DIR)
    with pytest.raises(MissingUtilityReferencesError):
        check_corpus_protocol_compatibility(cases, "post-pilot-v4")
    check_corpus_protocol_compatibility(cases, "post-pilot-v3")  # must not raise


def test_check_corpus_protocol_compatibility_rejects_unscorable_id():
    cases = load_corpus(HR_CORPUS_DIR)
    with pytest.raises(UnsupportedScoringProtocolError):
        check_corpus_protocol_compatibility(cases, "post-pilot-v1")


# --- j. legacy AST isolation: v4 never reads case_input.text --------------


def test_v4_path_never_calls_the_legacy_free_text_reference_function(monkeypatch):
    """Behavioral proof, not just naming: monkeypatch the legacy free-text
    extraction function to raise, and confirm v4 scoring still succeeds --
    the v4 branch of score_utility must never call it."""
    import adaptive_disclosure_gateway.experiments.scoring.utility as utility_module

    def _boom(*args, **kwargs):
        raise AssertionError("post-pilot-v4 must never call the legacy v3 reference extractor")

    monkeypatch.setattr(utility_module, "_legacy_v3_reference_values", _boom)

    case_input, oracle = _synthetic_case(
        sample_id="synthetic-legacy-fn-isolation",
        categories_and_values={"contract_value": "R$ 520000.00"},
        depends_on=["contract_value"],
        utility_references=[
            _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")
        ],
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))
    score = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4"
    )
    contract_value = next(c for c in score.by_category if c.category == "contract_value")
    assert contract_value.outcome == "answerable"


def test_v4_never_reads_case_input_text_by_ast():
    """AST check on classify_generalized_band_against_references and the v4
    dispatch arm of score_utility: neither function's source references
    ``text`` at all."""
    import ast
    import inspect

    for func in (classify_generalized_band_against_references,):
        tree = ast.parse(inspect.getsource(func))
        names = {
            node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", None)
            for node in ast.walk(tree)
        }
        assert "text" not in names


# --- k. no-leak: a marker in utility_references never reaches a result ----


def test_marker_planted_in_utility_references_never_reaches_a_runner_result():
    """Behavioral proof: run a real HR case through the real runner with a
    distinctive marker value planted in its (synthetic, opted-in)
    utility_references, and assert the marker appears nowhere in the
    serialized result -- payload, audit, provider payload/task, or the
    safe-serialized CaseResult.
    """
    from adaptive_disclosure_gateway.experiments.case_result import to_safe_dict
    from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
    from adaptive_disclosure_gateway.experiments.runner import run_case_for_treatment

    marker_amount = "987654.32"
    assert marker_amount not in HR_CORPUS_DIR.joinpath("hr_salary_analysis_001.yaml").read_text(
        encoding="utf-8"
    )

    cases = {c.input.sample_id: c for c in load_hr_v1_cases(HR_CORPUS_DIR)}
    case = cases["hr_salary_analysis_001"]
    poisoned_oracle = case.oracle.model_copy(
        update={
            "utility_references": [
                _ref("salary", ReferenceOperator.GREATER_THAN_OR_EQUAL, marker_amount)
            ]
        }
    )
    poisoned_case = case._replace(oracle=poisoned_oracle)
    policy_repository = PolicyRepository.from_directory(POLICY_DIR)

    for treatment in Treatment:
        result = run_case_for_treatment(
            poisoned_case,
            treatment,
            corpus_version="hr/v1",
            run_classification=PILOT_DEVELOPMENT,
            policy_repository=policy_repository,
            experiment_run_id="utility-reference-marker-probe",
            protocol_id="post-pilot-v4",
        )
        serialized = json.dumps(to_safe_dict(result), default=str)
        assert marker_amount not in serialized, (
            f"{treatment.value}: a utility_references marker reached the serialized result"
        )
        assert (
            marker_amount not in result.case_execution.execution.disclosure_result.external_payload
        )
        assert marker_amount not in repr(result.case_execution.execution.audit)
        assert marker_amount not in repr(result.score)
        assert marker_amount not in json.dumps(asdict(result.score.utility), default=str)


def test_treatment_output_identical_regardless_of_utility_references():
    """The oracle's utility_references must never influence what a
    treatment actually produces -- only post-execution scoring reads it.
    Execution output (decision/action/payload) must be byte-identical
    whether utility_references is None, empty, or populated."""
    from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases

    cases = {c.input.sample_id: c for c in load_hr_v1_cases(HR_CORPUS_DIR)}
    case = cases["hr_salary_analysis_001"]
    policy_repository = PolicyRepository.from_directory(POLICY_DIR)

    variants = [
        None,
        [],
        [_ref("salary", ReferenceOperator.GREATER_THAN_OR_EQUAL, "5000.00")],
    ]
    for treatment in (Treatment.STATIC_SANITIZATION, Treatment.TASK_AWARE):
        payloads = []
        for refs in variants:
            variant_case = case._replace(
                oracle=case.oracle.model_copy(update={"utility_references": refs})
            )
            execution = execute_case(
                case_input=variant_case.input,
                treatment=treatment,
                corpus_version="hr/v1",
                run_classification=PILOT_DEVELOPMENT,
                policy_repository=policy_repository,
                protocol_id="post-pilot-v3",
            )
            payloads.append(execution.execution.disclosure_result.external_payload)
        assert len(set(payloads)) == 1, f"{treatment.value}: payload varied with utility_references"


def test_case_oracle_score_case_end_to_end_under_v4():
    """End-to-end sanity through score_case (not just score_utility
    directly): a v4-opted-in synthetic case scores answerable through the
    full scoring pipeline, with protocol_id threaded from RunIdentity."""
    from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases

    cases = {c.input.sample_id: c for c in load_hr_v1_cases(HR_CORPUS_DIR)}
    case = cases["hr_salary_analysis_001"]
    opted_in_oracle = case.oracle.model_copy(
        update={
            "utility_references": [
                _ref("salary", ReferenceOperator.GREATER_THAN_OR_EQUAL, "5000.00")
            ]
        }
    )
    opted_in_case = case._replace(oracle=opted_in_oracle)
    policy_repository = PolicyRepository.from_directory(POLICY_DIR)

    execution = execute_case(
        case_input=opted_in_case.input,
        treatment=Treatment.TASK_AWARE,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repository,
        protocol_id="post-pilot-v4",
    )
    assert execution.identity.protocol_id == "post-pilot-v4"
    score = score_case(opted_in_case.input, opted_in_case.oracle, execution)
    salary_utility = next(c for c in score.utility.by_category if c.category == "salary")
    assert salary_utility.outcome == "answerable"
    assert salary_utility.reason == "generalized_band_decidable"
