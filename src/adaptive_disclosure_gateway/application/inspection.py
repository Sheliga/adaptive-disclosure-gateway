"""The T27 / issue #69 visual diff/inspector projection: builds a
``DisclosureInspection`` from a source text and the ``DisclosureDecision``
already computed for it -- never a second decision phase, never a string
diff.

Source of truth is the pipeline's own structured metadata. Every
transforming treatment (B1 -- Static Sanitization through B4 --
Policy-governed) builds ``decision.result.external_payload`` by walking
``ordered = detection.overlap.resolve_overlaps(spans)`` and appending
exactly one ``Transformation`` per ordered span, in the same order (see
``transformations/decision_application.py::_allowed_result`` and
``transformations/static_sanitization.py::StaticSanitizer._allowed_result``,
which both follow this shape independently). ``_structured_alignment``
below re-derives that same walk from ``decision.spans``/
``decision.result.transformations`` rather than diffing ``text`` against
``decision.result.external_payload`` as strings: a string diff cannot tell
two equal occurrences of the same value apart (the mis-anchoring case a
naive implementation would get wrong -- see the test suite's dedicated
guard), and it cannot attribute a segment to the category/action that
produced it.

B0 -- Direct (``transformations/direct_disclosure.py``) is a deliberate
exception to that per-span shape: its single ``Transformation`` is a
synthetic, whole-text audit entry (category ``"direct_disclosure"``) that
never corresponds to a real detected span, by design -- B0's payload does
not depend on detection at all. ``_structured_alignment`` therefore never
succeeds for it (the span/category/count checks below fail for
essentially any detected-span shape), and ``build_inspection`` falls back
to treating the whole text as one untouched segment whenever
``external_payload == text`` -- which is true for B0 unconditionally, and
also true for any other treatment that happened to detect and transform
nothing at all (in which case ``_structured_alignment`` already succeeds
directly, on the trivial zero-span/zero-transformation case, and this
fallback is never reached).

Every alignment requirement is verified, never assumed: a treatment whose
transformations do not zip 1:1 against ``resolve_overlaps(decision.spans)``
in category, value, and text-offset order -- or whose reconstructed
``original``/``disclosed`` strings do not equal ``text``/
``decision.result.external_payload`` exactly -- falls through to the
whole-text fallback above, and if that does not apply either, the whole
projection fails closed (``unavailable_reason="alignment_failed"``) rather
than emitting a partial or best-effort result. ``build_inspection`` never
raises: any exception encountered while building the projection (e.g. from
``resolve_overlaps`` over a structurally invalid span) is caught and
treated exactly like any other alignment failure.

No-leak invariant: this module never imports ``vault`` and never calls any
vault method (pinned by ``tests/test_inspection_isolation.py``) -- everything
it needs (category, original value, transformed value, action) already sits
on ``SensitiveSpan``/``Transformation``, which the decision phase already
computed. It opens no OTel span and sets no span attribute of its own, so
there is nothing here for CLAUDE.md's no-leak invariant to catch a value
escaping through.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.application.contracts import (
    DisclosureInspection,
    DisclosureInspectionSegment,
)
from adaptive_disclosure_gateway.detection.overlap import resolve_overlaps
from adaptive_disclosure_gateway.domain import SensitiveSpan, Transformation
from adaptive_disclosure_gateway.pipeline import DisclosureDecision

_BLOCKED = DisclosureInspection(available=False, unavailable_reason="blocked", segments=())
_ALIGNMENT_FAILED = DisclosureInspection(
    available=False, unavailable_reason="alignment_failed", segments=()
)


def _untouched(segment_text: str) -> DisclosureInspectionSegment:
    return DisclosureInspectionSegment(
        action=None, category=None, original=segment_text, disclosed=segment_text
    )


def _structured_alignment(
    text: str,
    spans: list[SensitiveSpan],
    transformations: list[Transformation],
    external_payload: str,
) -> tuple[DisclosureInspectionSegment, ...] | None:
    """Attempt the strict per-span alignment described in the module
    docstring. Returns the resulting segments (an empty tuple is a valid,
    successful result -- both ``spans``/``transformations`` empty and
    ``text`` empty) or ``None`` if any requirement is violated -- never
    raises.
    """
    try:
        ordered = resolve_overlaps(spans)
    except Exception:  # noqa: BLE001 -- fail-closed by design, kind-only
        return None

    if len(ordered) != len(transformations):
        return None

    segments: list[DisclosureInspectionSegment] = []
    cursor = 0
    for span, transformation in zip(ordered, transformations):
        if span.category != transformation.category:
            return None
        if span.value != transformation.original:
            return None
        if span.start < cursor:
            return None
        if text[span.start : span.end] != span.value:
            return None

        if span.start > cursor:
            segments.append(_untouched(text[cursor : span.start]))

        disclosed = transformation.transformed if transformation.transformed is not None else ""
        segments.append(
            DisclosureInspectionSegment(
                action=transformation.action,
                category=transformation.category,
                original=transformation.original,
                disclosed=disclosed,
            )
        )
        cursor = span.end

    if cursor < len(text):
        segments.append(_untouched(text[cursor:]))

    reconstructed_original = "".join(segment.original for segment in segments)
    reconstructed_disclosed = "".join(segment.disclosed for segment in segments)
    if reconstructed_original != text or reconstructed_disclosed != external_payload:
        return None

    return tuple(segments)


def _build_inspection(text: str, decision: DisclosureDecision) -> DisclosureInspection:
    if decision.result.status != "allowed":
        return _BLOCKED

    segments = _structured_alignment(
        text, decision.spans, decision.result.transformations, decision.result.external_payload
    )
    if segments is not None:
        return DisclosureInspection(available=True, unavailable_reason=None, segments=segments)

    if decision.result.external_payload == text:
        # The B0 -- Direct fallback described in the module docstring (also
        # reachable, harmlessly, by any other treatment whose transformations
        # cannot be structurally aligned but which still disclosed the text
        # unchanged): the whole text as one untouched segment, or no segment
        # at all for empty text.
        return DisclosureInspection(
            available=True,
            unavailable_reason=None,
            segments=() if text == "" else (_untouched(text),),
        )

    return _ALIGNMENT_FAILED


def build_inspection(text: str, decision: DisclosureDecision) -> DisclosureInspection:
    """Build the visual diff/inspector projection of ``decision`` over
    ``text``. Never raises -- see the module docstring's fail-closed
    contract.
    """
    try:
        return _build_inspection(text, decision)
    except Exception:  # noqa: BLE001 -- fail-closed by design, kind-only
        return _ALIGNMENT_FAILED
