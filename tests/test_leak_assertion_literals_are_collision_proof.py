"""Guards against a hexadecimal-collision false negative in leak assertions.

Incident this pins (see ``tests/test_audit.py``'s ``FORBIDDEN_RAW_SUBSTRINGS``
and ``tests/telemetry_assertions.py``'s module docstring for the sibling
numeric-coincidence incident): many tests prove a sensitive value did not
leak by asserting a short literal derived from it -- typically ``"8500"``,
from the ``Salary: R$ 8500.00`` HR fixture -- is not a substring of some
haystack. Several of those haystacks contain hexadecimal material that has
nothing to do with the fixture: audit records carry HMAC-SHA256
``payload_hash``/``response_hash``/``reconstructed_hash`` digests
(``src/adaptive_disclosure_gateway/audit.py``, keyed by a fresh
``secrets.token_bytes(32)`` per process), and pseudonymized payloads carry
``PSEUDO-{category}-{32 hex chars}`` tokens
(``src/adaptive_disclosure_gateway/vault/in_memory.py``, ``secrets.token_hex``).

``0``-``9`` and ``a``-``f`` are all valid hex digits, so a short literal like
``"8500"`` (measured: ~0.0895% probability per digest) can appear inside one
of these digests by pure chance. That is rare enough to pass hundreds of
local runs and still bite in CI -- which is exactly what happened to PR #74
(GitHub Actions run 35533670630): the assertion passed locally, then failed
in CI when an unrelated digest happened to contain "8500".

The fix already used elsewhere in this suite (``test_audit.py``) is to assert
against a literal that cannot arise from hex digits alone, e.g. ``"8500.00"``
instead of ``"8500"`` -- the ``.`` makes the substring collision-proof by
construction while remaining a more faithful description of what must not
leak (the actual fixture value is ``R$ 8500.00``, not the bare digits).

This test enforces that fix at the AST level across every test module, for
the three shapes this codebase uses to assert a value never leaked:

1. ``assert "LIT" not in haystack`` (or any ``not in`` comparison with a
   string-literal operand, including chained comparisons);
2. a literal inside a tuple/list assigned to a sensitively-named variable,
   e.g. ``SENSITIVE_ORIGINALS = (..., "8500", ...)`` or
   ``FORBIDDEN_RAW_SUBSTRINGS = (...)``;
3. a literal passed as a ``forbidden_values`` argument to
   ``assert_span_attributes_never_leak`` / ``_assert_span_attributes_never_leak``
   (``tests/telemetry_assertions.py``);
4. ``for value in ("A", "8500", ...): assert value not in haystack`` -- the
   literal never appears directly at the ``not in`` compare site, but each
   tuple element still reaches it indirectly through the loop variable.

A literal is flagged when it is short enough to collide (fewer than
``MAX_COLLISION_PRONE_LENGTH`` characters) *and* composed entirely of
hexadecimal characters (``[0-9a-fA-F]``) -- the exact shape that can hide
inside an HMAC digest or a ``secrets.token_hex`` pseudonym token.

A small, explicitly justified ALLOWLIST covers the handful of sites where the
same literal shape is genuinely safe (the haystack being scanned cannot
contain hex-bearing digest/pseudonym material, or the site is deliberately
testing the leak-check helper itself against that exact literal) -- see the
comments next to each entry.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TESTS_ROOT = Path(__file__).parent

# Literals shorter than this can plausibly hide inside a 32-char hex digest
# or pseudonym token by pure chance; see the module docstring for the
# measured ~0.0895%-per-digest collision probability at length 4.
MAX_COLLISION_PRONE_LENGTH = 8

_HEX_ONLY = re.compile(r"^[0-9a-fA-F]+$")

# Variable names that, in this codebase, hold tuples/lists of raw sensitive
# values a test asserts must never leak (mirrors FORBIDDEN_IDENTIFIERS in
# tests/test_no_sensitive_value_in_raises.py: narrow and deliberate rather
# than a blanket keyword match).
_SENSITIVE_COLLECTION_NAME = re.compile(r"(sensitive|forbidden)", re.IGNORECASE)

_LEAK_HELPER_NAMES = {
    "assert_span_attributes_never_leak",
    "_assert_span_attributes_never_leak",
}

# (relative file path, literal) pairs that are exempt, each with the reason
# it cannot actually collide. Keyed by literal rather than line number so a
# harmless edit elsewhere in the file does not require touching this list.
ALLOWLIST: set[tuple[str, str]] = {
    # RecordingParser's stub markdown output; the haystack it is asserted
    # against is IngestionError's message, which reports only deterministic
    # byte/character counts (e.g. "6 characters", "5 characters") -- it never
    # carries a hash, pseudonym or any other hex-bearing digest, so "abcdef"
    # cannot collide with anything here regardless of its hex shape.
    ("test_application_ingestion.py", "abcdef"),
    # Deliberately exercises assert_span_attributes_never_leak itself against
    # a numeric (duration_ms-shaped) span attribute to pin the hardening
    # documented in tests/telemetry_assertions.py's module docstring -- see
    # this module's own docstring. It is not scanning a hash/pseudonym-
    # bearing haystack, so reusing "8500" here is the point of the test, not
    # a collision risk.
    ("test_telemetry_leak_check_hardening.py", "8500"),
}


def _is_collision_prone(value: str) -> bool:
    return bool(value) and len(value) < MAX_COLLISION_PRONE_LENGTH and bool(_HEX_ONLY.match(value))


def _rel(path: Path) -> str:
    return path.relative_to(TESTS_ROOT).as_posix()


def _string_literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _iter_not_in_literal_violations(tree: ast.Module, rel_path: str) -> list[str]:
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for op, left_operand, right_operand in zip(
            node.ops, operands[:-1], operands[1:], strict=True
        ):
            if not isinstance(op, ast.NotIn):
                continue
            for operand in (left_operand, right_operand):
                literal = _string_literal(operand)
                if literal is None:
                    continue
                if not _is_collision_prone(literal):
                    continue
                if (rel_path, literal) in ALLOWLIST:
                    continue
                violations.append(
                    f"{rel_path}:{node.lineno} asserts `not in` against collision-prone "
                    f"hex-only literal {literal!r} (len {len(literal)}) -- a HMAC digest "
                    "or secrets.token_hex pseudonym can contain this substring by pure "
                    "chance; use a literal that cannot arise from hex digits alone "
                    "(e.g. include the fixture's decimal point, as test_audit.py's "
                    "FORBIDDEN_RAW_SUBSTRINGS does with '8500.00')"
                )
    return violations


def _iter_sensitive_collection_violations(tree: ast.Module, rel_path: str) -> list[str]:
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        if not any(_SENSITIVE_COLLECTION_NAME.search(name) for name in names):
            continue
        value = node.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            continue
        for elt in value.elts:
            literal = _string_literal(elt)
            if literal is None:
                continue
            if not _is_collision_prone(literal):
                continue
            if (rel_path, literal) in ALLOWLIST:
                continue
            violations.append(
                f"{rel_path}:{elt.lineno} includes collision-prone hex-only literal "
                f"{literal!r} (len {len(literal)}) in sensitive-values collection "
                f"{names} -- see test_leak_assertion_literals_are_collision_proof.py "
                "module docstring"
            )
    return violations


def _compares_name_not_in_something(body: list[ast.stmt], target_name: str) -> bool:
    """True if any statement in ``body`` (searched recursively) compares the
    loop variable named ``target_name`` with ``not in`` against something --
    the shape ``for value in (...): assert value not in haystack`` uses to
    apply a `not in` check to each literal in a tuple/list indirectly through
    the loop variable, without any literal appearing directly at the compare
    site.
    """
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            for op, left_operand, right_operand in zip(
                node.ops, operands[:-1], operands[1:], strict=True
            ):
                if not isinstance(op, ast.NotIn):
                    continue
                for operand in (left_operand, right_operand):
                    if isinstance(operand, ast.Name) and operand.id == target_name:
                        return True
    return False


def _iter_for_loop_not_in_violations(tree: ast.Module, rel_path: str) -> list[str]:
    """Catches ``for value in ("A", "8500", ...): assert value not in
    haystack`` -- the literals never appear directly at the `not in` compare
    site (pattern (a) above misses it), and the tuple is not assigned to a
    sensitively-named variable (pattern (b) above misses it too).
    """
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        target = node.target
        if not isinstance(target, ast.Name):
            continue
        iterable = node.iter
        if not isinstance(iterable, (ast.Tuple, ast.List)):
            continue
        if not _compares_name_not_in_something(node.body, target.id):
            continue
        for elt in iterable.elts:
            literal = _string_literal(elt)
            if literal is None:
                continue
            if not _is_collision_prone(literal):
                continue
            if (rel_path, literal) in ALLOWLIST:
                continue
            violations.append(
                f"{rel_path}:{elt.lineno} includes collision-prone hex-only literal "
                f"{literal!r} (len {len(literal)}) in a `for {target.id} in (...)` "
                f"tuple whose body asserts `{target.id} not in ...` -- see "
                "test_leak_assertion_literals_are_collision_proof.py module docstring"
            )
    return violations


def _iter_leak_helper_call_violations(tree: ast.Module, rel_path: str) -> list[str]:
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue
        if name not in _LEAK_HELPER_NAMES:
            continue
        # First positional arg is the spans list; the rest are forbidden
        # values.
        for arg in node.args[1:]:
            literal = _string_literal(arg)
            if literal is None:
                continue
            if not _is_collision_prone(literal):
                continue
            if (rel_path, literal) in ALLOWLIST:
                continue
            violations.append(
                f"{rel_path}:{arg.lineno} passes collision-prone hex-only literal "
                f"{literal!r} (len {len(literal)}) to {name}(...) -- see "
                "test_leak_assertion_literals_are_collision_proof.py module docstring"
            )
    return violations


def test_no_leak_assertion_uses_a_collision_prone_hex_only_literal():
    py_files = sorted(TESTS_ROOT.glob("*.py"))
    assert py_files, "expected test modules under tests/"

    all_violations: list[str] = []
    for path in py_files:
        rel_path = _rel(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        all_violations.extend(_iter_not_in_literal_violations(tree, rel_path))
        all_violations.extend(_iter_sensitive_collection_violations(tree, rel_path))
        all_violations.extend(_iter_for_loop_not_in_violations(tree, rel_path))
        all_violations.extend(_iter_leak_helper_call_violations(tree, rel_path))

    assert not all_violations, "\n".join(all_violations)


def test_collision_prone_detector_flags_short_hex_and_spares_others():
    # Pins the detector itself against real defect shapes, not test
    # apparatus: a bare hex-only literal under the length threshold must be
    # caught in all three forms, while a literal made collision-proof by a
    # non-hex character (e.g. '.') or by being long enough must not be.
    assert _is_collision_prone("8500") is True
    assert _is_collision_prone("abcdef") is True
    assert _is_collision_prone("8500.00") is False  # '.' is not hex
    assert _is_collision_prone("g500") is False  # 'g' is not hex
    assert _is_collision_prone("12345678") is False  # too long to be "short"
    assert _is_collision_prone("") is False

    tree = ast.parse(
        'assert "8500" not in payload\n'
        'SENSITIVE_ORIGINALS = ("Ana Souza", "8500")\n'
        'assert_span_attributes_never_leak(spans, "8500")\n'
        "def f(joined):\n"
        '    for value in ("Ana Souza", "8500"):\n'
        "        assert value not in joined\n"
        '    for strategy in ("b0", "b1"):\n'
        "        assert strategy in joined\n"  # positive `in`, not `not in` -> spared
    )
    not_in_violations = _iter_not_in_literal_violations(tree, "synthetic.py")
    collection_violations = _iter_sensitive_collection_violations(tree, "synthetic.py")
    for_loop_violations = _iter_for_loop_not_in_violations(tree, "synthetic.py")
    call_violations = _iter_leak_helper_call_violations(tree, "synthetic.py")

    assert len(not_in_violations) == 1
    assert len(collection_violations) == 1
    assert len(call_violations) == 1
    assert len(for_loop_violations) == 1  # only the "8500" element; "Ana Souza" isn't hex-short
