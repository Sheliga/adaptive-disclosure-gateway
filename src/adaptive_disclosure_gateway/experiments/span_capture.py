"""Per-case OTel span capture for T10's experiment runner.

``pipeline.run_disclosure_case`` is run for real -- never duplicated or
reimplemented -- and its spans are captured with a fresh, function-scoped
``InMemorySpanExporter``/``TracerProvider`` pair, installed and torn down
exactly the way ``tests/conftest.py``'s ``recorded_spans`` fixture already
does for the rest of this codebase's test suite: swap the private
``trace._TRACER_PROVIDER`` global for the duration of one call, then restore
whatever was installed before. Using the same technique here (rather than
inventing a second one) is what lets the runner execute inside the test
suite without corrupting any other test's tracer provider, and is also
exactly why the global must be *restored*, not merely replaced -- a second
call from inside a `recorded_spans`-using test would otherwise clobber that
fixture's own installed provider.
"""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest
from adaptive_disclosure_gateway.pipeline import (
    DisclosureTreatment,
    ExecutionResult,
    run_disclosure_case,
)
from adaptive_disclosure_gateway.providers import DEFAULT_TIMEOUT_SECONDS, Provider


def run_case_with_span_capture(
    treatment: DisclosureTreatment,
    request: DisclosureRequest,
    provider: Provider,
    *,
    detector: Detector | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    capture_raw_values_for_controlled_experiment: bool = False,
) -> tuple[ExecutionResult, Sequence[ReadableSpan]]:
    """Run ``request`` through ``run_disclosure_case`` and return both the
    real ``ExecutionResult`` and every OTel span emitted while it ran.

    Installs a private tracer provider only for the duration of this call
    (never process-wide), and always restores the previous global provider
    in a ``finally`` block -- safe to call from inside the pytest suite
    itself, alongside ``tests/conftest.py``'s own ``recorded_spans`` fixture.
    """
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))

    previous_provider = trace._TRACER_PROVIDER
    trace._TRACER_PROVIDER = tracer_provider
    try:
        result = run_disclosure_case(
            treatment,
            request,
            provider,
            detector=detector,
            timeout=timeout,
            capture_raw_values_for_controlled_experiment=(
                capture_raw_values_for_controlled_experiment
            ),
        )
    finally:
        trace._TRACER_PROVIDER = previous_provider
        tracer_provider.shutdown()

    return result, exporter.get_finished_spans()
