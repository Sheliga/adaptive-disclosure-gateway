"""T20 / issue #28, slice 1: ``build_treatment`` moved to the neutral
``treatment_factory`` module so both the T10 experiment runner
(``experiments.treatments``) and the new ``application`` package can build
a treatment without either depending on the other. Pins the refactor did not
fork the factory into two implementations and did not change what it builds.
"""

from __future__ import annotations

import ast
from pathlib import Path

from adaptive_disclosure_gateway import treatment_factory
from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.experiments import treatments as experiments_treatments
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations import (
    DirectDiscloser,
    PolicyGovernedDiscloser,
    ReversiblePseudonymizer,
    StaticSanitizer,
    TaskAwareDiscloser,
)
from adaptive_disclosure_gateway.vault import InMemoryVault

TREATMENT_FACTORY_PATH = (
    Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway" / "treatment_factory.py"
)
POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def test_experiments_treatments_reexports_the_same_function_object():
    """A re-export, not a second copy: identity, not just equal behavior."""
    assert experiments_treatments.build_treatment is treatment_factory.build_treatment


def test_treatment_factory_builds_the_expected_class_for_every_treatment():
    vault = InMemoryVault()
    policy_repository = PolicyRepository.from_directory(POLICY_DIR)
    expected = {
        Treatment.DIRECT: DirectDiscloser,
        Treatment.STATIC_SANITIZATION: StaticSanitizer,
        Treatment.REVERSIBLE_PSEUDONYMIZATION: ReversiblePseudonymizer,
        Treatment.TASK_AWARE: TaskAwareDiscloser,
        Treatment.POLICY_GOVERNED: PolicyGovernedDiscloser,
    }
    for treatment, expected_class in expected.items():
        built = treatment_factory.build_treatment(
            treatment, vault=vault, policy_repository=policy_repository
        )
        assert isinstance(built, expected_class)
        assert built.treatment is treatment


def test_treatment_factory_never_imports_the_corpus_package():
    """Mirrors tests/test_corpus_oracle_isolation.py's rule for every other
    production module that builds treatments: this neutral, shared factory
    must never import the corpus/oracle package either, since it is now a
    dependency of the application layer as well as the runner.
    """
    tree = ast.parse(
        TREATMENT_FACTORY_PATH.read_text(encoding="utf-8"), filename=str(TREATMENT_FACTORY_PATH)
    )
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    assert not any("corpus" in module.lower() for module in modules)
