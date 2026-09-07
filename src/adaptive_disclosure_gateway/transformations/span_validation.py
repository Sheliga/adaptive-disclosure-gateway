"""Shared text-relative validation for ``SensitiveSpan`` at the treatment
boundary (issue #17).

``SensitiveSpan`` itself (see ``domain.py``) already rejects offsets that are
structurally impossible without knowing the source text: missing, negative,
inverted or zero-length. It cannot go further than that, because the model
has no access to the text the offsets are supposed to index into.

The checks here close that remaining gap -- ``end`` must be within the text,
and the slice the offsets claim must actually equal ``span.value`` -- on top
of the structural check (``domain.span_offsets_are_structurally_valid``),
which is deliberately re-run from scratch here rather than trusted, because
``SensitiveSpan.model_construct`` bypasses Pydantic validation entirely, so a
caller can hand a treatment a structurally invalid span despite the
model-level guard; this boundary is what actually stops it from reaching
payload slicing.

Every treatment (B1 today, B2/B3/B4 later) must call this before slicing
``request.text`` against supplied spans, so this lives outside any single
treatment module.
"""

from __future__ import annotations

from collections.abc import Iterable

from adaptive_disclosure_gateway.domain import (
    SensitiveSpan,
    span_offsets_are_structurally_valid,
)


def span_matches_text(span: SensitiveSpan, text: str) -> bool:
    """True only if ``span``'s offsets are safe to slice ``text`` with and
    the slice they claim equals ``span.value`` exactly.
    """
    if not span_offsets_are_structurally_valid(span):
        return False
    if span.end > len(text):
        return False
    return text[span.start : span.end] == span.value


def spans_are_valid(spans: Iterable[SensitiveSpan], text: str) -> bool:
    """True only if every span in ``spans`` passes ``span_matches_text``
    against ``text``.
    """
    return all(span_matches_text(span, text) for span in spans)
