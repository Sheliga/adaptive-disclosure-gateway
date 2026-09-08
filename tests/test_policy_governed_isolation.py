"""Extends tests/test_treatment_isolation.py's ``PolicyRepository.decide()``
allowlist with B4's single, explicit, named exception (T08 / issue #7).

Every treatment before B4 is forbidden from calling
``PolicyRepository.decide()`` -- the per-category contextual action
entrypoint -- and may only use ``PolicyRepository`` for
``resolve_pseudonym_scope``/``is_reconstruction_authorized`` (pinned,
unmodified, by ``tests/test_treatment_isolation.py``'s allowlist tests:
``test_shared_and_b2_b3_modules_use_policy_repository_only_for_scope_and_reconstruction``
and its siblings -- none of those tests, or the files they scan, change for
B4). B4 -- Policy-governed is the first and only treatment allowed to call
``decide()``, and that usage must stay localized to
``transformations/policy_governed.py`` specifically -- not
``decision_application.py`` (shared with B2/B3), not ``task_aware.py``, not
``reversible_pseudonymization.py``.

This is checked two ways, so the guarantee is a real allowlist rather than a
hand-maintained blocklist:

1. **Positive control** -- ``policy_governed.py`` is confirmed to actually
   call ``.decide()``. Without this, the negative check below could pass
   vacuously if B4 stopped using the one entrypoint it exists to exercise.
2. **Negative, codebase-wide check** -- every *other* production source file
   under ``src/adaptive_disclosure_gateway`` is scanned (not a fixed list of
   suspects) for a call to ``.decide()`` on anything shaped like a
   ``PolicyRepository``; none may have one. A future module that adds a new
   ``.decide()`` call anywhere else fails this immediately, without needing
   to be added to any denylist by hand.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"
POLICY_GOVERNED_PATH = SRC_ROOT / "transformations" / "policy_governed.py"

_POLICY_RECEIVER_NAMES = {"policy_repository", "policyrepository", "policies"}
_POLICY_RECEIVER_ATTRS = {"policy_repository", "_policies", "policies"}


def _is_policy_like_receiver(value: ast.expr) -> bool:
    """True if ``value`` -- the object a method is being called on -- is
    shaped like this codebase's ``PolicyRepository``: a bare name such as
    ``policy_repository``/``policies``, or an attribute such as
    ``self._policies``. Mirrors
    ``tests/test_treatment_isolation.py``'s ``_is_policy_like_receiver``
    (kept as an independent copy here rather than imported, so this file's
    own check does not depend on that module's internals staying stable).
    """
    if isinstance(value, ast.Name):
        return value.id.lower() in _POLICY_RECEIVER_NAMES
    if isinstance(value, ast.Attribute):
        return value.attr.lower() in _POLICY_RECEIVER_ATTRS
    return False


def _decide_call_lines(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "decide"
            and _is_policy_like_receiver(node.func.value)
        ):
            lines.append(node.lineno)
    return lines


def test_policy_governed_module_exists_and_actually_calls_policy_repository_decide():
    assert POLICY_GOVERNED_PATH.exists(), "expected transformations/policy_governed.py to exist"
    lines = _decide_call_lines(POLICY_GOVERNED_PATH)
    assert lines, (
        "expected transformations/policy_governed.py to call "
        "PolicyRepository.decide() -- B4 is the treatment authorized to use it; "
        "an empty result here means this positive control is not actually checking anything"
    )


def test_no_module_other_than_policy_governed_calls_policy_repository_decide():
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path == POLICY_GOVERNED_PATH:
            continue
        for lineno in _decide_call_lines(path):
            violations.append(f"{path.relative_to(SRC_ROOT.parents[1])}:{lineno}")

    assert not violations, (
        "PolicyRepository.decide() must only be called from "
        f"transformations/policy_governed.py -- found unexpected call(s) at: {violations}"
    )
