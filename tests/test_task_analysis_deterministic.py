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

    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE
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
    task = "Confirm whether this employee's salary matches Finance department policy exactly."
    relevance = _relevance(task)

    assert relevance["salary"] is TaskRelevance.RELEVANT_WITH_EXACT_VALUE


def test_conflicting_mentions_resolve_to_ambiguous_rather_than_guessing():
    task = "State the employee's name in the summary. Do not disclose the employee's name."
    relevance = _relevance(task)

    assert relevance["employee_name"] is TaskRelevance.AMBIGUOUS


def test_category_with_no_controlled_indicator_profile_defaults_to_not_relevant():
    relevance = _relevance("Summarize this record.", categories=("some_future_category",))

    assert relevance["some_future_category"] is TaskRelevance.NOT_RELEVANT
