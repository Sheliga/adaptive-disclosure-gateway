"""Pins the per-treatment architectural isolation acceptance criteria for
issues #5 and #3.

This is checked at the import-graph level (static analysis of the actual
source) rather than by trusting docstrings, so a change that wires a
treatment to something its isolation contract forbids fails the suite
instead of silently regressing the guarantee.

The rule is NOT the same for every treatment:

- Detection and Static Sanitization (B1) must depend on none of policy,
  vault or task-awareness at all -- the strict, original rule from issue #5.
- Reversible Pseudonymization (B2) is *narrowly* allowed to import the
  policy engine and the vault (see
  ``test_reversible_pseudonymizer_*`` below for exactly how narrow), because
  issue #3 requires B2 to resolve pseudonym scope and to authorize
  reconstruction through ``PolicyRepository``, and to store/retrieve
  pseudonyms through a ``Vault``. It must still never import task-relevance
  or task-analysis code: docs/experimental-design.md's B2->B3 comparison
  isolates task-awareness as the *only* variable B3 adds over B2, so if B2
  could consult task relevance that isolation would already be broken
  before B3 exists.
- Direct (B0, issue #25) is stricter than B1: it needs no detection either,
  since no detected span participates in producing its payload at all (the
  payload is the input text, verbatim). So B0 forbids policy, vault,
  detection *and* task-awareness -- it needs none of them.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"

# Full isolation: detection and B1 may depend on none of these.
B1_FORBIDDEN_SUBSTRINGS = ("polic", "vault", "task_relevance", "task_analysis")

# B0 is stricter still: unlike B1 (which imports detection.overlap to
# resolve overlapping spans before slicing), B0 never slices the text at
# all, so it needs no detection dependency either.
B0_FORBIDDEN_SUBSTRINGS = ("polic", "vault", "detect", "task_relevance", "task_analysis")

# B2's allowance is narrow: it may import policy/vault (for scope
# resolution, reconstruction authorization, and pseudonym storage only --
# see the module-level docstring in reversible_pseudonymization.py and the
# static-mapping test below), but task-awareness stays forbidden exactly
# like B1.
B2_FORBIDDEN_SUBSTRINGS = ("task_relevance", "task_analysis")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _assert_no_forbidden_imports(path: Path, forbidden_substrings: tuple[str, ...]) -> None:
    modules = _imported_modules(path)
    for module in modules:
        lowered = module.lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in lowered, f"{path} imports forbidden module {module!r}"


def test_detection_package_has_no_policy_or_vault_dependency():
    detection_dir = SRC_ROOT / "detection"
    paths = list(detection_dir.glob("*.py"))
    assert paths, "detection package should exist with source files"
    for path in paths:
        _assert_no_forbidden_imports(path, B1_FORBIDDEN_SUBSTRINGS)


def test_static_sanitizer_has_no_policy_or_vault_dependency():
    static_sanitization_path = SRC_ROOT / "transformations" / "static_sanitization.py"
    assert static_sanitization_path.exists()
    _assert_no_forbidden_imports(static_sanitization_path, B1_FORBIDDEN_SUBSTRINGS)


def test_direct_discloser_has_no_policy_vault_detection_or_task_awareness_dependency():
    direct_disclosure_path = SRC_ROOT / "transformations" / "direct_disclosure.py"
    assert direct_disclosure_path.exists()
    _assert_no_forbidden_imports(direct_disclosure_path, B0_FORBIDDEN_SUBSTRINGS)


def test_reversible_pseudonymizer_has_no_task_awareness_dependency():
    reversible_pseudonymization_path = (
        SRC_ROOT / "transformations" / "reversible_pseudonymization.py"
    )
    assert reversible_pseudonymization_path.exists()
    _assert_no_forbidden_imports(reversible_pseudonymization_path, B2_FORBIDDEN_SUBSTRINGS)


def test_reversible_pseudonymizer_category_action_mapping_is_static_not_policy_derived():
    """B2 may import PolicyRepository, but only to resolve pseudonym scope
    and to authorize reconstruction -- never to choose the action for a
    category, which must stay the same static, task-independent mapping B1
    uses (docs/experimental-design.md's B1->B2 comparison holds this
    constant; only reversibility changes). Calling
    ``PolicyRepository.decide()`` -- the per-category action-selection
    entrypoint -- would break that, so its absence from B2's source is the
    actual invariant this pins, not just "policy is importable."
    """
    reversible_pseudonymization_path = (
        SRC_ROOT / "transformations" / "reversible_pseudonymization.py"
    )
    tree = ast.parse(
        reversible_pseudonymization_path.read_text(encoding="utf-8"),
        filename=str(reversible_pseudonymization_path),
    )
    decide_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "decide"
    ]
    assert not decide_calls, (
        "reversible_pseudonymization.py must never call PolicyRepository.decide() -- "
        "the category -> action mapping stays static, exactly like B1"
    )

    from adaptive_disclosure_gateway.transformations import reversible_pseudonymization as b2

    assert isinstance(b2.ACTIONS, dict) and b2.ACTIONS, (
        "ACTIONS must be a static, non-empty mapping"
    )
