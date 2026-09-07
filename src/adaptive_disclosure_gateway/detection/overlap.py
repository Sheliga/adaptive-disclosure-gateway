from __future__ import annotations

from adaptive_disclosure_gateway.domain import (
    SensitiveSpan,
    span_offsets_are_structurally_valid,
)

# Fixed precedence used to break ties between equally long overlapping spans.
# Earlier categories win. A category absent from this tuple is treated as
# lowest priority (but resolution still stays total: absent categories are
# then broken by leftmost start, category name and value, in that order).
CATEGORY_PRECEDENCE: tuple[str, ...] = (
    "medical_data",
    "cnpj",
    "cpf",
    "employee_name",
    "email",
    "phone",
    "salary",
    "department",
)


def _precedence_rank(category: str) -> int:
    try:
        return CATEGORY_PRECEDENCE.index(category)
    except ValueError:
        return len(CATEGORY_PRECEDENCE)


def _span_bounds(span: SensitiveSpan) -> tuple[int, int]:
    # No `or 0` coercion: SensitiveSpan.start/end are required, validated
    # ints (issue #17). A span that reaches here with missing/invalid
    # offsets (e.g. constructed via model_construct, bypassing validation)
    # must not be silently normalized into a zero-length (0, 0) span that
    # then passes resolution unnoticed -- it should surface as an error
    # instead.
    return span.start, span.end


def _sort_key(span: SensitiveSpan) -> tuple[int, int, int, str, str]:
    start, end = _span_bounds(span)
    length = end - start
    return (-length, _precedence_rank(span.category), start, span.category, span.value)


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def resolve_overlaps(spans: list[SensitiveSpan]) -> list[SensitiveSpan]:
    """Deterministically resolve overlapping SensitiveSpan detections.

    Rule: the longest span wins. Equal-length overlapping spans are broken by
    ``CATEGORY_PRECEDENCE`` (earlier wins), then by leftmost start offset,
    then by category name, then by value. This ordering is total (it always
    produces a decision) and reproducible (the result does not depend on the
    input order), which is what allows the same text to always be resolved
    the same way.

    Candidates are visited in that priority order and kept unless they
    overlap a span already kept (a variant of the classic weighted
    interval-scheduling greedy algorithm, weighted by the key above rather
    than by end time). The result is returned sorted by start offset.

    Fails closed: every span is checked against
    ``domain.span_offsets_are_structurally_valid`` before any sorting takes
    place. A span with missing or invalid offsets (only reachable via
    ``SensitiveSpan.model_construct``, which bypasses Pydantic validation)
    raises ``ValueError`` naming the offending span's category and offsets --
    never its ``value``, which is sensitive data that must not end up in a
    log or traceback.
    """
    for span in spans:
        if not span_offsets_are_structurally_valid(span):
            raise ValueError(
                "SensitiveSpan with invalid offsets cannot be resolved: "
                f"category={span.category!r} start={span.start!r} end={span.end!r}"
            )

    ordered = sorted(spans, key=_sort_key)
    accepted: list[SensitiveSpan] = []
    accepted_bounds: list[tuple[int, int]] = []

    for span in ordered:
        bounds = _span_bounds(span)
        if any(_overlaps(bounds, taken) for taken in accepted_bounds):
            continue
        accepted.append(span)
        accepted_bounds.append(bounds)

    return sorted(accepted, key=lambda s: _span_bounds(s))
