"""Repository-wide guard (T26 / issue #67, extended T29 / issue #72):
``cryptography`` is a base dependency added specifically for sealed,
server-keyed envelopes. Pin that it is imported from a fixed, small
allowlist of modules -- each its own independent AEAD sealer with its own
key material, never sharing an implementation or a key -- so a future
change cannot casually spread a THIRD, uncontrolled crypto implementation
across the codebase. Mirrors ``tests/test_api_architecture.py``'s AST-based
isolation approach.

``application/vault_explorer.py`` (T29 / issue #72) joins
``application/restore_handle.py`` here deliberately: both need
authenticated encryption, but per the module's own docstring, its
per-process random key must never be derived from or shared with the
restore-handle sealer's configured secret -- so it cannot reuse
``restore_handle.py``'s ``RestoreHandleSealer`` and needs ``cryptography``
directly, exactly like that module does.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"

_ALLOWED_IMPORTERS = frozenset(
    {
        "application/restore_handle.py",
        "application/vault_explorer.py",
    }
)


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


def test_cryptography_is_imported_only_by_the_allowlisted_sealer_modules():
    offenders = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        if _imports_cryptography(path):
            relative = path.relative_to(SRC_DIR).as_posix()
            if relative not in _ALLOWED_IMPORTERS:
                offenders.append(relative)
    assert not offenders, f"cryptography imported outside {sorted(_ALLOWED_IMPORTERS)}: {offenders}"


def test_every_allowed_importer_actually_exists_and_imports_cryptography():
    for allowed in _ALLOWED_IMPORTERS:
        path = SRC_DIR / allowed
        assert path.is_file(), f"expected {allowed} to exist"
        assert _imports_cryptography(path), f"expected {allowed} to import cryptography"
