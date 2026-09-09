"""The single place that decides *which* concrete B0-B4 class to
instantiate for a given ``Treatment`` (moved out of ``experiments/treatments.py``
by T20 / issue #28, slice 1).

Why this module exists here, not in ``experiments`` or ``application``: both
``experiments`` (T10's experiment runner) and ``application`` (T20's
advisor-demo use-case boundary) need to construct a treatment object from a
``Treatment`` enum member, given the same primitives every treatment
constructor already accepts (``Vault``, ``PolicyRepository``, optionally a
``TaskAnalyzer``). Neither package should depend on the other to get this:
``experiments`` is T10's runner, ``application`` is a separate, later
consumer of the same core, and there is no reason for a demo-facing product
service to import runner code (or vice versa) just to build a treatment.
Writing a second factory in ``application`` was ruled out explicitly (T20's
"no duplicated scientific or security logic" rule covers this factory too,
even though it contains no disclosure-control logic of its own -- a second
copy of the same B0-B4 -> class mapping is exactly the kind of drift this
rule exists to prevent). So the function lives here, in a module neither
``experiments`` nor ``application`` owns, and both import it --
``experiments/treatments.py`` re-exports it unchanged so every existing
runner call site (``experiments/execution.py``'s ``from .treatments import
build_treatment``) keeps working without edits.

This is wiring code, not production treatment code: no treatment module
imports this, and this module never implements disclosure-control logic
itself -- it only constructs the constructors already frozen in
``transformations/``.

Receives no ``CaseOracle``, no corpus object at all -- only the primitives
every treatment constructor already accepts. See
``tests/test_experiments_ground_truth_isolation.py`` (for the experiments
side of this guarantee) and ``tests/test_application_ground_truth_isolation.py``
(for the application side).
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
