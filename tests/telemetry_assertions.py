"""Shared OTel span-attribute leak-check helper.

Deliberately named without a ``test_`` prefix so pytest never collects it as
a test module on its own -- it is imported by test modules that need this
assertion (``tests/test_telemetry_privacy.py`` and ``tests/test_pipeline.py``),
not run directly.

Hardening note (Part 1 of issue #26's branch work): a previous version of
this check ran the substring scan over ``str(value)`` for *every* span
attribute, including numeric ones. That produced a real false positive:
``time.perf_counter()`` noise in a ``duration_ms`` float attribute could --
purely by coincidence -- contain the same digit sequence as an unrelated
forbidden value (e.g. a duration of ``0.0850000069476664`` ms contains the
substring ``"8500"``, matching an $8500 salary fixture). Rounding
``duration_ms`` (see ``observability.elapsed_ms_since``) narrowed that one
occurrence, but the check itself was still fragile: any numeric span
attribute -- a byte count, a span count, a duration -- can, by pure numeric
coincidence, contain the same digits as an unrelated forbidden string.

The fix is structural, not another narrowing at the source: a numeric (int
or float) or boolean span attribute cannot carry a sensitive *string* value
in the first place -- its serialized form is only ever its own digits or
truth value, never arbitrary text. So the scan below only ever inspects
``str``-valued attributes and *sequences of ``str``* (the shape OTel uses
for e.g. ``categories``), and explicitly skips int/float/bool attributes.
This removes the whole class of numeric-coincidence false positives while
leaving the real leak channel -- a sensitive value written into a string
attribute, or into one element of a string-sequence attribute -- fully
checked, exactly as before.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _is_scannable_string_value(value: Any) -> bool:
    """True only for a ``str`` attribute or a sequence composed entirely of
    ``str`` elements -- the only OTel span attribute shapes that can carry a
    sensitive *string* value at all.

    Deliberately excludes ``int``, ``float`` and ``bool`` attributes (and any
    sequence of them): a numeric or boolean attribute's serialized form is
    only ever its own digits or truth value, so it cannot be mistaken for an
    unrelated forbidden string except by pure numeric coincidence -- exactly
    the false-positive class this module exists to close. See the module
    docstring for the concrete incident this documents.
    """
    if isinstance(value, str):
        return True
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return len(value) > 0 and all(isinstance(item, str) for item in value)
    return False


def assert_span_attributes_never_leak(spans, *forbidden_values: str) -> None:
    """Assert that no *string-bearing* attribute on any of ``spans`` contains
    any of ``forbidden_values`` as a substring.

    Only ``str`` attributes and sequences-of-``str`` attributes are scanned
    (see ``_is_scannable_string_value``) -- a numeric or boolean attribute is
    never a channel a sensitive string value could leak through, so scanning
    it would only ever produce a coincidental false positive, never catch a
    real leak.
    """
    assert spans, "expected at least one recorded span"
    for span in spans:
        for key, value in span.attributes.items():
            if not _is_scannable_string_value(value):
                continue
            serialized = str(value)
            for forbidden in forbidden_values:
                if not forbidden:
                    continue
                assert forbidden not in serialized, (
                    f"span attribute {key}={serialized!r} leaked forbidden value {forbidden!r}"
                )
