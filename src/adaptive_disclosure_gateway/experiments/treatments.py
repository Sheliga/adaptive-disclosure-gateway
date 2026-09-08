"""Treatment factory for T10's experiment runner.

The only place the runner decides *which* B0-B4 class to instantiate. This
is runner code, not production treatment code: no treatment module imports
this, and this module never implements disclosure-control logic itself --
it only wires up the constructors already frozen in ``transformations/``.

Receives no ``CaseOracle``, no corpus object at all -- only the primitives
every treatment constructor already accepts (``Vault``, ``PolicyRepository``,
optionally a ``TaskAnalyzer``). See
``tests/test_experiments_ground_truth_isolation.py``.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.pipeline import DisclosureTreatment
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.task_analysis import TaskAnalyzer
from adaptive_disclosure_gateway.transformations import (
    DirectDiscloser,
    PolicyGovernedDiscloser,
    ReversiblePseudonymizer,
    StaticSanitizer,
    TaskAwareDiscloser,
)
from adaptive_disclosure_gateway.vault import Vault


def build_treatment(
    treatment: Treatment,
    *,
    vault: Vault,
    policy_repository: PolicyRepository,
    task_analyzer: TaskAnalyzer | None = None,
) -> DisclosureTreatment:
    """Construct the treatment object identified by ``treatment``.

    ``vault``/``policy_repository`` are ignored by treatments that do not
    need them (B0, B1) -- always accepted here anyway so a caller can build
    one uniformly for every treatment in a run without branching.
    """
    if treatment is Treatment.DIRECT:
        return DirectDiscloser()
    if treatment is Treatment.STATIC_SANITIZATION:
        return StaticSanitizer()
    if treatment is Treatment.REVERSIBLE_PSEUDONYMIZATION:
        return ReversiblePseudonymizer(vault=vault, policy_repository=policy_repository)
    if treatment is Treatment.TASK_AWARE:
        return TaskAwareDiscloser(
            vault=vault, policy_repository=policy_repository, task_analyzer=task_analyzer
        )
    if treatment is Treatment.POLICY_GOVERNED:
        return PolicyGovernedDiscloser(
            vault=vault, policy_repository=policy_repository, task_analyzer=task_analyzer
        )
    raise ValueError(f"unknown treatment: {treatment!r}")
