"""Issue #93 / M3 -- ``post-pilot-v5`` numeric amount format contract:
scorer-side fidelity, date-grammar ASCII-ification, dispatch exhaustiveness
and the pre-run amount-format check.

This module does not re-test the amount grammar itself (see
``tests/test_amount_grammar_cross_check.py``); it pins how the scorer's v5
functions *use* that grammar: fidelity classification, dispatch by
``protocol_id``, and the new pre-run check that runs before any provider
call. All fixtures are synthetic, minimal, in-test data -- never a
confirmatory corpus.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import CorpusCase
from adaptive_disclosure_gateway.corpus.models import (
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
from adaptive_disclosure_gateway.experiments.post_pilot_protocol import (
    UnsupportedScoringProtocolError,
)
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.runner import run_pilot
from adaptive_disclosure_gateway.experiments.scoring.utility import (
    NUMERIC_BAND_UTILITY_REASONS,
    UnsupportedOriginalAmountFormatError,
    check_corpus_protocol_compatibility,
    classify_generalized_band_against_references,
    classify_generalized_band_against_references_v5,
    classify_generalized_date,
    classify_generalized_date_v5,
    score_utility,
)

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

_BAND = "R$ 500000-550000"


def _ref(category: str, operator: ReferenceOperator, value: str) -> NumericUtilityReference:
    return NumericUtilityReference(category=category, operator=operator, value=value)


def _synthetic_case(
    *,
    sample_id: str,
    category: str,
    span_value: str,
    utility_references: list[NumericUtilityReference] | None,
    expected_block_request: bool = False,
) -> tuple[CorpusCaseInput, CaseOracle]:
    span = ExpectedSpan(
        category=category,
        value=span_value,
        start=0,
        end=len(span_value),
        task_necessity=TaskNecessity.NOT_REQUIRED if expected_block_request else TaskNecessity.REQUIRED,
        expected_actions=(
            [DisclosureAction.BLOCK_REQUEST]
            if expected_block_request
            else [DisclosureAction.GENERALIZE]
        ),
    )
    oracle = CaseOracle(
        sample_id=sample_id,
        expected_spans=[span],
        expected_block_request=expected_block_request,
        expected_answer=None if expected_block_request else "synthetic answer",
        answer_depends_on_categories=None if expected_block_request else [category],
        utility_references=None if expected_block_request else utility_references,
    )
    case_input = CorpusCaseInput(
        sample_id=sample_id,
        text="synthetic case text with no category values or reference amounts in it",
        task="synthetic task",
        task_family=TaskFamily.TEAM_SUMMARY_WITHOUT_SALARY,
        domain="hr" if category == "salary" else "contracts",
        purpose="team_summary" if category == "salary" else "contract_review",
        policy_version="hr-v1" if category == "salary" else "contracts-v1",
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


# --- a. v5 fidelity: Brazilian original accepted where v4 rejects it -------


def test_v5_accepts_a_brazilian_original_that_v4_rejects_as_unscorable():
    brazilian_original = "R$ 520000,00"
    reference = _ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")

    v4_outcome, v4_reason = classify_generalized_band_against_references(
        brazilian_original, _BAND, [reference]
    )
    assert (v4_outcome, v4_reason) == ("not_answerable", "generalized_band_unscorable_original")

    v5_outcome, v5_reason = classify_generalized_band_against_references_v5(
        brazilian_original, _BAND, [reference]
    )
    assert (v5_outcome, v5_reason) == ("answerable", "generalized_band_decidable")


def test_v5_correct_band_accepted():
    outcome, reason = classify_generalized_band_against_references_v5(
        "R$ 520000,00", _BAND, []
    )
    assert (outcome, reason) == ("indeterminate", "generalized_band_no_reference")


def test_v5_neighbouring_band_excludes_original():
    outcome, reason = classify_generalized_band_against_references_v5(
        "R$ 520000,00", "R$ 550000-600000", []
    )
    assert (outcome, reason) == ("not_answerable", "generalized_band_excludes_original")


def test_v5_non_ascii_band_is_invalid():
    non_ascii_band = "R$ ٥٠٠٠٠٠-٥٥٠٠٠٠"
    outcome, reason = classify_generalized_band_against_references_v5(
        "R$ 520000,00", non_ascii_band, []
    )
    assert (outcome, reason) == ("not_answerable", "generalized_band_invalid")


def test_v5_band_with_trailing_newline_is_rejected():
    outcome, reason = classify_generalized_band_against_references_v5(
        "R$ 520000,00", f"{_BAND}\n", []
    )
    assert (outcome, reason) == ("not_answerable", "generalized_band_invalid")


def test_v5_every_reason_is_in_the_closed_set():
    cases = [
        ("R$ 520000,00", _BAND, []),
        ("R$ 520000,00", _BAND, [_ref("contract_value", ReferenceOperator.GREATER_THAN, "500000.00")]),
        ("not an amount", _BAND, []),
        ("R$ 520000,00", "not a band", []),
    ]
    for original, transformed, references in cases:
        _, reason = classify_generalized_band_against_references_v5(original, transformed, references)
        assert reason in NUMERIC_BAND_UTILITY_REASONS


# --- b. v5 date grammar is ASCII-only ---------------------------------------


def test_v5_date_grammar_rejects_non_ascii_digits_where_v3_v4_accept_them():
    non_ascii_month = "٢٠٢٦-٠٣"  # "2026-03" in Arabic-Indic digits
    v3_v4_outcome, v3_v4_reason = classify_generalized_date("2026-03-15", non_ascii_month, "month")
    v5_outcome, v5_reason = classify_generalized_date_v5("2026-03-15", non_ascii_month, "month")

    # Documents the pre-#91 behavior, frozen for v3/v4: `\d` happily matches
    # the Arabic-Indic digits, and Python's own `int()` happily parses them.
    assert (v3_v4_outcome, v3_v4_reason) == ("answerable", "generalized_date_sufficient_granularity")
    assert (v5_outcome, v5_reason) == ("not_answerable", "generalized_date_invalid")


def test_v5_date_grammar_rejects_trailing_newline():
    outcome, reason = classify_generalized_date_v5("2026-03-15", "2026-03\n", "month")
    assert (outcome, reason) == ("not_answerable", "generalized_date_invalid")


def test_v5_date_grammar_accepts_the_same_valid_forms_as_v3_v4():
    for required, transformed, original, expected in [
        ("month", "2026-03", "2026-03-15", "generalized_date_sufficient_granularity"),
        ("day", "2026-03-15", "2026-03-15", "generalized_date_excess_precision"),
    ]:
        v3_v4_outcome, v3_v4_reason = classify_generalized_date(original, transformed, required)
        v5_outcome, v5_reason = classify_generalized_date_v5(original, transformed, required)
        assert (v5_outcome, v5_reason) == (v3_v4_outcome, v3_v4_reason) == (
            ("answerable", expected) if "sufficient" in expected else ("not_answerable", expected)
        )


# --- c. dispatch: v5 differs from v4, v3/v4 unchanged, no silent fallthrough -


def test_score_utility_dispatches_v5_band_rule_for_v5_protocol():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v5-dispatch",
        category="contract_value",
        span_value="R$ 520000,00",
        utility_references=[_ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")],
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000,00"))

    score = score_utility(case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v5")
    contract_value = next(c for c in score.by_category if c.category == "contract_value")
    assert contract_value.outcome == "answerable"
    assert contract_value.reason == "generalized_band_decidable"


def test_score_utility_v4_still_rejects_the_same_brazilian_original():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v4-unchanged",
        category="contract_value",
        span_value="R$ 520000,00",
        utility_references=[_ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")],
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000,00"))

    score = score_utility(case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v4")
    contract_value = next(c for c in score.by_category if c.category == "contract_value")
    assert contract_value.outcome == "not_answerable"
    assert contract_value.reason == "generalized_band_unscorable_original"


def test_numeric_band_outcome_dispatch_never_falls_through_to_v4_for_an_unhandled_id(monkeypatch):
    """Defensive-exhaustiveness pin: even if a future protocol id is added to
    ``SCORABLE_PROTOCOL_IDS`` without updating this dispatch, ``score_utility``
    must raise rather than silently reusing v4's rule for it."""
    import adaptive_disclosure_gateway.experiments.post_pilot_protocol as protocol_module
    import adaptive_disclosure_gateway.experiments.scoring.utility as utility_module

    fake_ids = frozenset({"post-pilot-v3", "post-pilot-v4", "post-pilot-v5", "post-pilot-v6-not-real"})
    monkeypatch.setattr(protocol_module, "FROZEN_PROTOCOL_IDS", fake_ids)
    monkeypatch.setattr(protocol_module, "SCORABLE_PROTOCOL_IDS", fake_ids)
    monkeypatch.setattr(utility_module, "_check_case_protocol_compatibility", lambda *a, **k: None)

    case_input, oracle = _synthetic_case(
        sample_id="synthetic-unhandled-id",
        category="contract_value",
        span_value="R$ 520000.00",
        utility_references=[_ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")],
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))

    with pytest.raises(UnsupportedScoringProtocolError):
        score_utility(
            case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v6-not-real"
        )


def test_case_protocol_compatibility_never_falls_through_for_an_unhandled_scorable_id(monkeypatch):
    import adaptive_disclosure_gateway.experiments.post_pilot_protocol as protocol_module

    fake_ids = frozenset({"post-pilot-v3", "post-pilot-v4", "post-pilot-v5", "post-pilot-v6-not-real"})
    monkeypatch.setattr(protocol_module, "FROZEN_PROTOCOL_IDS", fake_ids)
    monkeypatch.setattr(protocol_module, "SCORABLE_PROTOCOL_IDS", fake_ids)
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-unhandled-id-compat",
        category="contract_value",
        span_value="R$ 520000.00",
        utility_references=[_ref("contract_value", ReferenceOperator.GREATER_THAN_OR_EQUAL, "500000.00")],
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))
    with pytest.raises(UnsupportedScoringProtocolError):
        score_utility(
            case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v6-not-real"
        )


def test_v5_opted_in_matrix_same_as_v4():
    """Same MissingUtilityReferencesError/StructuredReferencesRequireV4Error
    rules apply to v5 as to v4 (spec: keep class name, broaden message)."""
    from adaptive_disclosure_gateway.experiments.scoring.utility import (
        MissingUtilityReferencesError,
    )

    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v5-legacy-refused",
        category="contract_value",
        span_value="R$ 520000.00",
        utility_references=None,
    )
    result = _result(_band_transformation("contract_value", _BAND, "R$ 520000.00"))
    with pytest.raises(MissingUtilityReferencesError):
        score_utility(case_input, oracle, result, Treatment.TASK_AWARE, protocol_id="post-pilot-v5")


# --- d. hr/v1 and contracts/v1 refused under v5 (legacy-oracle reason) -----


def test_hr_v1_refused_under_v5():
    from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
    from adaptive_disclosure_gateway.experiments.scoring.utility import (
        MissingUtilityReferencesError,
    )

    hr_dir = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
    cases = load_hr_v1_cases(hr_dir)
    with pytest.raises(MissingUtilityReferencesError):
        check_corpus_protocol_compatibility(cases, "post-pilot-v5")


def test_contracts_v1_refused_under_v5():
    from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
    from adaptive_disclosure_gateway.experiments.scoring.utility import (
        MissingUtilityReferencesError,
    )

    contracts_dir = Path(__file__).parents[1] / "corpus" / "contracts" / "v1" / "cases"
    cases = load_hr_v1_cases(contracts_dir)
    with pytest.raises(MissingUtilityReferencesError):
        check_corpus_protocol_compatibility(cases, "post-pilot-v5")


# --- e. pre-run amount-format check: ALL cases, blocked included ------------


def test_pre_run_check_rejects_a_non_conforming_numeric_span_even_when_blocked():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v5-bad-format-blocked",
        category="salary",
        span_value="R$ 8.500,0",  # wrong cents digit count -- not in the v5 grammar
        utility_references=None,
        expected_block_request=True,
    )
    with pytest.raises(UnsupportedOriginalAmountFormatError) as excinfo:
        check_corpus_protocol_compatibility(
            [CorpusCase(input=case_input, oracle=oracle)], "post-pilot-v5"
        )
    assert "8.500,0" not in str(excinfo.value)
    assert "synthetic-v5-bad-format-blocked" in str(excinfo.value)
    assert "salary" in str(excinfo.value)


def test_pre_run_check_rejects_a_non_conforming_numeric_span_when_not_blocked():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v5-bad-format-open",
        category="contract_value",
        span_value="R$ 1.234",  # grouped, no cents -- rejected
        utility_references=[_ref("contract_value", ReferenceOperator.GREATER_THAN, "500.00")],
    )
    with pytest.raises(UnsupportedOriginalAmountFormatError):
        check_corpus_protocol_compatibility(
            [CorpusCase(input=case_input, oracle=oracle)], "post-pilot-v5"
        )


def test_pre_run_check_accepts_a_conforming_brazilian_span():
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v5-good-format",
        category="contract_value",
        span_value="R$ 520000,00",
        utility_references=[_ref("contract_value", ReferenceOperator.GREATER_THAN, "500000.00")],
    )
    check_corpus_protocol_compatibility(
        [CorpusCase(input=case_input, oracle=oracle)], "post-pilot-v5"
    )  # must not raise


def test_pre_run_check_is_not_applied_under_v3_or_v4():
    """The pre-run amount-format check is v5-only -- v3/v4 corpora with a
    non-conforming (e.g. malformed) oracle value must not be newly refused by
    this ticket merely for existing."""
    case_input, oracle = _synthetic_case(
        sample_id="synthetic-v3-bad-format-irrelevant",
        category="contract_value",
        span_value="R$ 1.234",
        utility_references=None,
    )
    check_corpus_protocol_compatibility(
        [CorpusCase(input=case_input, oracle=oracle)], "post-pilot-v3"
    )  # must not raise (v3 has no opted-in-reference requirement either)


def test_pre_run_check_runs_before_any_provider_call(tmp_path):
    """Behavioral proof (not just naming) that the v5 pre-run check runs
    before any provider is invoked, via the real ``run_pilot`` entrypoint
    over a tiny synthetic corpus directory with one non-conforming case."""

    case_yaml = """
input:
  sample_id: synthetic_v5_bad_amount
  task_family: authorized_salary_analysis
  text: |
    Employee: Jane Doe
    CPF: 111.222.333-44
    Salary: R$ 8.500,0
    Department: Engineering
  task: "Determine whether the salary is within band."
  domain: hr
  purpose: salary_analysis
  policy_version: hr-v1

oracle:
  sample_id: synthetic_v5_bad_amount
  expected_spans:
    - category: employee_name
      value: Jane Doe
      start: 10
      end: 18
      task_necessity: not_required
      expected_actions: [remove]
    - category: cpf
      value: 111.222.333-44
      start: 24
      end: 38
      task_necessity: not_required
      expected_actions: [remove]
    - category: salary
      value: "R$ 8.500,0"
      start: 47
      end: 57
      task_necessity: required
      expected_actions: [generalize]
    - category: department
      value: Engineering
      start: 70
      end: 81
      task_necessity: required
      expected_actions: [preserve]
  expected_block_request: false
  expected_answer: "irrelevant"
  answer_depends_on_categories: [salary, department]
  utility_references:
    - category: salary
      operator: greater_than
      value: "5000.00"
"""
    corpus_dir = tmp_path / "cases"
    corpus_dir.mkdir()
    (corpus_dir / "synthetic_v5_bad_amount.yaml").write_text(case_yaml, encoding="utf-8")

    calls = {"count": 0}

    class _CountingSpyProvider:
        provider_class = "fake"

        def generate(self, request):
            calls["count"] += 1
            raise AssertionError("provider must never be called")

    with pytest.raises(UnsupportedOriginalAmountFormatError):
        run_pilot(
            corpus_dir=corpus_dir,
            policy_dir=POLICY_DIR,
            corpus_version="synthetic/v5-pre-run-check",
            run_classification=PILOT_DEVELOPMENT,
            provider=_CountingSpyProvider(),
            protocol_id="post-pilot-v5",
        )
    assert calls["count"] == 0
