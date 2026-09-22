"""Regression pin for ``hr_salary_analysis_003`` (T10 / issue #8's closing
brief): the one documented, frozen B3-vs-oracle divergence
(``scripts/report_b3_corpus_divergence.py``) must:

1. still exist under B3 -- Task-aware exactly as documented (GENERALIZE
   chosen, PRESERVE is the only oracle-acceptable action) -- never
   "corrected" by tuning the analyzer or the corpus;
2. remain visible in the runner's own output as a *conformance* divergence
   (``score.conformance``), not silently absorbed or hidden;
3. have its utility consequence (the GENERALIZE band straddling the stated
   reference floor, making the comparison undecidable) measured
   *separately*, as a distinct utility outcome, never fused into the
   conformance divergence itself;
4. show B4 -- Policy-governed reproducing the identical divergence under
   hr-v1 (the corpus's own policy version, which has no override that would
   change salary's task-dependent action space relative to B3's own
   baseline) -- with ``policy_restricted``/``impossible_under_policy`` both
   ``False``, proving the divergence's cause is task-analysis, not policy.

No exception is taken, no analyzer/corpus edit is made to force
convergence -- this test exists specifically to fail if either happens by
accident.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.domain import DisclosureAction, Treatment
from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.scoring import score_case
from adaptive_disclosure_gateway.policies import PolicyRepository

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"
SAMPLE_ID = "hr_salary_analysis_003"


def _run(treatment: Treatment):
    cases = {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}
    case = cases[SAMPLE_ID]
    policy_repo = PolicyRepository.from_directory(POLICY_DIR)
    execution = execute_case(
        case_input=case.input,
        treatment=treatment,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repo,
        protocol_id="post-pilot-v3",
    )
    return case, score_case(case.input, case.oracle, execution)


def test_b3_still_generalizes_salary_where_the_oracle_accepts_only_preserve():
    case, score = _run(Treatment.TASK_AWARE)
    salary_expected = next(s for s in case.oracle.expected_spans if s.category == "salary")
    assert tuple(salary_expected.expected_actions) == (DisclosureAction.PRESERVE,)

    salary_conformance = next(s for s in score.conformance.spans if s.category == "salary")
    assert salary_conformance.resolved_action == DisclosureAction.GENERALIZE
    assert salary_conformance.outcome == "nonconformant"


def test_the_divergence_is_measured_as_utility_indeterminate_not_a_conformance_relabel():
    _, score = _run(Treatment.TASK_AWARE)
    salary_utility = next(c for c in score.utility.by_category if c.category == "salary")
    assert salary_utility.outcome == "indeterminate"
    assert salary_utility.reason == "generalized_band_ambiguous"
    # Conformance and utility are two independently-populated scores on the
    # same CaseScore -- neither was derived from the other.
    salary_conformance = next(s for s in score.conformance.spans if s.category == "salary")
    assert salary_conformance.outcome == "nonconformant"


def test_b4_reproduces_the_identical_divergence_under_hr_v1_with_no_policy_effect():
    _, score = _run(Treatment.POLICY_GOVERNED)
    salary_conformance = next(s for s in score.conformance.spans if s.category == "salary")
    assert salary_conformance.resolved_action == DisclosureAction.GENERALIZE
    assert salary_conformance.outcome == "nonconformant"

    salary_utility = next(c for c in score.utility.by_category if c.category == "salary")
    assert salary_utility.outcome == "indeterminate"

    assert score.outcomes.policy_restricted is False
    assert score.outcomes.impossible_under_policy is False
    assert score.outcomes.policy_block is False
    assert score.outcomes.blocked is False


def test_this_case_is_never_silently_dropped_from_the_scored_corpus():
    case, score = _run(Treatment.TASK_AWARE)
    assert case.input.sample_id == SAMPLE_ID
    assert score.conformance.total == len(case.oracle.expected_spans) == 4
