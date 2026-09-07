"""Task-necessity / answer-dependency coherence for the frozen HR pilot
corpus (T09 / issue #4, Phase A -- PR #31 review round 2).

Before this test existed, nothing checked that a span annotated
``task_necessity: required`` was actually a category the case's
``expected_answer`` depends on. That gap is exactly how
``hr_team_summary_001/002/003`` shipped with ``employee_name`` marked
``required`` even though each of those cases' task and ``expected_answer``
only ever ask for/name the employee's department -- identity was never
needed to satisfy the task.

``CaseOracle.answer_depends_on_categories`` (``src/adaptive_disclosure_gateway/
corpus/oracle.py``) makes the dependency an explicit, schema-validated
annotation. This test makes the *coherence* between that annotation and the
per-span ``task_necessity`` labels a structural invariant: for every
non-blocked case, the set of categories with at least one ``required`` span
must equal ``answer_depends_on_categories`` exactly. A blocked case never
produces an answer, so it must carry no such list at all.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.corpus import TaskNecessity, load_corpus

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"


def test_required_categories_match_answer_depends_on_categories_for_every_non_blocked_case():
    cases = load_corpus(REAL_CORPUS_DIR)
    non_blocked = [case for case in cases if not case.oracle.expected_block_request]
    assert non_blocked, "expected at least one non-blocked corpus case to check"

    mismatches = []
    for case in non_blocked:
        required_categories = {
            span.category
            for span in case.oracle.expected_spans
            if span.task_necessity is TaskNecessity.REQUIRED
        }
        declared_categories = set(case.oracle.answer_depends_on_categories or [])
        if required_categories != declared_categories:
            mismatches.append(
                f"{case.input.sample_id}: required_categories="
                f"{sorted(required_categories)} answer_depends_on_categories="
                f"{sorted(declared_categories)}"
            )

    assert not mismatches, (
        "task_necessity=required spans do not match answer_depends_on_categories "
        f"(a span cannot be required unless the expected_answer depends on it): {mismatches}"
    )


def test_blocked_cases_never_declare_answer_depends_on_categories():
    cases = load_corpus(REAL_CORPUS_DIR)
    blocked = [case for case in cases if case.oracle.expected_block_request]
    assert blocked, "expected at least one blocked corpus case to check"

    for case in blocked:
        assert case.oracle.answer_depends_on_categories is None, (
            f"{case.input.sample_id} expects BLOCK_REQUEST but still declares "
            "answer_depends_on_categories -- a blocked case never produces an "
            "answer for anything to depend on"
        )
