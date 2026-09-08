"""Stage-aware timing extraction from real ``pipeline.run_disclosure_case``
spans (T10 / issue #8).

The span inventory (module docstrings of ``pipeline.py``, the treatment
modules and ``detection/detector.py``) is fixed and already emitted in
production:

    detection.detect
    <semantic>.sanitize        (direct_disclosure / static_sanitization /
                                 reversible_pseudonymization / task_aware /
                                 policy_governed)
    <semantic>.reconstruct     (reversible_pseudonymization / task_aware /
                                 policy_governed only)
    pipeline.run_disclosure_case

``pipeline.run_disclosure_case`` calls ``detector.detect(request.text)`` and
then ``treatment.sanitize(request, spans)`` *sequentially*, inside its own
``with tracer.start_as_current_span("pipeline.run_disclosure_case")`` block
-- so both ``detection.detect`` and ``<semantic>.sanitize`` are direct
children (siblings of each other) of the pipeline span, never nested inside
one another. That structural fact -- not a self-reported duration attribute
-- is what this module uses to compute a treatment's own wall-clock latency
and to prove it excludes detection time: a sibling span's recorded
``start_time``/``end_time`` (OTel SDK timestamps, nanoseconds since the
epoch) cannot overlap the time spent inside a different sibling span that
already finished before it started.

There is no span around the provider invocation (see
``experiments/provider_instrumentation.py``): ``provider_ms`` is populated
by the caller from a ``ProviderCallMetrics``, not from anything here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from opentelemetry.sdk.trace import ReadableSpan

_PIPELINE_SPAN_NAME = "pipeline.run_disclosure_case"
_DETECTION_SPAN_NAME = "detection.detect"


@dataclass(frozen=True)
class StageTimings:
    """Per-case stage latencies, in milliseconds, extracted from real spans.

    ``detection_ms`` is the *first* ``detection.detect`` child span (over
    ``request.text``) -- the one every treatment comparison must hold
    constant. ``task_detection_ms`` is the second one, if present (the
    fail-closed check ``pipeline.run_disclosure_case`` runs over
    ``request.task`` for every treatment except the B0 unsafe-control
    baseline) -- never folded into ``detection_ms`` so B0's genuine
    exemption from that second check stays visible rather than being
    silently averaged away. Any field is ``None`` when the corresponding
    span never fired (e.g. ``reconstruction_ms`` for B0/B1, or for a blocked
    request).
    """

    detection_ms: float | None
    task_detection_ms: float | None
    treatment_ms: float | None
    reconstruction_ms: float | None
    pipeline_total_ms: float | None


def _duration_ms(span: ReadableSpan) -> float:
    return (span.end_time - span.start_time) / 1_000_000


def _find_root(spans: Sequence[ReadableSpan]) -> ReadableSpan | None:
    for span in spans:
        if span.name == _PIPELINE_SPAN_NAME:
            return span
    return None


def _children_of(spans: Sequence[ReadableSpan], parent: ReadableSpan) -> list[ReadableSpan]:
    parent_span_id = parent.context.span_id
    return [
        span for span in spans if span.parent is not None and span.parent.span_id == parent_span_id
    ]


def extract_stage_timings(spans: Sequence[ReadableSpan]) -> StageTimings:
    """Extract per-stage timings for one case run from its captured spans.

    Returns every field ``None`` if no ``pipeline.run_disclosure_case`` span
    is present at all (defensive only -- ``span_capture.run_case_with_span_capture``
    always produces one for a real run).
    """
    root = _find_root(spans)
    if root is None:
        return StageTimings(None, None, None, None, None)

    children = _children_of(spans, root)
    detection_spans = sorted(
        (span for span in children if span.name == _DETECTION_SPAN_NAME),
        key=lambda span: span.start_time,
    )
    treatment_spans = [span for span in children if span.name.endswith(".sanitize")]
    reconstruction_spans = [span for span in children if span.name.endswith(".reconstruct")]

    return StageTimings(
        detection_ms=_duration_ms(detection_spans[0]) if detection_spans else None,
        task_detection_ms=(_duration_ms(detection_spans[1]) if len(detection_spans) > 1 else None),
        treatment_ms=_duration_ms(treatment_spans[0]) if treatment_spans else None,
        reconstruction_ms=(_duration_ms(reconstruction_spans[0]) if reconstruction_spans else None),
        pipeline_total_ms=_duration_ms(root),
    )


def b0_treatment_span_is_isolated_from_detection(spans: Sequence[ReadableSpan]) -> bool:
    """Structural proof that B0's treatment latency excludes detection time.

    True only if all of the following hold against the *actual* recorded
    spans of one run:

    - a ``pipeline.run_disclosure_case`` root span exists;
    - both ``detection.detect`` and ``direct_disclosure.sanitize`` are direct
      children of that root (siblings of each other, neither nested inside
      the other);
    - the detection span's own recorded end time is at or before the
      treatment span's own recorded start time (i.e. they do not overlap --
      detection finished running before the treatment span even started).

    This is checked against real OTel SDK timestamps, not any span's
    self-reported ``*.duration_ms`` attribute -- so it is not circular with
    how ``treatment_ms`` above is computed from the same span.
    """
    root = _find_root(spans)
    if root is None:
        return False
    children = _children_of(spans, root)
    detection = next((span for span in children if span.name == _DETECTION_SPAN_NAME), None)
    treatment = next((span for span in children if span.name == "direct_disclosure.sanitize"), None)
    if detection is None or treatment is None:
        return False

    root_span_id = root.context.span_id
    same_parent = (
        detection.parent is not None
        and treatment.parent is not None
        and detection.parent.span_id == root_span_id
        and treatment.parent.span_id == root_span_id
    )
    sequential = detection.end_time <= treatment.start_time
    return same_parent and sequential
