"""Codebase-wide invariant, generalized from T14's fix in
``detection/overlap.py`` (see its ``resolve_overlaps`` docstring) and this
review's fixes in ``transformations/generalization.py``: three of the four
defects found across T14 and the T06/T13 review were the same class of bug
-- a sensitive value escaping through a side channel (an exception message,
in every one of these cases) rather than through the external payload the
rest of the test suite already guards. The rule did not survive T14 into
new code, so this test enforces it at the AST level across all of ``src/``
instead of relying on each new module remembering it.

The rule: a ``raise`` statement must never interpolate, into an f-string
passed to the exception constructor, a bare name or attribute access whose
identifier is one this codebase uses to hold sensitive/original content --
at minimum ``value``, ``text``, ``payload``, ``original``, ``pseudonym``,
``secret`` and ``mapping`` (matched case-insensitively, so both a bare local
like ``value`` and an attribute access like ``span.value`` or
``request.text`` are caught by looking at the trailing identifier). Naming a
*category*, a count, an offset, a type, a scope or an action is fine and
common in this codebase's fail-closed messages -- this test does not
attempt to reason about anything other than a directly named identifier, so
it is deliberately narrow: it will not catch a value laundered through an
intermediate variable with an unrelated name, string concatenation instead
of an f-string, or ``str(exc)`` embedding a lower-level exception's message
(see ``transformations/generalization.py``'s ``from None`` chains for how
that particular gap is closed by hand at the two call sites known to need
it). It is intentionally precise rather than exhaustive: if a legitimate
``raise`` ever trips it, the fix is to reword the message to name the
category/kind of failure instead -- never to weaken this check (see
CLAUDE.md's no-leak invariant).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"

# Case-insensitive identifiers that, in this codebase, are used exclusively
# to hold sensitive/original content rather than category names, counts,
# offsets, types or other safe-to-log metadata.
FORBIDDEN_IDENTIFIERS = {
    "value",
    "text",
    "payload",
    "original",
    "pseudonym",
    "secret",
    "mapping",
}


def _identifier_of(node: ast.expr) -> str | None:
    """The identifier an expression would be keyed off of, for a bare name
    (``value``) or an attribute access (``span.value`` -> ``value``);
    ``None`` for anything else (calls, literals, subscripts, binops, ...),
    which this check does not attempt to reason about.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _offending_identifiers(raise_node: ast.Raise) -> list[str]:
    """Every forbidden identifier interpolated into an f-string anywhere in
    the expression being raised (typically the exception constructor call).
    """
    exc = raise_node.exc
    if exc is None:
        return []
    offenders: list[str] = []
    for node in ast.walk(exc):
        if not isinstance(node, ast.JoinedStr):
            continue
        for part in node.values:
            if not isinstance(part, ast.FormattedValue):
                continue
            identifier = _identifier_of(part.value)
            if identifier is not None and identifier.lower() in FORBIDDEN_IDENTIFIERS:
                offenders.append(identifier)
    return offenders


def _iter_raise_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        offenders = _offending_identifiers(node)
        if offenders:
            violations.append(
                f"{path}:{node.lineno} raises with forbidden identifier(s) {offenders} "
                "interpolated into the message -- name the category/failure kind instead "
                "of the value itself"
            )
    return violations


def test_no_raise_in_src_interpolates_a_sensitive_identifier():
    py_files = sorted(SRC_ROOT.rglob("*.py"))
    assert py_files, "expected source files under src/adaptive_disclosure_gateway"

    all_violations: list[str] = []
    for path in py_files:
        all_violations.extend(_iter_raise_violations(path))

    assert not all_violations, "\n".join(all_violations)


def test_forbidden_identifier_detection_catches_a_bare_name_and_an_attribute_access():
    # Pins the detector itself against a real defect shape (not a sanity
    # check on ast.parse): a bare `value` and an attribute access like
    # `span.value` must both be caught, while an unrelated identifier like
    # `category` must not be flagged.
    tree = ast.parse(
        "def f(span, value, category):\n"
        "    raise ValueError(f'bad {value!r}')\n"
        "    raise ValueError(f'bad {span.value!r}')\n"
        "    raise ValueError(f'category={category!r}')\n"
    )
    raises = [node for node in ast.walk(tree) if isinstance(node, ast.Raise)]
    assert len(raises) == 3

    assert _offending_identifiers(raises[0]) == ["value"]
    assert _offending_identifiers(raises[1]) == ["value"]
    assert _offending_identifiers(raises[2]) == []
