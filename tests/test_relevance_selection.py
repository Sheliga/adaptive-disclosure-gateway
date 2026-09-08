"""Pins the shared task-relevance -> action selection rule extracted from
B3 -- Task-aware's own, formerly-private ``_select_action`` (T08 / issue #7
review round).

Before this extraction, ``transformations/task_aware.py`` had its own
module-private ``_select_action(level, action_space)`` -- the exact rule
that picks the least-disclosing action inside an already-ordered candidate
space that still satisfies a given ``TaskRelevance``. B4 -- Policy-governed
needs the identical rule to minimize inside whatever action space
``PolicyRepository.decide()`` resolves, so this suite pins the extracted,
now-shared function (``transformations.relevance_selection.
select_action_for_relevance``) directly, covering exactly the branches B3's
own behavioral suite (``tests/test_task_aware.py``) already exercises
end-to-end through a full ``TaskAwareDiscloser.sanitize()`` call. Testing
the pure function directly here, in addition to that existing suite passing
unchanged after the extraction, is what proves the refactor is behavior-
preserving: this is the regression test the extraction requires (CLAUDE.md's
TDD rule; T08's "small and neutral refactor" acceptance criterion).

``order_action_space`` is new -- B3's own action spaces
(``TASK_AWARE_ACTION_SPACES``) are hand-authored already in the canonical
least->most-disclosing order, so B3 never needed a function to *produce*
that order. B4 cannot make the same assumption: a policy YAML's
``allowed_actions``/``purpose_actions`` list is author-ordered, not
guaranteed to follow the canonical disclosure ordering
``select_action_for_relevance`` requires of its ``action_space`` argument.
"""

from __future__ import annotations

import pytest

from adaptive_disclosure_gateway.domain import DisclosureAction
from adaptive_disclosure_gateway.task_analysis import TaskRelevance
from adaptive_disclosure_gateway.transformations.relevance_selection import (
    CANONICAL_DISCLOSURE_ORDER,
    order_action_space,
    select_action_for_relevance,
)

# The exact three generic action spaces B3 uses today
# (transformations/task_aware.py's TASK_AWARE_ACTION_SPACES), reused here
# verbatim as the regression fixture -- if the extracted function disagreed
# with B3's own previous private copy on any of these, B3's existing
# behavioral suite (tests/test_task_aware.py) would already be failing.
_IDENTIFIER_SPACE = (DisclosureAction.REMOVE, DisclosureAction.PSEUDONYMIZE)
_SALARY_SPACE = (
    DisclosureAction.REMOVE,
    DisclosureAction.GENERALIZE,
    DisclosureAction.PRESERVE,
)
_DEPARTMENT_SPACE = (DisclosureAction.REMOVE, DisclosureAction.PRESERVE)
_SINGLETON_BLOCK_SPACE = (DisclosureAction.BLOCK_REQUEST,)


@pytest.mark.parametrize(
    ("level", "action_space", "expected"),
    [
        # NOT_RELEVANT always resolves to the least-disclosing (first) entry.
        (TaskRelevance.NOT_RELEVANT, _IDENTIFIER_SPACE, DisclosureAction.REMOVE),
        (TaskRelevance.NOT_RELEVANT, _SALARY_SPACE, DisclosureAction.REMOVE),
        (TaskRelevance.NOT_RELEVANT, _DEPARTMENT_SPACE, DisclosureAction.REMOVE),
        (TaskRelevance.NOT_RELEVANT, _SINGLETON_BLOCK_SPACE, DisclosureAction.BLOCK_REQUEST),
        # RELEVANT_WITHOUT_EXACT_VALUE resolves to the first non-REMOVE entry.
        (
            TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE,
            _IDENTIFIER_SPACE,
            DisclosureAction.PSEUDONYMIZE,
        ),
        (TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE, _SALARY_SPACE, DisclosureAction.GENERALIZE),
        (TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE, _DEPARTMENT_SPACE, DisclosureAction.PRESERVE),
        # A space with no non-REMOVE entry falls back to the first entry
        # rather than raising or inventing an action.
        (
            TaskRelevance.RELEVANT_WITHOUT_EXACT_VALUE,
            (DisclosureAction.REMOVE,),
            DisclosureAction.REMOVE,
        ),
        # RELEVANT_WITH_EXACT_VALUE resolves to PRESERVE when available...
        (TaskRelevance.RELEVANT_WITH_EXACT_VALUE, _SALARY_SPACE, DisclosureAction.PRESERVE),
        # ...and otherwise to the most disclosing available action, never an
        # action outside the space.
        (TaskRelevance.RELEVANT_WITH_EXACT_VALUE, _IDENTIFIER_SPACE, DisclosureAction.PSEUDONYMIZE),
        (TaskRelevance.RELEVANT_WITH_EXACT_VALUE, _DEPARTMENT_SPACE, DisclosureAction.PRESERVE),
    ],
)
def test_select_action_for_relevance_matches_b3s_frozen_behavior(level, action_space, expected):
    assert select_action_for_relevance(level, action_space) is expected


def test_ambiguous_relevance_is_not_handled_by_this_function():
    # AMBIGUOUS is deliberately handled by each caller (task_aware.py's own
    # decide() closure, policy_governed.py's own), never by this shared
    # function -- see task_aware.py's module docstring. This function's
    # contract only recognizes the three non-ambiguous levels.
    with pytest.raises(AssertionError):
        select_action_for_relevance(TaskRelevance.AMBIGUOUS, _SALARY_SPACE)


# --- order_action_space: new for B4, never needed by B3 --------------------


def test_order_action_space_sorts_into_canonical_least_to_most_disclosing_order():
    unordered = (DisclosureAction.PRESERVE, DisclosureAction.REMOVE, DisclosureAction.GENERALIZE)
    assert order_action_space(unordered) == (
        DisclosureAction.REMOVE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    )


def test_order_action_space_drops_duplicates():
    with_duplicates = (DisclosureAction.REMOVE, DisclosureAction.REMOVE, DisclosureAction.PRESERVE)
    assert order_action_space(with_duplicates) == (
        DisclosureAction.REMOVE,
        DisclosureAction.PRESERVE,
    )


def test_order_action_space_silently_drops_actions_outside_the_canonical_four():
    # BLOCK_REQUEST/TASK_DEPENDENT are not disclosure-level actions -- a
    # policy YAML that mistakenly lists one inside allowed_actions must not
    # be smuggled into the ordered space. Callers (policy_governed.py) are
    # responsible for detecting this shrinkage and failing closed; this
    # function's own job is only to order/filter, never to raise.
    with_invalid = (DisclosureAction.REMOVE, DisclosureAction.TASK_DEPENDENT)
    assert order_action_space(with_invalid) == (DisclosureAction.REMOVE,)


def test_canonical_disclosure_order_is_the_frozen_four_action_ladder():
    assert CANONICAL_DISCLOSURE_ORDER == (
        DisclosureAction.REMOVE,
        DisclosureAction.PSEUDONYMIZE,
        DisclosureAction.GENERALIZE,
        DisclosureAction.PRESERVE,
    )
