"""Repository-wide guard (T26 / issue #67): ``cryptography`` is a new base
dependency added specifically for the sealed restore handle. Pin that it is
imported from exactly one module, so a future change cannot casually spread
a second, independent crypto implementation across the codebase -- mirrors
``tests/test_api_architecture.py``'s AST-based isolation approach.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"

_ALLOWED_IMPORTER = "application/restore_handle.py"


def _imports_cryptography(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        if any(
            module == "cryptography" or module.startswith("cryptography.") for module in modules
        ):
            return True
    return False


def test_cryptography_is_imported_only_by_the_restore_handle_module():
    offenders = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        if _imports_cryptography(path):
            relative = path.relative_to(SRC_DIR).as_posix()
            if relative != _ALLOWED_IMPORTER:
                offenders.append(relative)
    assert not offenders, f"cryptography imported outside {_ALLOWED_IMPORTER}: {offenders}"


def test_the_allowed_importer_actually_exists_and_imports_cryptography():
    path = SRC_DIR / _ALLOWED_IMPORTER
    assert path.is_file()
    assert _imports_cryptography(path)
