"""T10 / issue #8 -- items 12, 13, 14 of the acceptance-criteria checklist.

12. serialization is stable, once volatile fields (run id, timestamp,
    wall-clock timing) are excluded;
13. no-leak: the safe serialized result never carries a raw value, a
    pseudonym/original mapping, ``requester_id``, or raw task/response text;
14. pairwise comparisons (B0->B1, B1->B2, B2->B3, B3->B4) are internally
    consistent (each pairwise summary reflects exactly its two treatments'
    own independently-computed rates, matched by case, never a cartesian
    mismatch).
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.experiments.aggregation import (
    summarize_b3_to_b4,
    summarize_pairwise,
    summarize_treatment,
)
from adaptive_disclosure_gateway.experiments.case_result import deterministic_key, to_safe_dict
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.runner import run_pilot

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _pilot_results():
    return run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
    )


# --- 12. stable serialization, ignoring declared volatile fields -----------


def test_deterministic_key_is_identical_across_two_independent_runs_of_the_same_case():
    results_a = _pilot_results()
    results_b = _pilot_results()

    result_a = next(
        r for r in results_a[Treatment.TASK_AWARE] if r.identity.case_id == "hr_team_summary_001"
    )
    result_b = next(
        r for r in results_b[Treatment.TASK_AWARE] if r.identity.case_id == "hr_team_summary_001"
    )

    # The full safe dict differs (different run_id/timestamp/timing).
    full_a = to_safe_dict(result_a)
    full_b = to_safe_dict(result_b)
    assert full_a["metadata"] != full_b["metadata"]

    # The deterministic key -- everything except run metadata and
    # wall-clock measurements -- must be byte-for-byte identical.
    key_a = json.dumps(deterministic_key(result_a), sort_keys=True)
    key_b = json.dumps(deterministic_key(result_b), sort_keys=True)
    assert key_a == key_b


def test_deterministic_key_excludes_run_id_and_timestamp_and_latency():
    result = _pilot_results()[Treatment.DIRECT][0]
    key = deterministic_key(result)
    assert "metadata" not in key
    assert "stage_timings" not in key
    assert "provider_metrics" not in key
    assert "provider_metrics_deterministic" in key
    assert "latency_ms" not in key["provider_metrics_deterministic"]


def test_deterministic_key_still_differs_between_genuinely_different_cases():
    results = _pilot_results()
    result_a = results[Treatment.STATIC_SANITIZATION][0]
    result_b = results[Treatment.STATIC_SANITIZATION][1]
    assert result_a.identity.case_id != result_b.identity.case_id
    assert deterministic_key(result_a) != deterministic_key(result_b)


# --- 13. no-leak in the serialized safe output ------------------------------


def test_safe_dict_never_leaks_any_raw_span_value_from_any_case():
    from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases

    cases = load_hr_v1_cases(CORPUS_DIR)
    raw_values = {span.value for case in cases for span in case.oracle.expected_spans}
    # Sanity: real raw values exist to search for.
    assert raw_values

    results = _pilot_results()
    for treatment_results in results.values():
        for result in treatment_results:
            serialized = json.dumps(to_safe_dict(result))
            for value in raw_values:
                assert value not in serialized, (
                    f"raw value leaked into safe output for {result.identity.case_id}/"
                    f"{result.identity.treatment_code}"
                )


def test_safe_dict_never_carries_requester_id_or_the_audits_raw_capture_field():
    result = _pilot_results()[Treatment.REVERSIBLE_PSEUDONYMIZATION][0]
    serialized = to_safe_dict(result)
    assert "requester_id" not in json.dumps(serialized)
    assert serialized["audit"].get("raw") is None
    assert "raw" not in serialized["audit"] or serialized["audit"]["raw"] is None


def test_safe_dict_never_carries_the_pseudonym_vault_mapping():
    # The vault mapping would show up as an explicit pseudonym->original
    # dict; to_safe_dict must never construct one at all.
    result = _pilot_results()[Treatment.REVERSIBLE_PSEUDONYMIZATION][0]
    serialized = to_safe_dict(result)
    assert "vault" not in json.dumps(serialized).lower()


# --- 14. pairwise comparisons are internally consistent ---------------------


def test_pairwise_summary_case_count_matches_the_intersection_of_both_sides():
    results = _pilot_results()
    summary = summarize_pairwise(results[Treatment.DIRECT], results[Treatment.STATIC_SANITIZATION])
    assert summary.case_count == 13
    assert summary.from_treatment == "b0"
    assert summary.to_treatment == "b1"


def test_pairwise_summary_never_mixes_a_case_from_one_treatment_with_a_different_case_from_the_other():
    results = _pilot_results()
    # Drop one case from the "to" side -- the pairwise summary must reflect
    # exactly 12 matched cases, not silently pad or misalign.
    to_side = [
        r
        for r in results[Treatment.REVERSIBLE_PSEUDONYMIZATION]
        if r.identity.case_id != "hr_team_summary_001"
    ]
    summary = summarize_pairwise(results[Treatment.STATIC_SANITIZATION], to_side)
    assert summary.case_count == 12


def test_full_pairwise_chain_b0_b1_b2_b3_b4_is_self_consistent_with_the_per_treatment_summaries():
    results = _pilot_results()
    sequence = [
        Treatment.DIRECT,
        Treatment.STATIC_SANITIZATION,
        Treatment.REVERSIBLE_PSEUDONYMIZATION,
        Treatment.TASK_AWARE,
        Treatment.POLICY_GOVERNED,
    ]
    per_treatment = {t: summarize_treatment(results[t]) for t in sequence}

    for from_t, to_t in pairwise(sequence):
        pairwise_summary = summarize_pairwise(results[from_t], results[to_t])
        # Every case is present in every treatment's result list here (the
        # pilot ran the same 13 cases through all five treatments), so the
        # pairwise rate must equal the from/to treatment's own full-corpus
        # rate exactly -- proving summarize_pairwise does not silently
        # recompute a different, inconsistent rate.
        assert pairwise_summary.conformant_rate_from == per_treatment[from_t].conformant_rate
        assert pairwise_summary.conformant_rate_to == per_treatment[to_t].conformant_rate


def test_b3_to_b4_summary_flags_the_frozen_hr_salary_analysis_003_case_as_not_policy_restricted():
    results = _pilot_results()
    summary = summarize_b3_to_b4(results[Treatment.TASK_AWARE], results[Treatment.POLICY_GOVERNED])
    case = next(c for c in summary.cases if c.case_id == "hr_salary_analysis_003")
    # Under hr-v1 (the corpus's own policy version), B4's policy-permitted
    # space for salary/salary_analysis is identical to B3's own baseline
    # space -- salary's own divergence against the oracle (GENERALIZE, not
    # PRESERVE) is a task-analysis property, not a policy restriction, and
    # must show up as such here.
    assert case.policy_restricted is False
    assert case.impossible_under_policy is False
    # But the case's *overall* action profile is NOT identical between B3
    # and B4: hr-v1's employee_name/department rules are hard
    # (PSEUDONYMIZE/PRESERVE, unconditionally -- no TASK_DEPENDENT branch at
    # all for either category), so B4 discloses both regardless of what
    # this case's task actually needs, while B3's task-aware layer picks
    # each category's own least-disclosing action for a NOT_RELEVANT read
    # (REMOVE for both). This makes B4 *more* disclosing than B3 for this
    # case overall -- a real, measured pilot finding, not a restriction (see
    # ``docs/hr-policy-matrix.md``: hr-v1 has no override for either
    # category, unlike hr-v2/hr-v3).
    assert case.same_action_profile is False
    assert case.exposure_direction == "b4_more"
