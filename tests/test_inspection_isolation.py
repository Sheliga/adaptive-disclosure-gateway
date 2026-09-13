"""T27 / issue #69: ``application/inspection.py`` must never import or call
into ``vault`` -- everything it needs (category, original value, transformed
value, action) already sits on ``SensitiveSpan``/``Transformation``, which
the decision phase already computed. A future edit that "just calls the
vault to double check" would reintroduce exactly the kind of pseudonym/
original mapping surface T27's own issue explicitly forbids
("nao retornar o mapping global pseudonimo -> original"). Mirrors
``tests/test_restore_handle_import_isolation.py``'s AST-based approach.
"""

from __future__ import annotations

import ast
from pathlib import Path

_INSPECTION_MODULE = (
    Path(__file__).parents[1]
    / "src"
    / "adaptive_disclosure_gateway"
    / "application"
    / "inspection.py"
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_inspection_module_exists():
    assert _INSPECTION_MODULE.is_file(), (
        "expected application/inspection.py (T27 / issue #69's inspection projection)"
    )


def test_inspection_module_never_imports_vault():
    modules = _imported_modules(_INSPECTION_MODULE)
    offenders = [
        module
        for module in modules
        if module == "adaptive_disclosure_gateway.vault"
        or module.startswith("adaptive_disclosure_gateway.vault.")
    ]
    assert not offenders, f"application/inspection.py must not import vault: {offenders}"


def test_inspection_module_never_calls_a_vault_attribute():
    """Belt-and-suspenders over the import-based check above: even an
    indirect reference (e.g. ``import adaptive_disclosure_gateway`` then
    ``adaptive_disclosure_gateway.vault.something``) would still have to
    access an attribute/name literally spelled ``vault`` somewhere in the
    executable source -- this walks the AST rather than grepping raw text,
    so it is not tripped by the module's own docstring discussing vault
    isolation in prose.
    """
    tree = ast.parse(
        _INSPECTION_MODULE.read_text(encoding="utf-8"), filename=str(_INSPECTION_MODULE)
    )
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "vault":
            offenders.append(node.lineno)
        if isinstance(node, ast.Attribute) and node.attr == "vault":
            offenders.append(node.lineno)
    assert not offenders, f"application/inspection.py must not reference `vault`: lines {offenders}"
