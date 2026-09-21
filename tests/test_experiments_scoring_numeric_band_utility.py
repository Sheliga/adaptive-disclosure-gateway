"""Issue #85 / M3 -- numeric-band GENERALIZE fidelity in utility scoring
(``post-pilot-v3``).

``score_utility``'s numeric-band GENERALIZE path (the pre-Gate-6 rule that
survives for ``salary``/``contract_value``/``penalty_amount``) never checked
that the band a treatment produced actually *contains* the case's own
oracle value -- only whether stated reference figures elsewhere in the text
fall unambiguously on one side of it (``_band_is_decidable``). A wrong band
(inverted, degenerate, or simply not containing the original) scored
``answerable`` whenever no reference figure happened to land inside it, and
with zero references every band was vacuously "decidable" (``all([])`` is
``True``). This module pins the replacement fidelity-first rule,
``classify_generalized_band``, this ticket adds: fidelity (does the band
contain the value at all) is checked before sufficiency (can the band be
resolved against a stated reference) -- mirroring the date-aware rule Gate 6
added in ``tests/test_experiments_scoring_date_utility.py``, whose structure
this module follows.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import get_args

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import load_corpus
from adaptive_disclosure_gateway.corpus.models import (
    CorpusCategory,
    ExpectedSpan,
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
from adaptive_disclosure_gateway.experiments.scoring.utility import (
    DATE_UTILITY_REQUIRED_GRANULARITY,
    NUMERIC_BAND_UTILITY_CATEGORIES,
    NUMERIC_BAND_UTILITY_REASONS,
    classify_generalized_band,
    score_utility,
)
from adaptive_disclosure_gateway.transformations.generalization import (
    GENERALIZATION_STRATEGIES,
    NumericBandStrategy,
    generalize,
)

HR_CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
CONTRACTS_CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "contracts" / "v1" / "cases"

REGISTERED_CORPUS_DIRS = (HR_CORPUS_DIR, CONTRACTS_CORPUS_DIR)


def _load_case(corpus_dir: Path, sample_id: str):
    return next(c for c in load_corpus(corpus_dir) if c.input.sample_id == sample_id)


# --- a. classify_generalized_band: containment/fidelity first --------------


def test_contains_original_and_sufficient_reference_is_decidable():
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 5000-10000", [4000.0])
    assert (outcome, reason) == ("answerable", "generalized_band_decidable")


def test_band_excluding_original_is_not_answerable_regardless_of_references():
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 10000-15000", [4000.0])
    assert (outcome, reason) == ("not_answerable", "generalized_band_excludes_original")


def test_exact_lower_bound_is_contained_half_open():
    outcome, reason = classify_generalized_band("R$ 5000.00", "R$ 5000-10000", [])
    assert (outcome, reason) == ("indeterminate", "generalized_band_no_reference")


def test_exact_upper_bound_is_excluded_half_open():
    outcome, reason = classify_generalized_band("R$ 10000.00", "R$ 5000-10000", [])
    assert (outcome, reason) == ("not_answerable", "generalized_band_excludes_original")


def test_upper_bound_value_is_contained_by_the_next_band():
    outcome, reason = classify_generalized_band("R$ 10000.00", "R$ 10000-15000", [])
    assert (outcome, reason) == ("indeterminate", "generalized_band_no_reference")


def test_value_just_below_upper_bound_is_contained():
    outcome, reason = classify_generalized_band("R$ 9999.99", "R$ 5000-10000", [])
    assert (outcome, reason) == ("indeterminate", "generalized_band_no_reference")


def test_inverted_band_is_invalid():
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 10000-5000", [])
    assert (outcome, reason) == ("not_answerable", "generalized_band_invalid")


def test_degenerate_zero_width_band_is_invalid():
    """Not producible by ``NumericBandStrategy`` (which enforces
    ``MIN_NUMERIC_BAND_WIDTH``), but the classification grammar must still be
    total over every string shape a corrupted/future treatment could emit.
    """
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 5000-5000", [])
    assert (outcome, reason) == ("not_answerable", "generalized_band_invalid")


def test_invalid_band_formats_are_rejected():
    invalid_bands = [
        "R$ 5000 - 10000",
        "5000-10000",
        "R$ 5.000-10.000",
        "US$ 5000-10000",
        "R$ -5000-0",
        "2026-02",
        "",
        None,
    ]
    for band in invalid_bands:
        outcome, reason = classify_generalized_band("R$ 9200.00", band, [])
        assert (outcome, reason) == (
            "not_answerable",
            "generalized_band_invalid",
        ), f"band={band!r}"


def test_unparseable_original_is_rejected_before_the_band_is_even_checked():
    """Unscorable-original takes precedence over an invalid band -- an
    unparseable original makes the transformed value unevaluable regardless
    of its own shape (mirrors ``classify_generalized_date``'s own ordering).
    """
    unparseable_originals = ["R$ 9.200,00", "9200", "R$ 9200", "", None]
    for original in unparseable_originals:
        outcome, reason = classify_generalized_band(original, "not a valid band", [])
        assert (outcome, reason) == (
            "not_answerable",
            "generalized_band_unscorable_original",
        ), f"original={original!r}"


def test_correct_band_with_reference_inside_it_is_ambiguous():
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 5000-10000", [7000.0])
    assert (outcome, reason) == ("indeterminate", "generalized_band_ambiguous")


def test_correct_band_with_reference_outside_it_is_decidable():
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 5000-10000", [4000.0])
    assert (outcome, reason) == ("answerable", "generalized_band_decidable")


def test_central_adversarial_wrong_band_with_reference_outside_it_is_not_answerable():
    """The exact HR audit finding: a band that is simply wrong (does not
    contain the original at all) previously scored ``answerable`` because no
    reference figure fell inside it. That must never happen again."""
    outcome, reason = classify_generalized_band("R$ 125000.00", "R$ 600000-650000", [500000.0])
    assert (outcome, reason) == ("not_answerable", "generalized_band_excludes_original")


def test_no_reference_and_correct_band_is_indeterminate_not_vacuously_decidable():
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 5000-10000", [])
    assert (outcome, reason) == ("indeterminate", "generalized_band_no_reference")


def test_no_reference_and_wrong_band_is_still_not_answerable():
    outcome, reason = classify_generalized_band("R$ 9200.00", "R$ 10000-15000", [])
    assert (outcome, reason) == ("not_answerable", "generalized_band_excludes_original")


# --- b. score_utility end-to-end on real cases with an injected wrong band -


def _contract_value_transformation(band: str, original: str | None = None) -> Transformation:
    return Transformation(
        category="contract_value",
        original=original if original is not None else "R$ 940000.00",
        transformed=band,
        action=DisclosureAction.GENERALIZE,
    )


def test_real_contracts_value_audit_002_with_a_wrong_band_is_not_answerable():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_value_audit_002")
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[_contract_value_transformation("R$ 600000-650000")],
        status="allowed",
    )
    score = score_utility(
        case.input, case.oracle, result, Treatment.POLICY_GOVERNED, protocol_id="post-pilot-v3"
    )
    contract_value_utility = next(c for c in score.by_category if c.category == "contract_value")
    assert contract_value_utility.outcome == "not_answerable"
    assert contract_value_utility.reason == "generalized_band_excludes_original"
    assert score.overall == "not_answerable"


def test_real_hr_salary_analysis_001_with_a_wrong_band_is_not_answerable():
    case = _load_case(HR_CORPUS_DIR, "hr_salary_analysis_001")
    salary_span = next(s for s in case.oracle.expected_spans if s.category == "salary")
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[
            Transformation(
                category="salary",
                original=salary_span.value,
                transformed="R$ 20000-25000",
                action=DisclosureAction.GENERALIZE,
            ),
        ],
        status="allowed",
    )
    score = score_utility(
        case.input, case.oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v3"
    )
    salary_utility = next(c for c in score.by_category if c.category == "salary")
    assert salary_utility.outcome == "not_answerable"
    assert salary_utility.reason == "generalized_band_excludes_original"
    assert score.overall == "not_answerable"


def test_ground_truth_is_the_oracle_span_value_never_the_transformations_own_original():
    """PR #86's principle, applied to the numeric-band path: a treatment's
    own ``Transformation.original`` must never be what the wrong-band check
    is judged against. Here ``Transformation.original`` is deliberately set
    to a value *inside* the wrong band while the oracle's real value
    (940000.00) is not -- if the scorer used the transformation's own
    ``original`` (the bug this pins against), it would wrongly validate."""
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_value_audit_002")
    contract_value_span = next(
        s for s in case.oracle.expected_spans if s.category == "contract_value"
    )
    assert contract_value_span.value == "R$ 940000.00"

    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[
            _contract_value_transformation("R$ 600000-650000", original="R$ 612345.00")
        ],
        status="allowed",
    )
    score = score_utility(
        case.input, case.oracle, result, Treatment.POLICY_GOVERNED, protocol_id="post-pilot-v3"
    )
    contract_value_utility = next(c for c in score.by_category if c.category == "contract_value")
    assert contract_value_utility.outcome == "not_answerable"
    assert contract_value_utility.reason == "generalized_band_excludes_original"


def test_real_hr_department_aggregation_003_one_wrong_salary_band_fails_the_category():
    case = _load_case(HR_CORPUS_DIR, "hr_department_aggregation_003")
    salary_spans = [s for s in case.oracle.expected_spans if s.category == "salary"]
    assert len(salary_spans) == 3

    transformations = []
    for index, span in enumerate(salary_spans):
        if index == 1:
            # A wrong band that does not contain this span's own value at all.
            transformations.append(
                Transformation(
                    category="salary",
                    original=span.value,
                    transformed="R$ 50000-55000",
                    action=DisclosureAction.GENERALIZE,
                )
            )
        else:
            band = generalize("salary", span.value)
            transformations.append(
                Transformation(
                    category="salary",
                    original=span.value,
                    transformed=band,
                    action=DisclosureAction.GENERALIZE,
                )
            )

    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=transformations,
        status="allowed",
    )
    score = score_utility(
        case.input, case.oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v3"
    )
    salary_utility = next(c for c in score.by_category if c.category == "salary")
    assert salary_utility.outcome == "not_answerable"


def test_synthetic_generalize_on_an_unregistered_category_fails_closed():
    oracle = CaseOracle(
        sample_id="synthetic-unregistered-generalize-category",
        expected_spans=[
            ExpectedSpan(
                category="department",
                value="Engineering",
                start=12,
                end=23,
                task_necessity=TaskNecessity.REQUIRED,
                expected_actions=[DisclosureAction.GENERALIZE],
            ),
        ],
        expected_block_request=False,
        expected_answer="Some department-derived answer.",
        answer_depends_on_categories=["department"],
    )
    case_input = CorpusCaseInput(
        sample_id="synthetic-unregistered-generalize-category",
        text="Department: Engineering",
        task="Name the broader region for this department.",
        task_family=TaskFamily.TEAM_SUMMARY_WITHOUT_SALARY,
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
    )
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[
            Transformation(
                category="department",
                original="Engineering",
                transformed="Some region",
                action=DisclosureAction.GENERALIZE,
            ),
        ],
        status="allowed",
    )
    score = score_utility(
        case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v3"
    )
    department_utility = next(c for c in score.by_category if c.category == "department")
    assert department_utility.outcome == "not_answerable"
    assert department_utility.reason == "generalized_category_unregistered"


def test_score_utility_numeric_band_rule_is_deterministic_across_repeated_calls():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_value_audit_002")
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[_contract_value_transformation("R$ 600000-650000")],
        status="allowed",
    )
    first = score_utility(
        case.input, case.oracle, result, Treatment.POLICY_GOVERNED, protocol_id="post-pilot-v3"
    )
    second = score_utility(
        case.input, case.oracle, result, Treatment.POLICY_GOVERNED, protocol_id="post-pilot-v3"
    )
    assert first == second


# --- c. regressions: existing pins stay green (not re-asserted here; see
# tests/test_experiments_hr_salary_analysis_003_regression.py and
# tests/test_experiments_scoring_date_utility.py's decidable-band pin) ------


# --- d. guards: no drift between the generalization registry and the two
# utility-scoring registries --------------------------------------------


def test_numeric_band_and_date_registries_are_disjoint():
    assert set(DATE_UTILITY_REQUIRED_GRANULARITY).isdisjoint(NUMERIC_BAND_UTILITY_CATEGORIES)


def test_every_numeric_band_strategy_category_is_registered_for_utility_scoring():
    numeric_strategy_categories = {
        category
        for category, strategy in GENERALIZATION_STRATEGIES.items()
        if isinstance(strategy, NumericBandStrategy)
    }
    assert numeric_strategy_categories == NUMERIC_BAND_UTILITY_CATEGORIES


def test_generalization_strategy_corpus_categories_equal_the_two_utility_registries_union():
    """Drift guard: every ``GENERALIZATION_STRATEGIES`` entry that is also a
    ``CorpusCategory`` must be registered in exactly one of the date/numeric
    utility registries -- otherwise it would silently fall into
    ``score_utility``'s fail-closed ``generalized_category_unregistered``
    branch the first time a real case exercised it."""
    corpus_categories = set(get_args(CorpusCategory))
    strategy_categories_in_corpus = {
        category for category in GENERALIZATION_STRATEGIES if category in corpus_categories
    }
    registries_union = set(DATE_UTILITY_REQUIRED_GRANULARITY) | set(NUMERIC_BAND_UTILITY_CATEGORIES)
    assert strategy_categories_in_corpus == registries_union


def test_every_numeric_oracle_span_in_every_registered_corpus_is_self_consistent():
    """Coherence guard: for every numeric-category oracle span in every
    registered corpus, the strict original parser accepts the span's own
    value, and the band the real generalization strategy produces from it
    always classifies as ``no_reference`` (never invalid/excludes/
    unscorable) when checked with no reference figures -- i.e. the frozen
    generator and the new fidelity check agree on every real oracle value."""
    checked_any = False
    for corpus_dir in REGISTERED_CORPUS_DIRS:
        for case in load_corpus(corpus_dir):
            for span in case.oracle.expected_spans:
                if span.category not in NUMERIC_BAND_UTILITY_CATEGORIES:
                    continue
                checked_any = True
                band = generalize(span.category, span.value)
                outcome, reason = classify_generalized_band(span.value, band, [])
                assert (outcome, reason) == (
                    "indeterminate",
                    "generalized_band_no_reference",
                ), f"{case.input.sample_id}/{span.category}: {outcome}/{reason}"
    assert checked_any, "expected at least one numeric-category oracle span"


# --- e. no-leak adversarial ---------------------------------------------


def test_classify_generalized_band_reason_never_contains_either_value():
    distinctive_original = "R$ 137913.00"
    distinctive_band = "R$ 713000-763000"
    outcome, reason = classify_generalized_band(distinctive_original, distinctive_band, [555111.0])
    assert outcome == "not_answerable"
    assert reason == "generalized_band_excludes_original"
    assert "137913.00" not in reason
    assert "R$ 713000-763000" not in reason
    assert "555111.00" not in reason


def test_score_utility_output_never_contains_a_distinctive_amount_or_band():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_value_audit_002")
    distinctive_original = "R$ 137913.00"
    distinctive_band = "R$ 713000-763000"
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[
            Transformation(
                category="contract_value",
                original=distinctive_original,
                transformed=distinctive_band,
                action=DisclosureAction.GENERALIZE,
            )
        ],
        status="allowed",
    )
    score = score_utility(
        case.input, case.oracle, result, Treatment.POLICY_GOVERNED, protocol_id="post-pilot-v3"
    )
    serialized = repr(dataclasses.asdict(score))
    as_json = json.dumps(dataclasses.asdict(score))
    for haystack in (serialized, as_json):
        assert "137913.00" not in haystack
        assert "R$ 713000-763000" not in haystack
        assert "555111.00" not in haystack


def test_every_reason_classify_generalized_band_can_return_is_in_the_closed_set():
    cases = [
        ("R$ 9200.00", "R$ 5000-10000", []),
        ("R$ 9200.00", "R$ 5000-10000", [4000.0]),
        ("R$ 9200.00", "R$ 5000-10000", [7000.0]),
        ("R$ 9200.00", "R$ 10000-15000", []),
        ("R$ 9200.00", "R$ 10000-5000", []),
        ("not an amount", "R$ 5000-10000", []),
    ]
    for original, transformed, references in cases:
        _, reason = classify_generalized_band(original, transformed, references)
        assert reason in NUMERIC_BAND_UTILITY_REASONS
