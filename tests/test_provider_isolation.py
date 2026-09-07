"""Pins the provider isolation acceptance criterion for issue #12: the
``providers`` package is the architecture's outermost, one-way wall -- a
provider implementation must never be able to reach back into policy, the
vault or detection, because those are exactly the mechanisms that already
decided what a treatment is allowed to disclose. If a provider could import
any of them, it could in principle re-derive or re-request something a
treatment withheld.

Checked at the import-graph level (static analysis of the actual source),
the same way ``tests/test_treatment_isolation.py`` pins B1/B2's isolation,
rather than trusting docstrings.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

SRC_ROOT = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"

# "polic" catches policy/policies; "vault" catches the vault package;
# "detect" catches the detection package -- mirrors the substring style
# already used by tests/test_treatment_isolation.py.
FORBIDDEN_SUBSTRINGS = ("polic", "vault", "detect")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_providers_package_has_no_policy_vault_or_detection_dependency():
    providers_dir = SRC_ROOT / "providers"
    paths = list(providers_dir.glob("*.py"))
    assert paths, "providers package should exist with source files"
    for path in paths:
        modules = _imported_modules(path)
        for module in modules:
            lowered = module.lower()
            for forbidden in FORBIDDEN_SUBSTRINGS:
                assert forbidden not in lowered, f"{path} imports forbidden module {module!r}"


def test_provider_request_carries_exactly_payload_and_task_fields():
    """The isolation boundary in ``docs``/issue #12 is that widening what a
    provider can see must require deliberately adding a field to
    ``ProviderRequest``, not merely forgetting to strip one from some larger
    object. Pinning the exact field set turns any such widening into a
    reviewable, intentional test change instead of a silent regression --
    e.g. someone routing a whole ``GovernanceContext`` or the original
    ``DisclosureRequest`` into a provider call by accident.
    """
    from adaptive_disclosure_gateway.providers import ProviderRequest

    field_names = {f.name for f in dataclasses.fields(ProviderRequest)}
    assert field_names == {"payload", "task"}
