"""Pins ``DeterministicTaskAnalyzer``'s behavior in isolation from the rest
of B3 (T07 / issue #6): determinism, the three explicit relevance levels,
and -- most importantly -- the negation forms the pilot's task profiles
actually use. A naive keyword matcher would see "salary" in "Salary and CPF
are not needed" and mark it relevant; these tests pin the opposite, correct
reading.

Tasks are constructed inline here, never read from ``corpus/hr/v1`` --
CLAUDE.md and issue #6 forbid coupling this analyzer to corpus content, and
these tests double as proof that no such coupling crept in (they would pass
even if the corpus directory did not exist).
"""

from __future__ import annotations

from adaptive_disclosure_gateway.task_analysis import DeterministicTaskAnalyzer, TaskRelevance

CATEGORIES = ("employee_name", "cpf", "salary", "department", "medical_data")


def _relevance(task: str, categories=CATEGORIES) -> dict[str, TaskRelevance]:
    return DeterministicTaskAnalyzer().analyze(task, categories).relevance_by_category


def test_same_task_and_categories_always_produce_the_same_relevance():
    task = "Determine whether the salary falls within the department's compensation band."
    first = _relevance(task)
    second = _relevance(task)
    third = DeterministicTaskAnalyzer().analyze(task, CATEGORIES).relevance_by_category

    assert first == second == third


# --- Negation forms named explicitly in issue #6's task ------------------


def test_not_needed_suffix_negation_marks_the_named_categories_not_relevant():
    task = "Write a role summary. Salary and CPF are not needed for this summary."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.NOT_RELEVANT
    assert relevance["cpf"] is TaskRelevance.NOT_RELEVANT


def test_do_not_include_prefix_negation_marks_the_named_categories_not_relevant():
    task = "Draft a directory note about this employee. Do not include salary or CPF."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.NOT_RELEVANT
    assert relevance["cpf"] is TaskRelevance.NOT_RELEVANT


def test_must_not_be_included_negation_marks_the_named_categories_not_relevant():
    task = "Provide a one-sentence team description. Salary and CPF must not be included."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.NOT_RELEVANT
    assert relevance["cpf"] is TaskRelevance.NOT_RELEVANT


def test_without_disclosing_negation_only_negates_its_own_clause():
    # The clause preceding "without" states the real instruction and must
    # stay positive; only "identity" (and, in this phrasing, "department")
    # inside the "without" clause is negated. A naive whole-sentence
    # negation rule would incorrectly wipe out "salary" here too.
    task = (
        "Estimate the average salary band for the department based on these "
        "records, without disclosing their identity."
    )
    relevance = _relevance(task)

    assert relevance["employee_name"] is TaskRelevance.NOT_RELEVANT
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


def test_without_clause_does_not_negate_text_preceding_it_in_the_same_sentence():
    task = (
        "Confirm whether this employee's salary meets the minimum wage floor, "
        "without disclosing their identity or department."
    )
    relevance = _relevance(task)

    # Positive mention of "salary" with no explicit exact-value evidence
    # (PR #33 review round: absence of signal never escalates to
    # RELEVANT_WITH_EXACT_VALUE) -- what this test actually pins is that
    # "without" does not retroactively negate "salary", which the
    # RELEVANT_WITHOUT_EXACT_VALUE (as opposed to NOT_RELEVANT) outcome
    # below still demonstrates.
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE
    assert relevance["employee_name"] is TaskRelevance.NOT_RELEVANT
    assert relevance["department"] is TaskRelevance.NOT_RELEVANT


# --- Three explicit relevance levels ---------------------------------------


def test_task_never_mentioning_a_category_is_not_relevant():
    task = "Write a one-sentence summary of this employee's role."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.NOT_RELEVANT
    assert relevance["medical_data"] is TaskRelevance.NOT_RELEVANT


def test_aggregate_wording_marks_a_numeric_category_relevant_without_exact_value():
    task = "Provide an aggregate salary range for the department from these records."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


def test_comparison_wording_marks_a_numeric_category_relevant_with_exact_value():
    # "company policy" (not "department policy"): the exactness cue must
    # bind to "salary" alone. An earlier version of this task said "Finance
    # department policy" instead, which happened to also plant "department"
    # a single token away from the cue -- closer to it than "salary" is.
    # See this module's docstring and deterministic.py's module docstring
    # for why that phrasing is no longer used: the third review round's
    # nearest-mention binding would otherwise bind the cue to the *nearer*,
    # unrelated "department" instead of "salary", which is the same
    # least-disclosure-preferred outcome this whole round exists to enforce
    # -- not a defect, but it means this task can no longer double as
    # positive-control text for salary specifically.
    task = "Confirm whether this employee's salary matches company policy exactly."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE


def test_conflicting_mentions_resolve_to_ambiguous_rather_than_guessing():
    task = "State the employee's name in the summary. Do not disclose the employee's name."
    relevance = _relevance(task)

    assert relevance["employee_name"] is TaskRelevance.AMBIGUOUS


def test_category_with_no_controlled_indicator_profile_defaults_to_not_relevant():
    relevance = _relevance("Summarize this record.", categories=("some_future_category",))

    assert relevance["some_future_category"] is TaskRelevance.NOT_RELEVANT


# --- Negative control: an indicator term with a common non-category meaning
# must not falsely mark the category relevant (PR #33 review round) --------
#
# A false NEGATIVE here only costs utility: the task-aware treatment falls
# back to the category's least-disclosing action, exactly as it would for
# any other NOT_RELEVANT category. A false POSITIVE is strictly worse: it
# can drive the resolved action all the way up to PRESERVE for a task that
# never asked for that category at all, actively *increasing* disclosure
# beyond what the task required. So whenever an indicator term's own English
# meaning is genuinely ambiguous (it has a common sense unrelated to the
# category), the safe reading is NOT_RELEVANT rather than a guessed
# RELEVANT_* level -- this is not a silent fallback to PRESERVE, it is the
# same explicit "least disclosing action in the category's action space"
# behavior NOT_RELEVANT already produces. See
# tests/test_task_aware.py's mirrored negative controls, which assert the
# actual *action* TaskAwareDiscloser produces from these same tasks, since
# the action -- not the relevance label alone -- is what determines real
# exposure in the external payload.


def test_pay_as_a_common_verb_does_not_falsely_mark_salary_relevant():
    relevance = _relevance("Pay attention to the department summary.")
    assert relevance["salary"] is TaskRelevance.NOT_RELEVANT


def test_pay_the_invoice_does_not_falsely_mark_salary_relevant():
    relevance = _relevance("Pay the invoice and summarize the department.")
    assert relevance["salary"] is TaskRelevance.NOT_RELEVANT


def test_pay_heed_does_not_falsely_mark_salary_relevant():
    task = "Summarize the department. Take care to pay heed to formatting."
    relevance = _relevance(task)
    assert relevance["salary"] is TaskRelevance.NOT_RELEVANT


def test_department_name_does_not_falsely_mark_employee_name_relevant():
    relevance = _relevance("What is the department name?")
    assert relevance["employee_name"] is TaskRelevance.NOT_RELEVANT


def test_naming_convention_does_not_falsely_mark_employee_name_relevant():
    relevance = _relevance("Follow the naming convention for the division.")
    assert relevance["employee_name"] is TaskRelevance.NOT_RELEVANT


def test_team_player_idiom_does_not_falsely_mark_department_relevant():
    # Found while auditing the indicator tables for the same class of
    # defect: "team" as a bare indicator matches common idioms that have
    # nothing to do with an org unit.
    relevance = _relevance(
        "Write a one-sentence summary praising this employee as a great team player."
    )
    assert relevance["department"] is TaskRelevance.NOT_RELEVANT


def test_work_as_a_team_idiom_does_not_falsely_mark_department_relevant():
    relevance = _relevance("Work as a team to summarize this report.")
    assert relevance["department"] is TaskRelevance.NOT_RELEVANT


def test_long_division_does_not_falsely_mark_department_relevant():
    relevance = _relevance("Perform long division to check the total on this record.")
    assert relevance["department"] is TaskRelevance.NOT_RELEVANT


# --- Positive controls: hardening the tables above must not blind the
# analyzer to genuine requests for the category -- otherwise "fixing" the
# false positive would just trade it for a false negative. ------------------


def test_pay_band_positive_control_still_marks_salary_relevant():
    relevance = _relevance("Confirm this employee's pay band for their current role.")
    assert relevance["salary"] is not TaskRelevance.NOT_RELEVANT


def test_payroll_positive_control_still_marks_salary_relevant():
    relevance = _relevance("Review the payroll figures for this department.")
    assert relevance["salary"] is not TaskRelevance.NOT_RELEVANT


def test_by_name_positive_control_still_marks_employee_name_relevant():
    relevance = _relevance("Draft an announcement addressed by name to this employee.")
    assert relevance["employee_name"] is not TaskRelevance.NOT_RELEVANT


def test_full_name_positive_control_still_marks_employee_name_relevant():
    relevance = _relevance("What is the employee's full name?")
    assert relevance["employee_name"] is not TaskRelevance.NOT_RELEVANT


def test_employees_team_positive_control_still_marks_department_relevant():
    task = "Provide a one-sentence description of this employee's team for an internal directory entry."
    relevance = _relevance(task)
    assert relevance["department"] is not TaskRelevance.NOT_RELEVANT


# --- Negative control: an exactness cue belonging to one category must not
# escalate a *different* category's relevance (PR #33 second review round).
#
# The historical defect: ``found_exact`` searched EXACT_VALUE_INDICATORS
# terms across the *entire* positive text, so a cue that plainly modifies
# one category's mention (e.g. "the exact CPF") also escalated any other,
# unrelated category mentioned anywhere else in the task (e.g. "salary" in
# the next sentence) to RELEVANT_WITH_EXACT_VALUE -- silently increasing
# disclosure for a category the task never asked to have exactly. Evidence
# that increases disclosure must be bound to the category it actually
# modifies (CLAUDE.md's no-leak invariant read together with this
# analyzer's own default-to-least-revealing rule).


def test_exact_cue_for_employee_name_does_not_escalate_salary_in_a_later_sentence():
    task = "Use the exact employee name in the greeting. Summarize the salary band."
    relevance = _relevance(task)

    assert relevance["employee_name"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


def test_exactly_cue_for_department_does_not_escalate_salary_in_a_later_sentence():
    task = "Return the department exactly. Provide the salary range."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


def test_exact_cue_for_cpf_does_not_escalate_salary_in_a_later_sentence():
    task = "Report the exact CPF. Summarize the salary."
    relevance = _relevance(task)

    assert relevance["cpf"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


# --- Positive control: the binding fix above must not blind the analyzer to
# genuine same-clause exactness evidence for salary, including forms where
# the cue and the category term are not perfectly adjacent. -----------------


def test_exact_salary_binds_within_the_same_clause():
    relevance = _relevance("Return the exact salary.")
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE


def test_salary_exactly_binds_within_the_same_clause():
    relevance = _relevance("Report the salary exactly.")
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE


def test_precise_salary_binds_within_the_same_clause():
    relevance = _relevance("Provide the precise salary for this record.")
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE


def test_salary_value_precisely_binds_with_one_word_between_cue_and_category():
    relevance = _relevance("State the salary value precisely.")
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE


def test_specific_salary_figure_binds_when_the_category_term_sits_inside_the_wrapper():
    # "specific" ... "figure" wraps around "salary" itself -- the indicator
    # term sits *inside* the exactness expression rather than next to a
    # single contiguous cue phrase. See deterministic.py's
    # ``_wrapper_bound_categories``.
    relevance = _relevance("Report the specific salary figure for this employee.")
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE


# --- Ambiguity: a wrapper cue enclosing more than one category's mention in
# the same clause must not escalate either of them (mandatory per the
# review round: prefer least disclosure whenever binding is unsafe). -------


def test_wrapper_cue_enclosing_two_categories_escalates_neither():
    # "specific ... figure" wraps *both* "salary" and "CPF" here -- there is
    # only one "figure" being asked for, and no deterministic way to tell
    # which of the two co-mentioned categories it refers to. The safe
    # reading is RELEVANT_WITHOUT_EXACT_VALUE for both, never a guess.
    task = "Report the specific salary and CPF figure for this employee."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE
    assert relevance["cpf"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


# --- Negative control: a same-clause exactness cue belonging to one category
# must not escalate a *different* category also mentioned in that same
# clause (PR #33 third review round). The prior fix only scoped the simple
# cue to one *sentence*; within that sentence it still bound the cue to
# EVERY positively mentioned category, so trivial rewordings that keep two
# categories in one clause -- joined by "and", by a comma, or by "then",
# rather than split across sentences -- reproduce the exact same leak the
# second review round was supposed to have closed. These are same-clause
# siblings of the cross-sentence tests above; the cue and its true target
# are adjacent (distance 0), while the unrelated category sits many tokens
# away, well outside ``_EXACT_VALUE_WINDOW`` -- see
# ``_nearest_bound_categories`` in deterministic.py.


def test_exact_employee_name_cue_does_not_escalate_salary_joined_by_and():
    task = "Use the exact employee name and summarize the salary band."
    relevance = _relevance(task)

    assert relevance["employee_name"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


def test_department_exactly_cue_does_not_escalate_salary_joined_by_and():
    task = "Return the department exactly and provide the salary range."
    relevance = _relevance(task)

    assert relevance["department"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


def test_exact_cpf_cue_does_not_escalate_salary_joined_by_and():
    task = "Report the exact CPF and summarize the salary."
    relevance = _relevance(task)

    assert relevance["cpf"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


def test_exact_employee_name_cue_does_not_escalate_salary_joined_by_comma_then():
    task = "Use the exact employee name, then summarize the salary band."
    relevance = _relevance(task)

    assert relevance["employee_name"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE


# --- Ambiguity: a cue exactly equidistant (in tokens) between two co-mentioned
# categories in the same clause must escalate neither -- the mirror of the
# wrapper tie-break above, for the simple-cue path's own nearest-mention
# binding. "salary" sits one token before the cue ("or precisely"); "the
# department" sits one token after it ("precisely the") -- a genuine tie,
# not resolvable without guessing which the cue actually modifies.


def test_cue_equidistant_between_two_categories_escalates_neither():
    task = "State the salary or precisely the department for this record."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE
    assert relevance["department"] is TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE
