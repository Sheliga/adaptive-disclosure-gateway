"""PR #35 review, blocker 2: the detector's own precision/recall/F1, scored
against the corpus's frozen ``expected_spans`` from spans genuinely captured
during a real execution -- never a second, independently re-run detection
pass.

Covers:

- ``RecordingDetector`` captures exactly the spans the real ``Detector``
  returned, category/offset-only, never the detected value;
- ``execute_case`` wires that capture into ``CaseExecution.detected_text_spans``
  without ever touching ground truth;
- ``score_detector_case``'s exact-match TP/FP/FN rule, including duplicate
  keys and empty inputs;
- precision/recall/F1 with the documented zero-denominator semantics
  (``None``, never an invented number);
- aggregation (micro and macro) across several cases;
- the real pilot's aggregate detector score is present, well-formed and
  never leaks a raw span value.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.corpus.models import ExpectedSpan, TaskNecessity
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureAction, Treatment
from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
from adaptive_disclosure_gateway.experiments.detector_capture import (
    DetectedSpanRef,
    RecordingDetector,
)
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.scoring.detector_scoring import (
    DetectorSpanResult,
    aggregate_detector_scores,
    score_detector_case,
)
from adaptive_disclosure_gateway.policies import PolicyRepository

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def _one_case(sample_id: str):
    cases = {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}
    return cases[sample_id]


def _expected_span(category: str, value: str, start: int, end: int) -> ExpectedSpan:
    return ExpectedSpan(
        category=category,
        value=value,
        start=start,
        end=end,
        task_necessity=TaskNecessity.REQUIRED,
        expected_actions=[DisclosureAction.PRESERVE],
    )


# --- RecordingDetector: captures real spans, category/offset-only ----------


def test_recording_detector_captures_the_real_detectors_own_output_verbatim():
    real = Detector()
    recording = RecordingDetector(real)
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\n"

    spans = recording.detect(text)

    assert spans == real.detect(text)  # deterministic detector -- same input, same output
    assert recording.text_spans == tuple(
        DetectedSpanRef(category=s.category, start=s.start, end=s.end) for s in spans
    )


def test_recording_detector_never_records_the_detected_value():
    recording = RecordingDetector(Detector())
    recording.detect("Employee: Ana Souza\nCPF: 123.456.789-09\n")

    for ref in recording.text_spans:
        assert not hasattr(ref, "value")


def test_recording_detector_text_spans_is_the_first_call_not_the_second():
    recording = RecordingDetector(Detector())
    recording.detect("Employee: Ana Souza\n")
    recording.detect("a second, unrelated call")

    assert len(recording.calls) == 2
    assert recording.text_spans == recording.calls[0]
    assert recording.text_spans != recording.calls[1] or recording.calls[0] == recording.calls[1]


def test_recording_detector_text_spans_is_empty_before_any_call():
    recording = RecordingDetector(Detector())
    assert recording.text_spans == ()


# --- execute_case wires captured spans in, ground-truth-free ---------------


def test_execute_case_populates_detected_text_spans_from_the_real_run():
    case = _one_case("hr_team_summary_001")
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    assert execution.detected_text_spans
    for ref in execution.detected_text_spans:
        assert isinstance(ref, DetectedSpanRef)
        assert ref.start >= 0
        assert ref.end > ref.start


# --- score_detector_case: exact-match TP/FP/FN ------------------------------


def test_perfect_match_scores_full_precision_recall_f1():
    expected = [_expected_span("employee_name", "Ana Souza", 0, 9)]
    detected = [DetectedSpanRef(category="employee_name", start=0, end=9)]

    score = score_detector_case(expected, detected)

    assert score.true_positive_count == 1
    assert score.false_positive_count == 0
    assert score.false_negative_count == 0
    assert score.precision == 1.0
    assert score.recall == 1.0
    assert score.f1 == 1.0
    assert score.spans == (DetectorSpanResult("employee_name", 0, 9, "true_positive"),)


def test_missed_span_is_a_false_negative_not_a_false_positive():
    expected = [_expected_span("salary", "R$ 1000", 0, 7)]
    detected: list[DetectedSpanRef] = []

    score = score_detector_case(expected, detected)

    assert score.true_positive_count == 0
    assert score.false_negative_count == 1
    assert score.false_positive_count == 0
    assert score.recall == 0.0
    assert score.precision is None  # no detected spans at all -- denominator is zero
    assert score.f1 is None


def test_extra_detected_span_is_a_false_positive_not_a_false_negative():
    expected: list[ExpectedSpan] = []
    detected = [DetectedSpanRef(category="salary", start=0, end=7)]

    score = score_detector_case(expected, detected)

    assert score.false_positive_count == 1
    assert score.true_positive_count == 0
    assert score.false_negative_count == 0
    assert score.precision == 0.0
    assert score.recall is None  # no expected spans at all -- denominator is zero
    assert score.f1 is None


def test_category_mismatch_at_the_same_offsets_counts_as_both_fn_and_fp():
    expected = [_expected_span("salary", "R$ 1000", 0, 7)]
    detected = [DetectedSpanRef(category="department", start=0, end=7)]

    score = score_detector_case(expected, detected)

    assert score.true_positive_count == 0
    assert score.false_negative_count == 1
    assert score.false_positive_count == 1
    assert score.precision == 0.0
    assert score.recall == 0.0
    assert score.f1 == 0.0


def test_partial_offset_overlap_is_never_credited_as_a_true_positive():
    """The documented matching rule is exact-match only -- a detected span
    overlapping but not exactly matching an oracle span's offsets must not
    be silently credited.
    """
    expected = [_expected_span("employee_name", "Ana Souza", 0, 9)]
    detected = [DetectedSpanRef(category="employee_name", start=0, end=8)]  # off by one

    score = score_detector_case(expected, detected)

    assert score.true_positive_count == 0
    assert score.false_negative_count == 1
    assert score.false_positive_count == 1


def test_duplicate_keys_on_both_sides_are_matched_positionally_and_determinately():
    expected = [
        _expected_span("employee_name", "Ana Souza", 0, 9),
        _expected_span("employee_name", "Ana Souza", 20, 29),
    ]
    detected = [
        DetectedSpanRef(category="employee_name", start=0, end=9),
        DetectedSpanRef(category="employee_name", start=20, end=29),
    ]

    score = score_detector_case(expected, detected)

    assert score.true_positive_count == 2
    assert score.false_positive_count == 0
    assert score.false_negative_count == 0


def test_empty_case_no_expected_no_detected_is_fully_undefined_not_invented():
    score = score_detector_case([], [])
    assert score.true_positive_count == 0
    assert score.false_positive_count == 0
    assert score.false_negative_count == 0
    assert score.precision is None
    assert score.recall is None
    assert score.f1 is None


# --- aggregation: micro and macro -------------------------------------------


def test_micro_aggregate_sums_counts_across_cases_before_computing_rates():
    case_a = score_detector_case(
        [_expected_span("employee_name", "Ana Souza", 0, 9)],
        [DetectedSpanRef(category="employee_name", start=0, end=9)],
    )
    case_b = score_detector_case(
        [_expected_span("salary", "R$ 1000", 0, 7)],
        [],  # missed entirely
    )

    aggregate = aggregate_detector_scores([case_a, case_b])

    assert aggregate.case_count == 2
    assert aggregate.true_positive_count == 1
    assert aggregate.false_negative_count == 1
    assert aggregate.false_positive_count == 0
    # micro: 1 TP / (1 TP + 1 FN) = 0.5 recall; precision is 1 TP / 1 detected = 1.0
    assert aggregate.micro_precision == 1.0
    assert aggregate.micro_recall == 0.5
    assert aggregate.micro_f1 is not None


def test_macro_aggregate_skips_cases_with_an_undefined_rate_rather_than_treating_it_as_zero():
    defined = score_detector_case(
        [_expected_span("employee_name", "Ana Souza", 0, 9)],
        [DetectedSpanRef(category="employee_name", start=0, end=9)],
    )
    undefined_precision = score_detector_case([], [])  # both rates None

    aggregate = aggregate_detector_scores([defined, undefined_precision])

    # If the undefined case's None had been treated as 0.0, macro_precision
    # would be 0.5 instead of 1.0.
    assert aggregate.macro_precision == 1.0
    assert aggregate.macro_recall == 1.0


def test_aggregate_of_no_cases_is_fully_none_not_invented():
    aggregate = aggregate_detector_scores([])
    assert aggregate.case_count == 0
    assert aggregate.micro_precision is None
    assert aggregate.micro_recall is None
    assert aggregate.micro_f1 is None
    assert aggregate.macro_precision is None


# --- end-to-end: score_case wires detector scoring into CaseScore ----------


def test_score_case_attaches_a_well_formed_detector_score_for_a_real_corpus_case():
    from adaptive_disclosure_gateway.experiments.scoring import score_case

    case = _one_case("hr_team_summary_001")
    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    score = score_case(case.input, case.oracle, execution)

    assert score.detector.true_positive_count + score.detector.false_negative_count == len(
        case.oracle.expected_spans
    )
    assert score.detector.precision is None or 0.0 <= score.detector.precision <= 1.0
    assert score.detector.recall is None or 0.0 <= score.detector.recall <= 1.0


def test_detector_score_never_leaks_any_raw_span_value_when_serialized():
    import json

    from adaptive_disclosure_gateway.experiments.case_result import CaseResult, to_safe_dict
    from adaptive_disclosure_gateway.experiments.run_identity import new_run_metadata
    from adaptive_disclosure_gateway.experiments.scoring import score_case

    case = _one_case("hr_team_summary_001")
    raw_values = {span.value for span in case.oracle.expected_spans}
    assert raw_values

    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )
    score = score_case(case.input, case.oracle, execution)
    result = CaseResult(
        identity=execution.identity,
        metadata=new_run_metadata("test-run"),
        score=score,
        case_execution=execution,
    )
    serialized = json.dumps(to_safe_dict(result)["score"]["detector"])
    for value in raw_values:
        assert value not in serialized
