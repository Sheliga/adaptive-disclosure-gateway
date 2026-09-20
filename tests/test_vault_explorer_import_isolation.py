"""Repository-wide guard (T29 / issue #72): ``application/vault_explorer.py``
is the ONLY module under ``application/`` or ``api/`` allowed to call
``Vault.reconstruct`` -- every other route must keep going through
``transformations.decision_application.reconstruct`` (a free function, not a
``.reconstruct(...)`` method call, so it does not trip this check) via the
existing ``execute``/``execute_document`` path. Mirrors
``tests/test_restore_handle_import_isolation.py``'s AST-based approach.

Also pins that ``vault_explorer.py`` holds no module-level mutable state and
imports nothing filesystem/persistence-shaped -- the "no persistence of any
kind" constraint reaches code that has not been written yet, not just what
this module looks like today.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"
_CHECKED_ROOTS = ("application", "api")
_ALLOWED_CALLER = "application/vault_explorer.py"

_FORBIDDEN_PERSISTENCE_MODULES = {"sqlite3", "shelve", "pickle", "dbm"}


def _checked_source_files() -> list[Path]:
    files: list[Path] = []
    for root_name in _CHECKED_ROOTS:
        files.extend(sorted((SRC_DIR / root_name).rglob("*.py")))
    return files


def _calls_reconstruct(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconstruct"
        ):
            return True
    return False


def test_checked_roots_actually_resolve_to_real_files():
    files = _checked_source_files()
    assert len(files) > 10
    names = {f.name for f in files}
    assert "service.py" in names
    assert "app.py" in names


def test_only_vault_explorer_module_calls_reconstruct_under_application_or_api():
    offenders = []
    for path in _checked_source_files():
        if _calls_reconstruct(path):
            relative = path.relative_to(SRC_DIR).as_posix()
            if relative != _ALLOWED_CALLER:
                offenders.append(relative)
    assert not offenders, f".reconstruct(...) called outside {_ALLOWED_CALLER}: {offenders}"


def test_the_allowed_caller_actually_exists_and_calls_reconstruct():
    path = SRC_DIR / _ALLOWED_CALLER
    assert path.is_file()
    assert _calls_reconstruct(path)


def test_vault_explorer_module_imports_no_persistence_primitive():
    path = SRC_DIR / _ALLOWED_CALLER
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        for module in modules:
            top_level = module.split(".")[0]
            if top_level in _FORBIDDEN_PERSISTENCE_MODULES:
                offenders.append(module)
    assert not offenders, f"vault_explorer.py must not import persistence modules: {offenders}"


def test_vault_explorer_module_declares_no_module_level_mutable_state():
    """No module-level ``dict``/``list``/``set`` literal assignment -- the
    only stateful object here must be a ``VaultExplorerSealer`` instance
    a caller constructs and owns itself, never a shared module-level
    collection that would let one caller's entries leak into another's.
    """
    path = SRC_DIR / _ALLOWED_CALLER
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if isinstance(value, (ast.Dict, ast.List, ast.Set)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            offenders.extend(getattr(target, "id", "<complex target>") for target in targets)
    assert not offenders, f"module-level mutable state found in {_ALLOWED_CALLER}: {offenders}"
