from __future__ import annotations

import os

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
