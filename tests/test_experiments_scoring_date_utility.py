"""M3 Gate 6 / Issue #38 -- date-aware GENERALIZE utility scoring
(``post-pilot-v2``).

``score_utility``'s GENERALIZE handling (``_band_is_decidable``) is a
numeric-band rule: applied to a month-year date it is a type error, not a
calibration choice (see the pattern in ``docs/research/post-pilot-protocol-v1.md``
section 4.2/6.1 and the audit behind this ticket). This module pins the
replacement date-aware rule this ticket adds for categories registered in
``DATE_UTILITY_REQUIRED_GRANULARITY`` (today: ``deadline``, required to the
day per Issue #56 / commit 66e4677 / ``docs/contracts-policy-matrix.md``),
while leaving the numeric-band path byte-for-byte unchanged for every other
GENERALIZE category.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import get_args

from adaptive_disclosure_gateway.corpus.loader import load_corpus
from adaptive_disclosure_gateway.corpus.models import CorpusCategory
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureResult,
    Transformation,
    Treatment,
)
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.scoring import score_case
from adaptive_disclosure_gateway.experiments.scoring.utility import (
    DATE_UTILITY_REQUIRED_GRANULARITY,
    classify_generalized_date,
    score_utility,
)
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations.generalization import (
    GENERALIZATION_STRATEGIES,
    MonthYearDateStrategy,
)

HR_CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
CONTRACTS_CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "contracts" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

# Every registered corpus (append here when a new corpus/vN is added) -- the
# two guard tests in this module (drift, coherence) must reach all of them.
REGISTERED_CORPUS_DIRS = (HR_CORPUS_DIR, CONTRACTS_CORPUS_DIR)


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def _load_case(corpus_dir: Path, sample_id: str):
    return next(c for c in load_corpus(corpus_dir) if c.input.sample_id == sample_id)


# --- a. helper, required=day -------------------------------------------------


def test_classify_generalized_date_month_generalization_is_insufficient_for_required_day():
    outcome, reason = classify_generalized_date("2026-02-27", "2026-02", "day")
    assert (outcome, reason) == ("not_answerable", "generalized_date_insufficient_granularity")


def test_classify_generalized_date_wrong_month_is_wrong_value():
    outcome, reason = classify_generalized_date("2026-02-27", "2026-03", "day")
    assert (outcome, reason) == ("not_answerable", "generalized_date_wrong_value")


def test_classify_generalized_date_wrong_year_is_wrong_value():
    outcome, reason = classify_generalized_date("2026-02-27", "2025-02", "day")
    assert (outcome, reason) == ("not_answerable", "generalized_date_wrong_value")


def test_classify_generalized_date_full_day_precision_is_excess_precision():
    outcome, reason = classify_generalized_date("2026-02-27", "2026-02-27", "day")
    assert (outcome, reason) == ("not_answerable", "generalized_date_excess_precision")


def test_classify_generalized_date_year_only_is_insufficient_for_required_day():
    outcome, reason = classify_generalized_date("2026-02-27", "2026", "day")
    assert (outcome, reason) == ("not_answerable", "generalized_date_insufficient_granularity")


def test_classify_generalized_date_invalid_transformed_grammar_is_rejected():
    for transformed in ("2026-13", "02/2026", "fevereiro de 2026", "2026-2", "", None):
        outcome, reason = classify_generalized_date("2026-02-27", transformed, "day")
        assert (outcome, reason) == (
            "not_answerable",
            "generalized_date_invalid",
        ), f"transformed={transformed!r}"


def test_classify_generalized_date_malformed_or_impossible_original_is_unscorable():
    for original in ("2026-02-30", "27/02/2026"):
        outcome, reason = classify_generalized_date(original, "2026-02", "day")
        assert (outcome, reason) == (
            "not_answerable",
            "generalized_date_unscorable_original",
        ), f"original={original!r}"


# --- b. helper, required=month (a boundary pin, not a registry entry) -------


def test_classify_generalized_date_month_precision_is_sufficient_when_month_required():
    outcome, reason = classify_generalized_date("2026-02-27", "2026-02", "month")
    assert (outcome, reason) == ("answerable", "generalized_date_sufficient_granularity")


def test_classify_generalized_date_year_only_is_insufficient_when_month_required():
    outcome, reason = classify_generalized_date("2026-02-27", "2026", "month")
    assert (outcome, reason) == ("not_answerable", "generalized_date_insufficient_granularity")


# --- c. score_utility end-to-end on the real contracts cases ----------------


def _deadline_transformation(case, action, transformed=None):
    deadline_span = next(s for s in case.oracle.expected_spans if s.category == "deadline")
    if action is DisclosureAction.GENERALIZE:
        value = (
            transformed
            if transformed is not None
            else f"{deadline_span.value[:4]}-{deadline_span.value[5:7]}"
        )
    elif action is DisclosureAction.PRESERVE:
        value = deadline_span.value
    elif action is DisclosureAction.REMOVE:
        value = None
    else:
        raise AssertionError(f"unsupported action for this helper: {action}")
    return Transformation(
        category="deadline", original=deadline_span.value, transformed=value, action=action
    )


def _score_deadline(case, action, transformed=None):
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[_deadline_transformation(case, action, transformed=transformed)],
        status="allowed",
    )
    score = score_utility(case.input, case.oracle, result, Treatment.TASK_AWARE)
    return next(c for c in score.by_category if c.category == "deadline")


def test_real_deadline_tracking_001_generalized_deadline_is_not_answerable():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_deadline_tracking_001")
    category_utility = _score_deadline(case, DisclosureAction.GENERALIZE)
    assert category_utility.outcome == "not_answerable"
    assert category_utility.reason == "generalized_date_insufficient_granularity"


def test_real_deadline_tracking_001_preserved_deadline_stays_answerable():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_deadline_tracking_001")
    category_utility = _score_deadline(case, DisclosureAction.PRESERVE)
    assert category_utility.outcome == "answerable"
    assert category_utility.reason == "preserved"


def test_real_deadline_tracking_001_removed_deadline_stays_removed():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_deadline_tracking_001")
    category_utility = _score_deadline(case, DisclosureAction.REMOVE)
    assert category_utility.outcome == "not_answerable"
    assert category_utility.reason == "removed"


def test_real_obligation_relation_001_generalized_deadline_is_not_answerable():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_obligation_relation_001")
    category_utility = _score_deadline(case, DisclosureAction.GENERALIZE)
    assert category_utility.outcome == "not_answerable"
    assert category_utility.reason == "generalized_date_insufficient_granularity"


def test_real_obligation_relation_001_preserved_deadline_stays_answerable():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_obligation_relation_001")
    category_utility = _score_deadline(case, DisclosureAction.PRESERVE)
    assert category_utility.outcome == "answerable"
    assert category_utility.reason == "preserved"


def test_real_obligation_relation_001_removed_deadline_stays_removed():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_obligation_relation_001")
    category_utility = _score_deadline(case, DisclosureAction.REMOVE)
    assert category_utility.outcome == "not_answerable"
    assert category_utility.reason == "removed"


# --- c'. oracle<->scorer coherence: the date rule must compare against the
# oracle span's own value, never the transformation's own `original` field
# (Gate 6 review finding, PR #86) ---------------------------------------


def test_generalized_date_is_judged_against_the_oracle_span_value_not_the_transformation_original():
    """A real regression pin for the review finding: ``classify_generalized_date``
    must be called with the oracle's own ``ExpectedSpan.value`` (ground
    truth), never ``Transformation.original`` (whatever the detector/
    treatment happened to read). If a treatment's own ``original`` disagreed
    with the oracle -- a real possible defect: a detector misread, or a
    span-matching mismatch -- comparing against the transformation's own
    field would silently validate the *wrong* ground truth.

    Constructed here as a distinctive, deliberately wrong ``original`` on a
    real corpus case's oracle: the oracle's own deadline is
    ``2026-02-27`` (year 2026), but the transformation claims a completely
    different ``original`` of ``2099-09-09`` (year 2099) with a
    ``transformed`` value (``"2099-09"``) consistent with *that* wrong
    original, not with the oracle's. If the scorer used the oracle's own
    value (correct), the year mismatch (2026 vs 2099) makes this
    ``generalized_date_wrong_value``. If it used the transformation's own
    ``original`` (the bug), the transformed value would agree with it and
    score ``generalized_date_insufficient_granularity`` instead -- which is
    exactly why this test can fail from the real defect.
    """
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_deadline_tracking_001")
    oracle_deadline = next(s for s in case.oracle.expected_spans if s.category == "deadline")
    assert oracle_deadline.value == "2026-02-27"

    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[
            Transformation(
                category="deadline",
                original="2099-09-09",
                transformed="2099-09",
                action=DisclosureAction.GENERALIZE,
            )
        ],
        status="allowed",
    )
    score = score_utility(case.input, case.oracle, result, Treatment.TASK_AWARE)
    category_utility = next(c for c in score.by_category if c.category == "deadline")

    assert category_utility.outcome == "not_answerable"
    assert category_utility.reason == "generalized_date_wrong_value"


# --- d. equivalence: component-consistent, never string-equal to original --


def test_classify_generalized_date_equivalence_is_by_parsed_components_not_string_equality():
    for original in ("2026-02-01", "2026-02-27"):
        outcome, reason = classify_generalized_date(original, "2026-02", "month")
        assert (outcome, reason) == (
            "answerable",
            "generalized_date_sufficient_granularity",
        ), f"original={original!r}"


# --- e. determinism ----------------------------------------------------------


def test_score_utility_date_rule_is_deterministic_across_repeated_calls():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_deadline_tracking_001")
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[_deadline_transformation(case, DisclosureAction.GENERALIZE)],
        status="allowed",
    )
    first = score_utility(case.input, case.oracle, result, Treatment.TASK_AWARE)
    second = score_utility(case.input, case.oracle, result, Treatment.TASK_AWARE)
    assert first == second


# --- g. numeric-band path unchanged: an explicit decidable-band pin --------


def test_numeric_band_generalize_still_scores_decidable_for_a_real_case():
    """A real, unmodified corpus case where a GENERALIZE band is decidable
    against a stated reference figure outside every detected span
    (``contracts_obligation_relation_001``'s payment ceiling): pins that
    adding the date-aware rule leaves the pre-existing numeric-band path
    byte-for-byte unchanged for non-date categories.
    """
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_obligation_relation_001")
    policy_repo = _policy_repo()
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.TASK_AWARE,
        corpus_version="contracts/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repo,
    )
    score = score_case(case.input, case.oracle, execution)
    contract_value_utility = next(
        c for c in score.utility.by_category if c.category == "contract_value"
    )
    assert contract_value_utility.outcome == "answerable"
    assert contract_value_utility.reason == "generalized_band_decidable"


# --- h. guards: no oracle/corpus change silently required -------------------


def test_every_month_year_date_category_that_is_a_corpus_category_is_registered():
    """Drift guard: every ``GENERALIZATION_STRATEGIES`` entry that is a
    ``MonthYearDateStrategy`` AND whose category is a member of
    ``CorpusCategory`` must appear in ``DATE_UTILITY_REQUIRED_GRANULARITY``.

    ``birth_date`` has a strategy but is not a ``CorpusCategory`` (no HR/
    Contracts oracle can ever reference it in ``answer_depends_on_categories``
    -- ``score_utility`` never scores a category outside the oracle's own
    frozen vocabulary), so it is correctly out of scope for this guard; this
    test also pins that fact rather than assuming it silently.
    """
    corpus_categories = set(get_args(CorpusCategory))
    assert "birth_date" not in corpus_categories

    date_categories = {
        category
        for category, strategy in GENERALIZATION_STRATEGIES.items()
        if isinstance(strategy, MonthYearDateStrategy)
    }
    assert "birth_date" in date_categories  # sanity that the strategy dict itself is as documented

    for category in date_categories:
        if category not in corpus_categories:
            continue
        assert category in DATE_UTILITY_REQUIRED_GRANULARITY, (
            f"{category!r} uses MonthYearDateStrategy and is a CorpusCategory but has no "
            "required-granularity registry entry"
        )


def test_registered_corpora_cite_the_full_iso_day_for_every_required_date_answer():
    """Coherence guard: in every registered corpus, for every non-blocked
    case where a registry category is in ``answer_depends_on_categories``,
    ``expected_answer`` cites that span's full ISO day verbatim -- never a
    coarsened form. This is what makes the day-granularity requirement in
    ``DATE_UTILITY_REQUIRED_GRANULARITY`` true of the actual corpus content,
    not just an assumption this module makes about it.
    """
    checked_any = False
    for corpus_dir in REGISTERED_CORPUS_DIRS:
        for case in load_corpus(corpus_dir):
            if case.oracle.expected_block_request:
                continue
            depends_on = case.oracle.answer_depends_on_categories or []
            for category in DATE_UTILITY_REQUIRED_GRANULARITY:
                if category not in depends_on:
                    continue
                for span in case.oracle.expected_spans:
                    if span.category != category:
                        continue
                    checked_any = True
                    assert span.value in case.oracle.expected_answer, (
                        f"{case.input.sample_id}: expected_answer does not cite the full "
                        f"ISO day for required category {category!r}"
                    )
    assert checked_any, "expected at least one case exercising a registered date category"


# --- i. adversarial no-leak --------------------------------------------------


def test_classify_generalized_date_reason_never_contains_either_date_value():
    distinctive_original = "1861-11-07"
    distinctive_transformed = "1861-11"
    outcome, reason = classify_generalized_date(
        distinctive_original, distinctive_transformed, "day"
    )
    assert outcome == "not_answerable"
    assert reason == "generalized_date_insufficient_granularity"
    assert distinctive_original not in reason
    assert distinctive_transformed not in reason


def test_score_utility_output_never_contains_a_distinctive_date_value():
    case = _load_case(CONTRACTS_CORPUS_DIR, "contracts_deadline_tracking_001")
    distinctive_original = "1861-11-07"
    distinctive_transformed = "1861-11"
    result = DisclosureResult(
        external_payload="irrelevant to score_utility",
        decisions=[],
        transformations=[
            Transformation(
                category="deadline",
                original=distinctive_original,
                transformed=distinctive_transformed,
                action=DisclosureAction.GENERALIZE,
            )
        ],
        status="allowed",
    )
    score = score_utility(case.input, case.oracle, result, Treatment.TASK_AWARE)
    serialized = repr(dataclasses.asdict(score))
    assert distinctive_original not in serialized
    assert distinctive_transformed not in serialized
