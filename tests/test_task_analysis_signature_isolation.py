"""Pins the structural guarantee ``task_analysis/base.py``'s module
docstring describes: ``TaskAnalyzer.analyze``'s signature is what keeps B3 --
Task-aware independent of every contextual dimension B4 -- Policy-governed
later adds (``domain``, ``purpose``, ``requester_role``, ``requester_id``,
``provider_class``, ``policy_version``), plus the raw text/values a treatment
already has and the analyzer must not additionally receive.

This is checked structurally (the actual parameter list, by
``inspect.signature``, and the actual imports, by AST) rather than by
trusting the docstring's promise -- the same spirit as
``tests/test_treatment_isolation.py`` and
``tests/test_corpus_oracle_isolation.py``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from adaptive_disclosure_gateway.task_analysis import DeterministicTaskAnalyzer
from adaptive_disclosure_gateway.task_analysis.base import TaskAnalyzer

SRC_ROOT = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"
TASK_ANALYSIS_DIR = SRC_ROOT / "task_analysis"


def test_task_analyzer_protocol_analyze_takes_only_task_and_categories():
    signature = inspect.signature(TaskAnalyzer.analyze)
    params = [name for name in signature.parameters if name != "self"]
    assert params == ["task", "categories"], (
        f"TaskAnalyzer.analyze must take exactly (task, categories); got {params}"
    )


def test_deterministic_analyzer_implements_the_same_narrow_signature():
    """The shipped implementation must not widen the Protocol's contract --
    an extra optional parameter would still satisfy ``TaskAnalyzer``
    structurally but would open a channel for a caller to (mis)use.
    """
    signature = inspect.signature(DeterministicTaskAnalyzer.analyze)
    params = [name for name in signature.parameters if name != "self"]
    assert params == ["task", "categories"]


def test_task_analysis_package_never_imports_policy_or_governance_context():
    files = sorted(TASK_ANALYSIS_DIR.glob("*.py"))
    assert files, "expected task_analysis package source files to exist"

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "polic" not in node.module.lower(), (
                    f"{path} imports forbidden module {node.module!r}"
                )
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported_names = {alias.name for alias in node.names}
                assert "GovernanceContext" not in imported_names, (
                    f"{path} imports GovernanceContext -- task_analysis must never see it"
                )
                assert "PolicyRepository" not in imported_names, (
                    f"{path} imports PolicyRepository -- task_analysis must never see it"
                )


def test_task_analysis_package_never_imports_vault_or_pipeline():
    files = sorted(TASK_ANALYSIS_DIR.glob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        for module in modules:
            lowered = module.lower()
            assert "vault" not in lowered, f"{path} imports forbidden module {module!r}"
            assert "pipeline" not in lowered, f"{path} imports forbidden module {module!r}"
