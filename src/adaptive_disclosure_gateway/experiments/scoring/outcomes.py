"""Separated outcome classification (T10 / issue #8).

The brief is explicit that these must never be fused into one flag or into
each other: ``policy_block``, ``policy_restricted``, ``impossible_under_policy``,
``ordinary_utility_failure``, ``provider_failure``. This module is the one
place that decides each of them, from ``CaseExecution`` (no oracle needed
for the first four) plus a ``UtilityScore`` (needed only for the fifth).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..execution import CaseExecution
from .utility import UtilityScore


@dataclass(frozen=True)
class CaseOutcomeFlags:
    blocked: bool
    policy_block: bool
    policy_restricted: bool
    impossible_under_policy: bool
    provider_called: bool
    provider_failure: bool


def classify_case_outcomes(case_execution: CaseExecution) -> CaseOutcomeFlags:
    result = case_execution.execution.disclosure_result
    audit = case_execution.execution.audit
    b4 = case_execution.b4_metadata

    return CaseOutcomeFlags(
        blocked=result.status == "blocked",
        policy_block=bool(b4 and "policy_block" in b4.block_reason_classes),
        policy_restricted=bool(b4 and b4.policy_restricted_categories),
        impossible_under_policy=bool(b4 and b4.impossible_under_policy_categories),
        provider_called=audit.provider.called,
        provider_failure=audit.provider.failed,
    )


def classify_ordinary_utility_failure(utility: UtilityScore, outcomes: CaseOutcomeFlags) -> bool:
    """``True`` only for a utility shortfall that is not already explained
    by one of the other, separately-reported outcome classes.

    A hard policy block (``outcomes.blocked``) is its own outcome, not an
    "ordinary" task failure -- the task was never even attempted.
    Impossible-under-policy (``outcomes.impossible_under_policy``) is also
    its own, narrower outcome (docs/experimental-design.md: "a task that
    cannot be executed because required information is forbidden by policy
    is not counted as an ordinary utility failure"). Everything else that
    still fails or is left indeterminate is an ordinary utility failure --
    including a B3 -- Task-aware analyzer read that happens to under- or
    over-minimize with no policy involved at all.
    """
    if utility.overall not in ("not_answerable", "indeterminate"):
        return False
    if outcomes.blocked:
        return False
    return not outcomes.impossible_under_policy
