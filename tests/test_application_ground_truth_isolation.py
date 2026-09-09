"""Architectural isolation between the T20 application/use-case boundary and
ground truth (T20 / issue #28, slice 1, absolute rule 4).

Mirrors ``tests/test_corpus_oracle_isolation.py``'s AST-based approach: the
``application`` package must never import or reference ``CaseOracle``, the
bare identifier ``oracle``, ``CorpusCase`` (the bundled input+oracle type),
or anything from ``experiments.scoring``. This is checked at the
source-code level (Name/Attribute identifiers, import targets) rather than
trusted from docstrings, so a future edit that wires in ground truth for
convenience fails the suite instead of silently regressing the invariant.
"""

from __future__ import annotations

import ast
from pathlib import Path

APPLICATION_DIR = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway" / "application"

_FORBIDDEN_IDENTIFIERS = {"CaseOracle", "oracle", "CorpusCase"}


def _application_source_files() -> list[Path]:
    files = sorted(APPLICATION_DIR.glob("*.py"))
    assert files, "expected application package source files to check"
    return files


def test_application_source_files_actually_cover_the_new_t20_modules():
    """Pins that the glob above actually reaches the modules this ticket
    adds -- a typo'd directory would make every other test in this file
    vacuously pass over an empty/incomplete file set.
    """
    names = {path.name for path in _application_source_files()}
    for expected in (
        "ingestion.py",
        "contracts.py",
        "summaries.py",
        "examples.py",
        "service.py",
    ):
        assert expected in names, f"expected {expected} to exist under application/"


def test_application_package_never_references_case_oracle_or_corpus_case():
    violations = []
    for path in _application_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            if name in _FORBIDDEN_IDENTIFIERS:
                violations.append(f"{path.name}:{node.lineno} references forbidden name {name!r}")
    assert not violations, "\n".join(violations)


def test_application_package_never_imports_the_oracle_module_or_experiments_scoring():
    violations = []
    for path in _application_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if module.endswith("corpus.oracle") or "experiments.scoring" in module:
                    violations.append(f"{path.name} imports forbidden module {module!r}")
    assert not violations, "\n".join(violations)


def test_application_package_never_imports_experiments_at_all():
    """Stronger than the scoring-only check above: the T20 application
    layer is a separate consumer of the core from the T10 experiment
    runner, not a dependent of it (see treatment_factory.py's module
    docstring for why build_treatment was moved to a neutral module instead
    of importing experiments.treatments from here).
    """
    violations = []
    for path in _application_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if "adaptive_disclosure_gateway.experiments" in module:
                    violations.append(f"{path.name} imports forbidden module {module!r}")
    assert not violations, "\n".join(violations)
