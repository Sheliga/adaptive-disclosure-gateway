"""T20 / issue #28, slice 2, absolute rule 2: the dependency arrow points
one way only, ``api`` -> ``application`` -> core -- the core must never
import the HTTP framework.

Mirrors ``tests/test_application_ground_truth_isolation.py``'s AST-based
approach: checked at the source-code level (import targets), not trusted
from docstrings, so a future edit that pulls fastapi/starlette/
pydantic-settings into a core module fails the suite instead of silently
regressing the invariant.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"

# Every module/package this ticket forbids from importing the framework
# (T20 / issue #28's absolute rule 2), relative to SRC_DIR. "api" itself is
# deliberately excluded -- it is the one package allowed to import fastapi.
_CORE_ROOTS = (
    "application",
    "transformations",
    "pipeline.py",
    "domain.py",
    "policies.py",
    "providers",
    "detection",
    "vault",
    "audit.py",
    "experiments",
    "corpus",
)

_FORBIDDEN_MODULE_PREFIXES = ("fastapi", "starlette", "pydantic_settings")


def _core_source_files() -> list[Path]:
    files: list[Path] = []
    for root_name in _CORE_ROOTS:
        root = SRC_DIR / root_name
        if root.is_file():
            files.append(root)
        else:
            files.extend(sorted(root.rglob("*.py")))
    return files


def test_core_roots_actually_resolve_to_real_files():
    """Pins that the glob above actually reaches real source files -- a
    typo'd root name would make the isolation test below vacuously pass
    over an empty file set.
    """
    files = _core_source_files()
    assert len(files) > 20, "expected many core source files to check"
    names = {f.name for f in files}
    assert "service.py" in names
    assert "pipeline.py" in names
    assert "domain.py" in names


def test_core_never_imports_the_http_framework():
    violations = []
    for path in _core_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            for module in modules:
                if module.startswith(_FORBIDDEN_MODULE_PREFIXES):
                    violations.append(
                        f"{path.relative_to(SRC_DIR)} imports forbidden module {module!r}"
                    )
    assert not violations, "\n".join(violations)


def test_api_package_exists_and_is_excluded_from_the_core_check():
    api_dir = SRC_DIR / "api"
    assert api_dir.is_dir()
    assert "api" not in _CORE_ROOTS
