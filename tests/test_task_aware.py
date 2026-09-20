"""Pins T07/B3's behavioral acceptance criteria (issue #6): task-aware
action selection inside B3's generic, fixed action space
(``transformations.task_aware.TASK_AWARE_ACTION_SPACES``), applied through
the same shared vault/scope/reconstruction machinery B2 -- Reversible
Pseudonymization uses (``transformations.decision_application``), plus
independence from every B4 -- Policy-governed contextual dimension and the
fail-closed paths issue #6 requires.

Tasks are constructed inline throughout, never read from
``corpus/hr/v1``'s ``task_necessity`` oracle field -- CLAUDE.md and issue #6
forbid using ground truth as treatment input. See
``scripts/report_b3_corpus_divergence.py`` for this suite's replacement of
its former corpus-conformance test: a standalone report, not a pytest
invariant, that runs B3 over the frozen 13-case corpus and prints
per-case/per-category convergence against the oracle -- kept out of this
suite so the frozen corpus is never a de facto implementation target (see
the "Comparison against the frozen HR corpus's ground truth" section below
for why that test was removed).
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
    SensitiveSpan,
)
from adaptive_disclosure_gateway.policies import PolicyDocument, PolicyRepository
from adaptive_disclosure_gateway.task_analysis import TaskAnalysis, TaskRelevance
from adaptive_disclosure_gateway.transformations import ReversiblePseudonymizer, TaskAwareDiscloser
from adaptive_disclosure_gateway.vault import InMemoryVault

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

TEXT = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
        "request_id": "req-1",
        "document_id": "doc-1",
        "session_id": "sess-1",
    }
    values.update(overrides)
    return GovernanceContext(**values)


def _request(text: str, task: str, **context_overrides) -> DisclosureRequest:
    return DisclosureRequest(text=text, task=task, context=_context(**context_overrides))


def _discloser(task_analyzer=None) -> TaskAwareDiscloser:
    return TaskAwareDiscloser(
        vault=InMemoryVault(),
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        task_analyzer=task_analyzer,
    )


def _actions_by_category(result) -> dict[str, DisclosureAction]:
    return {decision.category: decision.action for decision in result.decisions}


class _StubAnalyzer:
    """A task analyzer that ignores its ``task`` argument entirely and
    reports a single fixed relevance for every category it is asked about --
    used to isolate B3's action-selection logic from the deterministic
    analyzer's own negation/indicator heuristics.
    """

    def __init__(self, relevance: TaskRelevance | dict[str, TaskRelevance]) -> None:
        self._relevance = relevance

    def analyze(self, task, categories):
        if isinstance(self._relevance, dict):
            mapping = {category: self._relevance[category] for category in categories}
        else:
            mapping = dict.fromkeys(categories, self._relevance)
        return TaskAnalysis(relevance_by_category=mapping)


class _RaisingAnalyzer:
    def analyze(self, task, categories):
        raise RuntimeError("boom: this message must never reach any result field")


class _UnknownLevelAnalyzer:
    """Returns something that is not a ``TaskRelevance`` member at all --
    simulating a misbehaving or future-incompatible analyzer implementation
    that bypasses ``TaskAnalysis``'s own pydantic validation (e.g. a hand
    rolled stand-in object, exactly like this one).
    """

    class _FakeAnalysis:
        def __init__(self, categories):
            self.relevance_by_category = dict.fromkeys(categories, "not_a_real_relevance_level")

    def analyze(self, task, categories):
        return self._FakeAnalysis(categories)


# --- Determinism ------------------------------------------------------------


def test_same_input_and_task_produce_the_same_decision_across_repeated_runs():
    task = "Confirm whether this employee's salary meets the minimum wage floor exactly."

    first = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    second = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(first) == _actions_by_category(second)


# --- The task changes the decision (B3's defining property) ----------------


def test_different_tasks_over_the_same_text_and_context_yield_different_decisions():
    # "exactly" is required here (PR #33 review round): a positive salary
    # mention with no explicit exact-value evidence now defaults to
    # RELEVANT_WITHOUT_EXACT_VALUE (GENERALIZE), not PRESERVE -- see
    # task_analysis/deterministic.py's EXACT_VALUE_INDICATORS. This task
    # genuinely wants the exact figure, so it says so explicitly. "company
    # policy" (not "department policy" -- PR #33 third review round): the
    # nearest-mention binding must not have a closer, unrelated category
    # sitting between "salary" and the cue.
    exact_salary_task = "Confirm whether this employee's salary matches company policy exactly."
    no_salary_task = "Write a one-sentence summary of this employee's role. Salary is not needed."

    with_salary = _discloser().sanitize(_request(TEXT, exact_salary_task), Detector().detect(TEXT))
    without_salary = _discloser().sanitize(_request(TEXT, no_salary_task), Detector().detect(TEXT))

    assert (
        _actions_by_category(with_salary)["salary"]
        != _actions_by_category(without_salary)["salary"]
    )
    assert _actions_by_category(with_salary)["salary"] is DisclosureAction.PRESERVE
    assert _actions_by_category(without_salary)["salary"] is DisclosureAction.REMOVE


# --- Independence from every B4 contextual dimension ------------------------
#
# The structural guarantee is task_analysis.base.TaskAnalyzer.analyze's
# signature (pinned in tests/test_task_analysis_signature_isolation.py):
# the analyzer physically cannot receive any of these dimensions. The tests
# below are the end-to-end confirmation, not the only defense -- each varies
# exactly one dimension while text and task stay fixed and asserts the
# resulting per-category action is unchanged. request_id/document_id/
# session_id are all supplied on every context so that whichever pseudonym
# scope a dimension change happens to resolve to always has the identifier
# it needs -- otherwise a scope-resolution failure (a *disclosure-control*
# outcome, not a task-awareness one) would masquerade as a decision change.

_TASK_FOR_DIMENSION_TESTS = (
    "Confirm whether this employee's salary matches company policy exactly. "
    "The employee's name and CPF are not required for this review."
)


def test_varying_purpose_does_not_change_the_decision():
    base = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, purpose="team_summary"),
        Detector().detect(TEXT),
    )
    varied = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, purpose="compensation_review"),
        Detector().detect(TEXT),
    )
    assert _actions_by_category(base) == _actions_by_category(varied)


def test_varying_requester_role_does_not_change_the_decision():
    base = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, requester_role="hr_analyst"),
        Detector().detect(TEXT),
    )
    varied = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, requester_role="hr_admin"),
        Detector().detect(TEXT),
    )
    assert _actions_by_category(base) == _actions_by_category(varied)


def test_varying_requester_id_does_not_change_the_decision():
    base = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, requester_id="u1"),
        Detector().detect(TEXT),
    )
    varied = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, requester_id="u2"),
        Detector().detect(TEXT),
    )
    assert _actions_by_category(base) == _actions_by_category(varied)


def test_varying_provider_class_does_not_change_the_decision():
    base = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, provider_class="external_llm"),
        Detector().detect(TEXT),
    )
    varied = _discloser().sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, provider_class="internal_llm"),
        Detector().detect(TEXT),
    )
    assert _actions_by_category(base) == _actions_by_category(varied)


def test_varying_domain_and_policy_version_together_does_not_change_the_decision():
    # domain and policy_version are the two dimensions whose *resolvability*
    # (not their effect on the decision) are coupled in this architecture --
    # PolicyRepository.resolve_pseudonym_scope blocks outright when a
    # context's domain does not match its policy_version's own domain (see
    # policies.py). To vary domain without that unrelated failure
    # contaminating this test, a second, self-consistent (domain,
    # policy_version) pair is loaded into its own in-memory
    # PolicyRepository -- configs/policies/hr-v1.yaml itself is untouched.
    # ``rules`` is intentionally empty: task_aware.py never calls
    # PolicyRepository.decide(), so no rule is ever read.
    second_repository = PolicyRepository(
        policies={
            "finance-v1": PolicyDocument(version="finance-v1", domain="finance", rules={}),
        }
    )

    hr_result = TaskAwareDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    ).sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, domain="hr", policy_version="hr-v1"),
        Detector().detect(TEXT),
    )
    finance_result = TaskAwareDiscloser(
        vault=InMemoryVault(), policy_repository=second_repository
    ).sanitize(
        _request(TEXT, _TASK_FOR_DIMENSION_TESTS, domain="finance", policy_version="finance-v1"),
        Detector().detect(TEXT),
    )

    assert _actions_by_category(hr_result) == _actions_by_category(finance_result)


# --- Minimal exposure for a category the task explicitly does not need -----


def test_task_explicitly_not_needing_a_category_selects_its_least_disclosing_action():
    task = (
        "Confirm whether this employee's salary meets the minimum wage floor, "
        "without disclosing their identity or department."
    )
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    actions = _actions_by_category(result)

    assert actions["employee_name"] is DisclosureAction.REMOVE
    assert actions["department"] is DisclosureAction.REMOVE
    assert "Ana Souza" not in result.external_payload
    assert "Engineering" not in result.external_payload


# --- Necessary information: exact value vs. reduced form -------------------


def test_task_needing_the_exact_numeric_value_selects_preserve():
    task = "Confirm whether this employee's salary matches company policy exactly."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.PRESERVE
    assert "8500" in result.external_payload


def test_task_needing_only_a_reduced_form_selects_generalize():
    task = "Provide an aggregate salary range for the department from these records."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload
    assert "R$ 5000-10000" in result.external_payload


def test_task_needing_identity_without_the_exact_original_selects_pseudonymize():
    task = "Draft an announcement addressed by name to this employee, confirming their department."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["employee_name"] is DisclosureAction.PSEUDONYMIZE
    assert "Ana Souza" not in result.external_payload


# --- B2's reconstruction mechanism is retained unchanged --------------------


def test_b3_round_trip_reconstruction_recovers_the_original_value():
    task = "Draft an announcement addressed by name to this employee."
    discloser = _discloser()
    request = _request(TEXT, task)
    result = discloser.sanitize(request, Detector().detect(TEXT))
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")

    response_text = f"Hello {pseudonym}, welcome to the team."
    reconstructed = discloser.reconstruct(response_text, result, request.context)

    assert reconstructed == "Hello Ana Souza, welcome to the team."
    assert pseudonym not in reconstructed


def test_b3_request_scope_ceiling_limits_cross_request_linkability_like_b2():
    # Mirrors test_reversible_pseudonymization.py's hr_viewer-ceiling test:
    # hr_viewer is capped at REQUEST scope by configs/policies/hr-v1.yaml,
    # so two different requests sharing a session must not share a
    # pseudonym -- proving B3 inherited this behavior rather than
    # reimplementing (and potentially weakening) it.
    text = "Employee: Ana Souza\n"
    task = "Draft an announcement addressed by name to this employee."
    discloser = _discloser()

    first = discloser.sanitize(
        _request(
            text,
            task,
            requester_role="hr_viewer",
            request_id="req-1",
            session_id="sess-shared",
        ),
        Detector().detect(text),
    )
    second = discloser.sanitize(
        _request(
            text,
            task,
            requester_role="hr_viewer",
            request_id="req-2",
            session_id="sess-shared",
        ),
        Detector().detect(text),
    )

    first_pseudonym = next(
        t.transformed for t in first.transformations if t.category == "employee_name"
    )
    second_pseudonym = next(
        t.transformed for t in second.transformations if t.category == "employee_name"
    )
    assert first_pseudonym != second_pseudonym


# --- Fail-closed paths: none of these may ever resolve to PRESERVE ---------


def test_category_outside_the_generic_action_space_blocks_the_request():
    request = _request("some free text value here", "summarize this")
    spans = [SensitiveSpan(category="unknown_category", value="value here", start=15, end=25)]

    result = _discloser().sanitize(request, spans)

    assert result.status == "blocked"
    assert "value here" not in result.external_payload
    assert all(d.action is not DisclosureAction.PRESERVE for d in result.decisions)


def test_analyzer_raising_blocks_the_whole_request_without_leaking_its_message():
    result = _discloser(task_analyzer=_RaisingAnalyzer()).sanitize(
        _request(TEXT, "Confirm the salary."), Detector().detect(TEXT)
    )

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert all(d.action is DisclosureAction.BLOCK_REQUEST for d in result.decisions)
    dumped = "".join(d.reason for d in result.decisions)
    assert "boom" not in dumped
    assert "Ana Souza" not in dumped


def test_analyzer_returning_an_unrecognized_relevance_level_blocks_the_whole_request():
    result = _discloser(task_analyzer=_UnknownLevelAnalyzer()).sanitize(
        _request(TEXT, "Confirm the salary."), Detector().detect(TEXT)
    )

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert all(d.action is DisclosureAction.BLOCK_REQUEST for d in result.decisions)


def test_ambiguous_relevance_resolves_to_the_least_disclosing_action_never_preserve():
    analyzer = _StubAnalyzer(
        {
            "employee_name": TaskRelevance.AMBIGUOUS,
            "cpf": TaskRelevance.NOT_RELEVANT,
            "salary": TaskRelevance.AMBIGUOUS,
            "department": TaskRelevance.AMBIGUOUS,
        }
    )
    result = _discloser(task_analyzer=analyzer).sanitize(
        _request(TEXT, "State the employee's name. Do not state the employee's name."),
        Detector().detect(TEXT),
    )
    actions = _actions_by_category(result)

    assert actions["employee_name"] is DisclosureAction.REMOVE
    assert actions["salary"] is DisclosureAction.REMOVE
    assert actions["department"] is DisclosureAction.REMOVE
    assert all(action is not DisclosureAction.PRESERVE for action in actions.values())
    # The ambiguity is recorded explicitly in the audit trail, not silently
    # folded into an ordinary "not relevant" decision.
    ambiguous_reasons = [d.reason for d in result.decisions if d.category == "employee_name"]
    assert any("ambiguous" in reason.lower() for reason in ambiguous_reasons)


def test_pay_as_a_common_verb_never_escalates_salary_to_preserve():
    # Negative control (PR #33 review round): a false-positive lexical match
    # is a disclosure-control defect, not a quality one -- unlike a false
    # negative (which only costs utility by falling back to the category's
    # least-disclosing action), a false positive can escalate an unrelated
    # task's resolved action all the way to PRESERVE. Asserted here at the
    # *action* level -- not just the analyzer's relevance label in
    # tests/test_task_analysis_deterministic.py -- because the action is
    # what actually determines exposure in the external payload.
    result = _discloser().sanitize(
        _request(TEXT, "Pay attention to the department summary."), Detector().detect(TEXT)
    )
    assert _actions_by_category(result)["salary"] is DisclosureAction.REMOVE


def test_pay_the_invoice_never_escalates_salary_to_preserve():
    result = _discloser().sanitize(
        _request(TEXT, "Pay the invoice and summarize the department."), Detector().detect(TEXT)
    )
    assert _actions_by_category(result)["salary"] is DisclosureAction.REMOVE


def test_pay_heed_never_escalates_salary_to_preserve():
    task = "Summarize the department. Take care to pay heed to formatting."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    assert _actions_by_category(result)["salary"] is DisclosureAction.REMOVE


def test_department_name_does_not_escalate_employee_name_disclosure():
    result = _discloser().sanitize(
        _request(TEXT, "What is the department name?"), Detector().detect(TEXT)
    )
    assert _actions_by_category(result)["employee_name"] is DisclosureAction.REMOVE


def test_naming_convention_does_not_escalate_employee_name_disclosure():
    result = _discloser().sanitize(
        _request(TEXT, "Follow the naming convention for the division."), Detector().detect(TEXT)
    )
    assert _actions_by_category(result)["employee_name"] is DisclosureAction.REMOVE


def test_team_player_idiom_does_not_escalate_department_disclosure():
    # Found while auditing the indicator tables for the same class of
    # defect as "pay"/"name": "team" as a bare indicator matches idioms
    # unrelated to an org unit and would otherwise PRESERVE the department
    # for a task that never asked for it.
    task = "Write a one-sentence summary praising this employee as a great team player."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    assert _actions_by_category(result)["department"] is DisclosureAction.REMOVE


def test_long_division_does_not_escalate_department_disclosure():
    task = "Perform long division to check the total on this record."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    assert _actions_by_category(result)["department"] is DisclosureAction.REMOVE


# --- Positive controls: hardened indicators still recognize genuine need ---


def test_pay_band_positive_control_still_selects_preserve_for_salary():
    # The cue sits right after "pay band" (PR #33 third review round): the
    # previous phrasing put "exactly" at the very end of the sentence, many
    # tokens past "pay band", which the nearest-mention binding's window no
    # longer reaches -- this is the same genuine-need positive control, not
    # a weaker one, just phrased so the cue is close enough to the category
    # it is actually meant to modify.
    task = "Confirm this employee's pay band precisely for their current role."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    assert _actions_by_category(result)["salary"] is DisclosureAction.PRESERVE


def test_full_name_positive_control_still_selects_pseudonymize():
    task = "What is the employee's full name for this record?"
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    assert _actions_by_category(result)["employee_name"] is DisclosureAction.PSEUDONYMIZE


def test_employees_team_positive_control_still_selects_preserve_for_department():
    task = "Provide a one-sentence description of this employee's team for an internal directory entry."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    assert _actions_by_category(result)["department"] is DisclosureAction.PRESERVE


# --- Negative control: an exactness cue bound to one category must not
# escalate a *different* category's resolved action (PR #33 second review
# round). Asserted here at the action level -- not just the analyzer's
# relevance label -- because the action is what determines real exposure in
# the external payload: the historical defect drove salary all the way to
# PRESERVE for tasks that never asked for salary's exact value at all.


def test_exact_employee_name_cue_never_escalates_salary_to_preserve():
    task = "Use the exact employee name in the greeting. Summarize the salary band."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


def test_department_exactly_cue_never_escalates_salary_to_preserve():
    task = "Return the department exactly. Provide the salary range."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


def test_exact_cpf_cue_never_escalates_salary_to_preserve():
    task = "Report the exact CPF. Summarize the salary."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


# --- Negative control: the same defect, same-clause (PR #33 third review
# round). The previous fix only scoped the simple cue to one *sentence*; a
# trivial rewording that keeps the unrelated category in the *same* clause
# (joined by "and", by a comma, or by "then", instead of split across
# sentences) reproduced the identical leak all the way to PRESERVE. Asserted
# at the action level, like the cross-sentence negative controls above,
# because the action -- not the relevance label -- is what the external
# payload actually exposes.


def test_exact_employee_name_cue_never_escalates_salary_to_preserve_joined_by_and():
    task = "Use the exact employee name and summarize the salary band."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


def test_department_exactly_cue_never_escalates_salary_to_preserve_joined_by_and():
    task = "Return the department exactly and provide the salary range."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


def test_exact_cpf_cue_never_escalates_salary_to_preserve_joined_by_and():
    task = "Report the exact CPF and summarize the salary."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


def test_exact_employee_name_cue_never_escalates_salary_to_preserve_joined_by_comma_then():
    task = "Use the exact employee name, then summarize the salary band."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


# --- Ambiguity: a cue exactly equidistant between two co-mentioned
# categories in the same clause must escalate neither -- the simple-cue
# path's own tie-break, mirroring the wrapper tie-break below. Asserted only
# on "salary": "department"'s action space is binary (REMOVE/PRESERVE), so
# RELEVANT_WITH_EXACT_VALUE and RELEVANT_WITHOUT_EXACT_VALUE already resolve
# to the same PRESERVE action for it regardless of this tie -- "salary" is
# the category whose 3-tier space (REMOVE/GENERALIZE/PRESERVE) actually
# exposes whether the tie-break holds.


def test_cue_equidistant_between_two_categories_never_escalates_salary_to_preserve():
    task = "State the salary or precisely the department for this record."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.GENERALIZE
    assert "8500.00" not in result.external_payload


# --- Positive controls: the binding fix must still recognize genuine
# same-clause exactness evidence for salary, including non-adjacent and
# wrapper forms. --------------------------------------------------------


def test_salary_value_precisely_still_selects_preserve_for_salary():
    task = "State the salary value precisely."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.PRESERVE
    assert "8500" in result.external_payload


def test_specific_salary_figure_still_selects_preserve_for_salary():
    task = "Report the specific salary figure for this employee."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))

    assert _actions_by_category(result)["salary"] is DisclosureAction.PRESERVE
    assert "8500" in result.external_payload


# --- Ambiguity: a wrapper cue enclosing two categories in the same clause
# must escalate neither to preserve. -------------------------------------


def test_wrapper_cue_enclosing_salary_and_cpf_never_escalates_either_to_preserve():
    task = "Report the specific salary and CPF figure for this employee."
    result = _discloser().sanitize(_request(TEXT, task), Detector().detect(TEXT))
    actions = _actions_by_category(result)

    assert actions["salary"] is DisclosureAction.GENERALIZE
    assert actions["cpf"] is DisclosureAction.PSEUDONYMIZE
    assert "8500.00" not in result.external_payload
    assert "123.456.789-09" not in result.external_payload


def test_medical_data_still_blocks_unconditionally_regardless_of_relevance():
    for relevance in TaskRelevance:
        text = TEXT + "Medical notes: Reports chronic migraine and requested leave.\n"
        analyzer = _StubAnalyzer(relevance)
        result = _discloser(task_analyzer=analyzer).sanitize(
            _request(text, "Summarize this employee's medical leave."), Detector().detect(text)
        )
        assert result.status == "blocked", f"expected block for relevance={relevance}"


# --- B2 -> B3 isolation: forcing every category's least-disclosing-but-
# usable action reproduces B2's own static mapping exactly, demonstrating
# that the vault mechanism, scopes, reconstruction and audit shape are
# unchanged -- only *how* the action is chosen differs. -----------------
#
# RELEVANT_WITHOUT_EXACT_VALUE is the level chosen (rather than
# RELEVANT_WITH_EXACT_VALUE) because it is the one that reproduces B2's
# GENERALIZE choice for salary: "with exact value" would select PRESERVE for
# salary instead, which is a genuinely different (and correct, task-aware)
# decision, not a B2 equivalent.


def test_b2_and_b3_produce_identical_payloads_and_reconstruction_when_b3_mirrors_b2s_choices():
    shared_vault = InMemoryVault()
    policy_repository = PolicyRepository.from_directory(POLICY_DIR)
    request = _request(TEXT, "irrelevant task text -- the stub analyzer ignores it")
    spans = Detector().detect(TEXT)

    b2 = ReversiblePseudonymizer(vault=shared_vault, policy_repository=policy_repository)
    b3 = TaskAwareDiscloser(
        vault=shared_vault,
        policy_repository=policy_repository,
        task_analyzer=_StubAnalyzer(TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE),
    )

    b2_result = b2.sanitize(request, spans)
    b3_result = b3.sanitize(request, spans)

    assert b2_result.status == b3_result.status == "allowed"
    assert b2_result.external_payload == b3_result.external_payload
    assert b2_result.reconstruction_required == b3_result.reconstruction_required
    assert [(t.category, t.action, t.transformed) for t in b2_result.transformations] == [
        (t.category, t.action, t.transformed) for t in b3_result.transformations
    ]

    b2_response = "Please schedule a review with {} next week.".format(
        next(t.transformed for t in b2_result.transformations if t.category == "employee_name")
    )
    b3_response = "Please schedule a review with {} next week.".format(
        next(t.transformed for t in b3_result.transformations if t.category == "employee_name")
    )
    assert b2.reconstruct(b2_response, b2_result, request.context) == b3.reconstruct(
        b3_response, b3_result, request.context
    )


# --- Comparison against the frozen HR corpus's ground truth -----------------
#
# There used to be a suite-level invariant here asserting every one of the
# 13 frozen HR corpus cases' B3 decisions fell inside that case's
# oracle-acceptable action set. Removed deliberately (PR #33 review round,
# alongside the exact-value default flip above): once a positive category
# mention defaults to RELEVANT_WITHOUT_EXACT_VALUE unless the task carries
# narrow, explicit exact-value evidence, treating 100% conformance against
# this specific frozen corpus as a pass/fail suite gate turns the corpus
# into an implementation target -- exactly what CLAUDE.md's corpus-freeze
# rule and issue #6 forbid. The corpus is this experiment's *evaluation*
# oracle (scored in T10), not a specification B3 must reproduce exactly.
#
# ``scripts/report_b3_corpus_divergence.py`` replaces this: a standalone,
# non-pytest report that runs B3 over the 13 cases and prints per-case,
# per-category convergence/divergence against the oracle, for development
# visibility now and reuse in T10 -- it is not part of this suite because a
# script that only reports, and cannot fail a build, is not a test.
#
# tests/test_corpus_oracle_isolation.py still pins that no production code
# (including this analyzer) has any import path to ``case.oracle`` at all;
# that guarantee is unaffected by this removal.
