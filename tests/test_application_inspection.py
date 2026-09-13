"""T27 / issue #69: ``application/inspection.py``'s ``build_inspection`` --
the visual diff/inspector projection for the advisor demo.

Every test here uses the REAL treatment classes (``StaticSanitizer`` --
B1, ``ReversiblePseudonymizer`` -- B2, ``TaskAwareDiscloser`` -- B3,
``PolicyGovernedDiscloser`` -- B4, ``DirectDiscloser`` -- B0) and the real
``pipeline.decide_disclosure`` decision phase, exactly like
``tests/test_telemetry_privacy.py``'s own style -- only the ``Detector`` is
ever a stub, injected so a test can pin exact span offsets (including
adversarial ones a naive string-diff would get wrong) rather than depending
on the built-in regex/label rules. Values are synthetic throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from adaptive_disclosure_gateway.application.inspection import build_inspection
from adaptive_disclosure_gateway.detection.overlap import resolve_overlaps
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    DisclosureResult,
    GovernanceContext,
    PolicyDecision,
    SensitiveSpan,
    Transformation,
)
from adaptive_disclosure_gateway.pipeline import DisclosureDecision, decide_disclosure
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.task_analysis.base import TaskAnalysis, TaskRelevance
from adaptive_disclosure_gateway.transformations import (
    PolicyGovernedDiscloser,
    ReversiblePseudonymizer,
    StaticSanitizer,
    TaskAwareDiscloser,
)
from adaptive_disclosure_gateway.transformations.direct_disclosure import DirectDiscloser
from adaptive_disclosure_gateway.vault import InMemoryVault

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
        "requester_role": "hr_analyst",
        "session_id": "demo-session",
    }
    values.update(overrides)
    return GovernanceContext(**values)


@dataclass
class _StubDetector:
    """Reports fixed spans for one exact ``text`` string, and nothing for
    any other (in particular, ``request.task`` -- so the fail-closed
    task-only check never fires unless a test wires it in on purpose via
    ``by_text``).
    """

    by_text: dict[str, list[SensitiveSpan]] = field(default_factory=dict)

    def detect(self, text: str) -> list[SensitiveSpan]:
        return list(self.by_text.get(text, []))


def _span(category: str, value: str, start: int) -> SensitiveSpan:
    return SensitiveSpan(category=category, value=value, start=start, end=start + len(value))


def _decide(treatment, text: str, task: str, spans: list[SensitiveSpan], **context_overrides):
    request = DisclosureRequest(text=text, task=task, context=_context(**context_overrides))
    detector = _StubDetector(by_text={text: spans})
    return decide_disclosure(treatment, request, detector=detector)


def _by_category(inspection):
    return {
        segment.category: segment for segment in inspection.segments if segment.category is not None
    }


def _assert_concatenation_invariants(inspection, text: str, external_payload: str) -> None:
    assert "".join(segment.original for segment in inspection.segments) == text
    assert "".join(segment.disclosed for segment in inspection.segments) == external_payload


# --- B1 -- Static Sanitization -----------------------------------------------


def test_b1_static_sanitization_segments_match_transformations():
    """REMOVE (employee_name/cpf), GENERALIZE (salary), PRESERVE (department)
    -- B1's fixed ``ACTIONS`` mapping (``transformations/static_sanitization.py``)
    applied to the HR fixture categories.
    """
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Eng\n"
    spans = [
        _span("employee_name", "Ana Souza", text.index("Ana Souza")),
        _span("cpf", "123.456.789-09", text.index("123.456.789-09")),
        _span("salary", "R$ 8500.00", text.index("R$ 8500.00")),
        _span("department", "Eng", text.index("Eng")),
    ]
    decision = _decide(StaticSanitizer(), text, "summarize", spans)
    assert decision.result.status == "allowed"

    inspection = build_inspection(text, decision)

    assert inspection.available is True
    assert inspection.unavailable_reason is None
    by_category = _by_category(inspection)
    assert by_category["employee_name"].action is DisclosureAction.REMOVE
    assert by_category["employee_name"].disclosed == ""
    assert by_category["cpf"].action is DisclosureAction.REMOVE
    assert by_category["salary"].action is DisclosureAction.GENERALIZE
    assert by_category["salary"].original == "R$ 8500.00"
    assert by_category["department"].action is DisclosureAction.PRESERVE
    assert by_category["department"].disclosed == "Eng"
    for segment in inspection.segments:
        if segment.category is not None:
            transformation = next(
                t for t in decision.result.transformations if t.category == segment.category
            )
            assert segment.action is transformation.action
            assert segment.category == transformation.category
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


# --- B2 -- Reversible Pseudonymization ---------------------------------------


def test_b2_reversible_pseudonymization_segments_match_transformations():
    """PSEUDONYMIZE (employee_name/cpf), GENERALIZE (salary), PRESERVE
    (department) -- B2's ``ACTIONS`` mapping
    (``transformations/reversible_pseudonymization.py``).
    """
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Eng\n"
    spans = [
        _span("employee_name", "Ana Souza", text.index("Ana Souza")),
        _span("cpf", "123.456.789-09", text.index("123.456.789-09")),
        _span("salary", "R$ 8500.00", text.index("R$ 8500.00")),
        _span("department", "Eng", text.index("Eng")),
    ]
    treatment = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    decision = _decide(treatment, text, "summarize", spans)
    assert decision.result.status == "allowed"

    inspection = build_inspection(text, decision)

    by_category = _by_category(inspection)
    assert by_category["employee_name"].action is DisclosureAction.PSEUDONYMIZE
    assert "Ana Souza" not in by_category["employee_name"].disclosed
    assert by_category["employee_name"].disclosed  # a pseudonym was emitted
    assert by_category["salary"].action is DisclosureAction.GENERALIZE
    assert by_category["department"].action is DisclosureAction.PRESERVE
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


# --- B3 -- Task-aware ---------------------------------------------------------


class _FixedRelevanceAnalyzer:
    """Ignores the task text; reports a fixed, per-category relevance --
    isolating the segment-building assertions from the deterministic
    analyzer's own heuristics, mirroring
    ``tests/test_policy_governed.py``'s ``_StubAnalyzer``.
    """

    def __init__(self, relevance_by_category: dict[str, TaskRelevance]) -> None:
        self._relevance = relevance_by_category

    def analyze(self, task, categories) -> TaskAnalysis:
        return TaskAnalysis(
            relevance_by_category={category: self._relevance[category] for category in categories}
        )


def test_b3_task_aware_segments_match_transformations():
    """REMOVE (cpf, NOT_RELEVANT -> least-disclosing), PSEUDONYMIZE
    (employee_name, RELEVANT_WITHOUT_EXACT_VALUE -> first non-REMOVE),
    GENERALIZE (salary, RELEVANT_WITHOUT_EXACT_VALUE), PRESERVE (department,
    RELEVANT_WITH_EXACT_VALUE) -- all four resolved from B3's own generic
    per-category action space (``task_aware.TASK_AWARE_ACTION_SPACES``) via
    a fixed-relevance stub analyzer.
    """
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Eng\n"
    spans = [
        _span("employee_name", "Ana Souza", text.index("Ana Souza")),
        _span("cpf", "123.456.789-09", text.index("123.456.789-09")),
        _span("salary", "R$ 8500.00", text.index("R$ 8500.00")),
        _span("department", "Eng", text.index("Eng")),
    ]
    analyzer = _FixedRelevanceAnalyzer(
        {
            "employee_name": TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE,
            "cpf": TaskRelevance.NOT_RELEVANT,
            "salary": TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE,
            "department": TaskRelevance.RELEVANT_WITH_EXACT_VALUE,
        }
    )
    treatment = TaskAwareDiscloser(
        vault=InMemoryVault(),
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        task_analyzer=analyzer,
    )
    decision = _decide(treatment, text, "irrelevant task text", spans)
    assert decision.result.status == "allowed"

    inspection = build_inspection(text, decision)

    by_category = _by_category(inspection)
    assert by_category["employee_name"].action is DisclosureAction.PSEUDONYMIZE
    assert by_category["cpf"].action is DisclosureAction.REMOVE
    assert by_category["salary"].action is DisclosureAction.GENERALIZE
    assert by_category["department"].action is DisclosureAction.PRESERVE
    assert by_category["department"].disclosed == "Eng"
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


# --- B4 -- Policy-governed -----------------------------------------------------


def test_b4_policy_governed_segments_match_transformations():
    """hr-v1 policy resolves: employee_name -> hard PSEUDONYMIZE, cpf ->
    hard REMOVE, department -> hard PRESERVE, salary -> TASK_DEPENDENT with
    ``purpose=salary_analysis`` widening ``allowed_actions`` to
    ``[remove, generalize, preserve]`` (see ``configs/policies/hr-v1.yaml``);
    a RELEVANT_WITHOUT_EXACT_VALUE stub relevance resolves salary to
    GENERALIZE (the first non-REMOVE action in that space). All four
    disclosure actions therefore appear in this single test.
    """
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Eng\n"
    spans = [
        _span("employee_name", "Ana Souza", text.index("Ana Souza")),
        _span("cpf", "123.456.789-09", text.index("123.456.789-09")),
        _span("salary", "R$ 8500.00", text.index("R$ 8500.00")),
        _span("department", "Eng", text.index("Eng")),
    ]
    analyzer = _FixedRelevanceAnalyzer(
        {
            "employee_name": TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE,
            "cpf": TaskRelevance.NOT_RELEVANT,
            "salary": TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE,
            "department": TaskRelevance.RELEVANT_WITH_EXACT_VALUE,
        }
    )
    treatment = PolicyGovernedDiscloser(
        vault=InMemoryVault(),
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        task_analyzer=analyzer,
    )
    decision = _decide(treatment, text, "irrelevant task text", spans, purpose="salary_analysis")
    assert decision.result.status == "allowed"

    inspection = build_inspection(text, decision)

    by_category = _by_category(inspection)
    assert by_category["employee_name"].action is DisclosureAction.PSEUDONYMIZE
    assert by_category["cpf"].action is DisclosureAction.REMOVE
    assert by_category["salary"].action is DisclosureAction.GENERALIZE
    assert by_category["department"].action is DisclosureAction.PRESERVE
    actions_present = {segment.action for segment in inspection.segments if segment.action}
    assert actions_present == {
        DisclosureAction.PSEUDONYMIZE,
        DisclosureAction.REMOVE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    }
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


# --- B0 -- Direct --------------------------------------------------------------


def test_b0_direct_is_a_single_untouched_segment():
    """B0's own ``Transformation`` is a synthetic, whole-text audit entry
    (category ``"direct_disclosure"``) that never corresponds to a real
    detected span -- see ``application/inspection.py``'s module docstring
    for why the structured per-span alignment cannot and must not succeed
    for it, and why the fallback below is what actually applies.
    """
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\n"
    spans = [
        _span("employee_name", "Ana Souza", text.index("Ana Souza")),
        _span("cpf", "123.456.789-09", text.index("123.456.789-09")),
    ]
    decision = _decide(DirectDiscloser(), text, "summarize", spans)
    assert decision.result.status == "allowed"
    assert decision.result.external_payload == text

    inspection = build_inspection(text, decision)

    assert inspection.available is True
    assert inspection.unavailable_reason is None
    assert len(inspection.segments) == 1
    segment = inspection.segments[0]
    assert segment.action is None
    assert segment.category is None
    assert segment.original == text
    assert segment.disclosed == text


def test_b0_direct_over_empty_text_has_no_segments():
    decision = _decide(DirectDiscloser(), "", "summarize", [])
    assert decision.result.external_payload == ""

    inspection = build_inspection("", decision)

    assert inspection.available is True
    assert inspection.segments == ()


# --- mis-anchoring guard -------------------------------------------------------


def test_mis_anchored_value_attributes_the_transformed_segment_to_the_reported_occurrence():
    """The same value appears twice; the stub detector reports only the
    SECOND occurrence. A string-search/replace implementation would remove
    or flag BOTH occurrences (or the wrong one); the span-based projection
    must transform only the reported occurrence and leave the first, textually
    identical occurrence untouched.
    """
    text = "Contact Ana Souza about Ana Souza's transfer.\n"
    first_offset = text.index("Ana Souza")
    second_offset = text.index("Ana Souza", first_offset + 1)
    assert first_offset != second_offset
    spans = [_span("employee_name", "Ana Souza", second_offset)]

    decision = _decide(StaticSanitizer(), text, "summarize", spans)
    assert decision.result.status == "allowed"
    # The untouched first occurrence must still read as plain text in the
    # payload -- pins that the treatment itself only removed the reported
    # occurrence (sanity for the fixture, not for the inspector).
    assert decision.result.external_payload.count("Ana Souza") == 1

    inspection = build_inspection(text, decision)

    assert inspection.available is True
    transformed = [s for s in inspection.segments if s.category == "employee_name"]
    assert len(transformed) == 1
    assert transformed[0].action is DisclosureAction.REMOVE
    assert transformed[0].disclosed == ""
    # The untouched segment(s) must still contain the FIRST occurrence as
    # plain text -- proving the transform was attributed to the second one.
    untouched_text = "".join(s.original for s in inspection.segments if s.category is None)
    assert untouched_text.count("Ana Souza") == 1
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


def test_repeated_value_both_detected_gets_two_transformed_segments_with_the_same_b2_pseudonym():
    text = "Contact Ana Souza. Reassign Ana Souza's cases.\n"
    first_offset = text.index("Ana Souza")
    second_offset = text.index("Ana Souza", first_offset + 1)
    spans = [
        _span("employee_name", "Ana Souza", first_offset),
        _span("employee_name", "Ana Souza", second_offset),
    ]
    treatment = ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )
    decision = _decide(treatment, text, "summarize", spans)
    assert decision.result.status == "allowed"

    inspection = build_inspection(text, decision)

    transformed = [s for s in inspection.segments if s.category == "employee_name"]
    assert len(transformed) == 2
    assert transformed[0].disclosed == transformed[1].disclosed
    assert transformed[0].disclosed != ""
    assert "Ana Souza" not in transformed[0].disclosed
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


# --- unicode / boundary edge cases ---------------------------------------------


def test_unicode_multiline_adjacent_and_boundary_spans():
    """Astral character (an emoji, one Python code point) at the very start
    of the text; a combining mark inside a value; ``\\r\\n``/``\\n`` in
    untouched text; two adjacent spans (no gap between them); a span ending
    exactly at the end of the text.
    """
    span_a_value = "\U0001f600Ana"  # astral char + text, at offset 0
    middle_untouched = "\r\nDept: "
    span_b_value = "Engineering"
    span_c_value = "café@x.com"  # "cafe" + COMBINING ACUTE ACCENT + rest
    trailing_untouched = "\ndone: "
    span_d_value = "5551234"

    text = (
        span_a_value
        + middle_untouched
        + span_b_value
        + span_c_value
        + trailing_untouched
        + span_d_value
    )
    span_a_start = 0
    span_b_start = len(span_a_value) + len(middle_untouched)
    span_c_start = span_b_start + len(span_b_value)  # adjacent to span_b
    span_d_start = span_c_start + len(span_c_value) + len(trailing_untouched)
    assert span_d_start + len(span_d_value) == len(text)  # ends exactly at text end

    spans = [
        _span("employee_name", span_a_value, span_a_start),
        _span("department", span_b_value, span_b_start),
        _span("email", span_c_value, span_c_start),
        _span("phone", span_d_value, span_d_start),
    ]
    decision = _decide(StaticSanitizer(), text, "summarize", spans)
    assert decision.result.status == "allowed"

    inspection = build_inspection(text, decision)

    assert inspection.available is True
    assert len(inspection.segments) == 6
    kinds = [(s.category, s.action) for s in inspection.segments]
    assert kinds == [
        ("employee_name", DisclosureAction.REMOVE),
        (None, None),
        ("department", DisclosureAction.PRESERVE),
        ("email", DisclosureAction.REMOVE),
        (None, None),
        ("phone", DisclosureAction.REMOVE),
    ]
    assert inspection.segments[1].original == middle_untouched
    assert inspection.segments[4].original == trailing_untouched
    assert inspection.segments[2].disclosed == span_b_value
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


# --- overlapping spans ----------------------------------------------------------


def test_overlapping_spans_follow_resolve_overlaps_exactly_like_the_payload():
    """A shorter ``cpf`` span overlaps a longer ``employee_name`` span; per
    ``detection.overlap.resolve_overlaps``, the longest span wins. The
    treatment's own ``sanitize`` resolves the same overlap internally to
    build the payload -- the inspector must land on the identical winner.
    """
    text = "XCPFHOLDERX and more text\n"
    short = _span("cpf", "CPFHOLDER"[:5], 1)  # "CPFHO", len 5
    long = _span("employee_name", "CPFHOLDER", 1)  # len 9, overlaps `short`
    decision = _decide(StaticSanitizer(), text, "summarize", [short, long])
    assert decision.result.status == "allowed"
    assert len(decision.result.transformations) == 1
    assert decision.result.transformations[0].category == "employee_name"

    inspection = build_inspection(text, decision)

    assert inspection.available is True
    transformed = [s for s in inspection.segments if s.category is not None]
    assert len(transformed) == 1
    assert transformed[0].category == "employee_name"
    assert transformed[0].original == "CPFHOLDER"
    _assert_concatenation_invariants(inspection, text, decision.result.external_payload)


# --- alignment failure ------------------------------------------------------------


def test_structurally_invalid_span_fails_closed_without_raising():
    """``resolve_overlaps`` raises ``ValueError`` on a structurally invalid
    span (only reachable via ``model_construct``, bypassing normal
    validation) -- ``build_inspection`` must catch it and fail closed rather
    than propagate.
    """
    malformed_span = SensitiveSpan.model_construct(category="cpf", value="123", start=-1, end=-1)
    result = DisclosureResult(
        external_payload="something else entirely",
        decisions=[
            PolicyDecision(
                category="cpf",
                action=DisclosureAction.REMOVE,
                reason="test",
                allowed_actions=[DisclosureAction.REMOVE],
            )
        ],
        transformations=[
            Transformation(
                category="cpf", original="123", transformed=None, action=DisclosureAction.REMOVE
            )
        ],
        status="allowed",
    )
    decision = DisclosureDecision(spans=[malformed_span], result=result)

    inspection = build_inspection("some unrelated text", decision)

    assert inspection.available is False
    assert inspection.unavailable_reason == "alignment_failed"
    assert inspection.segments == ()


def test_mismatched_transformation_category_fails_closed_without_raising():
    """A decision whose transformation's category disagrees with its
    corresponding span's category (a state normal treatment code cannot
    produce, but a monkeypatched/hand-built decision can) must fail closed,
    not silently mislabel the segment."""
    text = "Value: 12345\n"
    span = _span("cpf", "12345", text.index("12345"))
    result = DisclosureResult(
        external_payload="Value: [REDACTED-DIFFERENTLY]\n",
        decisions=[],
        transformations=[
            Transformation(
                category="employee_name",  # disagrees with span.category="cpf"
                original="12345",
                transformed=None,
                action=DisclosureAction.REMOVE,
            )
        ],
        status="allowed",
    )
    decision = DisclosureDecision(spans=[span], result=result)

    inspection = build_inspection(text, decision)

    assert inspection.available is False
    assert inspection.unavailable_reason == "alignment_failed"
    assert inspection.segments == ()


# --- blocked ------------------------------------------------------------------


def test_blocked_decision_is_unavailable_and_never_echoes_the_original_text():
    text = "Medical notes: Reports chronic migraine.\n"
    spans = [_span("medical_data", "Reports chronic migraine", text.index("Reports"))]
    decision = _decide(StaticSanitizer(), text, "summarize", spans)
    assert decision.result.status == "blocked"

    inspection = build_inspection(text, decision)

    assert inspection.available is False
    assert inspection.unavailable_reason == "blocked"
    assert inspection.segments == ()


def test_sensitive_value_only_in_the_task_blocks_and_is_unavailable():
    """The fail-closed task check (``pipeline.decide_disclosure``) blocks
    the whole request when the DETECTOR finds something in ``request.task``
    -- the text itself may be entirely clean.
    """
    text = "Nothing sensitive here.\n"
    task = "Summarize for Ana Souza, CPF 123.456.789-09.\n"
    request = DisclosureRequest(text=text, task=task, context=_context())
    detector = _StubDetector(
        by_text={task: [_span("employee_name", "Ana Souza", task.index("Ana Souza"))]}
    )
    decision = decide_disclosure(StaticSanitizer(), request, detector=detector)
    assert decision.result.status == "blocked"

    inspection = build_inspection(text, decision)

    assert inspection.available is False
    assert inspection.unavailable_reason == "blocked"
    assert inspection.segments == ()


# --- sanity: resolve_overlaps import is exercised, not just imported ----------


def test_resolve_overlaps_helper_used_by_this_module_still_behaves_as_expected():
    """Not a test of ``build_inspection`` -- pins that this test module's own
    understanding of ``resolve_overlaps``' tie-break rule (longest span wins)
    matches reality, so the overlap test above fails for the right reason if
    ``detection/overlap.py`` ever changes that rule.
    """
    short = _span("cpf", "AAAAA", 0)
    long = _span("employee_name", "AAAAAAAAA", 0)
    resolved = resolve_overlaps([short, long])
    assert len(resolved) == 1
    assert resolved[0].category == "employee_name"
