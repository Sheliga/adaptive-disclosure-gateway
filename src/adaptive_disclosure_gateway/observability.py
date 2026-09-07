from __future__ import annotations

import os
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = "adaptive-disclosure-gateway"


def configure_telemetry(
    service_name: str = SERVICE_NAME,
    endpoint: str | None = None,
) -> trace.Tracer:
    """Configure OTLP tracing.

    Trace attributes must contain metadata only. Raw input, reconstructed output,
    vault values and other sensitive content are intentionally outside this API.
    """
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))

    otlp_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(SERVICE_NAME)


def elapsed_ms_since(started: float) -> float:
    """Elapsed milliseconds since ``started`` (a ``time.perf_counter()`` reading),
    rounded to microsecond precision for use as a span attribute.

    ``time.perf_counter()`` deltas are binary floats whose ``str()`` can carry
    ~17 significant digits of measurement noise. Left unrounded, that noise is
    effectively random digits and can -- purely by coincidence -- contain the
    same digit sequence as an unrelated sensitive value (e.g. a duration of
    ``0.0850000069476664`` ms contains the substring "8500"), which is not an
    actual leak but will intermittently trip a naive "value not in span" check.
    Rounding to 3 decimal places keeps millisecond timing useful while
    guaranteeing no 4-digit run can appear on either side of the decimal
    point for any realistic (sub-second) duration.
    """
    return round((time.perf_counter() - started) * 1000, 3)
