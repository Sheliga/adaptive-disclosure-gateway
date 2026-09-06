"""Pins the architectural isolation acceptance criterion for issue #5:

B1 and the detector must not depend on PolicyRepository, task relevance, or
the pseudonym vault. This is checked at the import-graph level (static
analysis of the actual source) rather than by trusting docstrings, so a
future change that wires B1 to the policy engine or a vault fails the suite
instead of silently regressing the isolation guarantee.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"
FORBIDDEN_SUBSTRINGS = ("polic", "vault", "task_relevance", "task_analysis")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _assert_no_forbidden_imports(path: Path) -> None:
    modules = _imported_modules(path)
    for module in modules:
        lowered = module.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            assert forbidden not in lowered, f"{path} imports forbidden module {module!r}"


def test_detection_package_has_no_policy_or_vault_dependency():
    detection_dir = SRC_ROOT / "detection"
    paths = list(detection_dir.glob("*.py"))
    assert paths, "detection package should exist with source files"
    for path in paths:
        _assert_no_forbidden_imports(path)


def test_b1_sanitizer_has_no_policy_or_vault_dependency():
    b1_path = SRC_ROOT / "transformations" / "b1.py"
    assert b1_path.exists()
    _assert_no_forbidden_imports(b1_path)
