"""The B3/B4 task-relevance contract (T07 / issue #6).

``TaskAnalyzer`` is the single most important structural guarantee in this
package: its ``analyze`` signature takes *only* ``task`` and ``categories``.
It is deliberately not given a ``GovernanceContext``, ``domain``,
``purpose``, ``requester_role``, ``requester_id``, ``provider_class``,
``policy_version``, raw span values, or ``request.text``. That is what makes
Task-aware (B3) independent of every dimension B4 -- Policy-governed later
adds (see docs/experimental-design.md's B2->B3 and B3->B4 comparisons): the
isolation is enforced by this method's shape, not by trusting that no future
implementation reaches for one of those fields. See
``tests/test_task_analysis_signature_isolation.py``, which pins this
structurally (by inspecting the ``analyze`` signature itself) rather than by
convention alone.
"""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class TaskRelevance(StrEnum):
    """The three explicit relevance levels a task analyzer may report for a
    detected category, plus an explicit "could not determine" outcome.

    Deliberately not a boolean: "relevant" is not one thing here -- a task
    can need a category's *presence* (a stable reference/band suffices) or
    its *exact original value* (nothing less specific will do), and callers
    (``transformations/task_aware.py``) must be able to tell those apart to
    pick the least-disclosing action that still serves the task.
    """

    NOT_RELEVANT = "not_relevant"
    RELEVANT_WITHOUT_EXACT_VALUE = "relevant_without_exact_value"
    RELEVANT_WITH_EXACT_VALUE = "relevant_with_exact_value"
    AMBIGUOUS = "ambiguous"


class TaskAnalysis(BaseModel):
    """One analyzer call's relevance judgement, one entry per category it
    was asked about. A category from the caller's ``categories`` argument
    that is absent from ``relevance_by_category`` is treated by
    ``transformations/task_aware.py`` exactly like an unrecognized relevance
    value -- the analyzer is expected to report on every category it was
    asked to.
    """

    relevance_by_category: dict[str, TaskRelevance] = Field(default_factory=dict)


@runtime_checkable
class TaskAnalyzer(Protocol):
    """Task-relevance judgement, replaceable behind this interface (the
    pilot ships one deterministic implementation --
    ``deterministic.DeterministicTaskAnalyzer`` -- but B3/B4's contract with
    ``transformations/task_aware.py`` is this method shape, not that class).

    ``analyze`` may legitimately raise, and a caller must treat that (and an
    unrecognized relevance value in the result) as fail-closed for the whole
    request -- see ``transformations/task_aware.py``'s module docstring.
    """

    def analyze(self, task: str, categories: Collection[str]) -> TaskAnalysis: ...
