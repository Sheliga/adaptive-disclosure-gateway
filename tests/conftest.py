import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def recorded_spans():
    """In-memory OTel spans recorded during a test.

    A fresh exporter and TracerProvider are created for every test that asks
    for this fixture, and installed as the *global* OTel tracer provider only
    for the lifetime of that test. This is deliberately function-scoped
    (rather than the previous module-level singleton shared by the whole
    session): with a single shared exporter, any test that produces spans
    without requesting this fixture (most tests do, via Detector/StaticSanitizer/
    ReversiblePseudonymizer) leaves them sitting in the shared buffer for
    whatever runs next, so a test's assertions could observe spans that are
    not its own. Giving each test its own provider/exporter -- and restoring
    whatever was previously installed afterwards -- makes that impossible
    regardless of what other tests do or the order they run in.

    ``opentelemetry.trace.set_tracer_provider`` intentionally only accepts the
    first call per process (repeats are logged and ignored), so it cannot be
    used here; the private ``_TRACER_PROVIDER`` global is swapped directly
    instead, which is the standard approach OTel's own test suites use for
    exactly this kind of per-test provider isolation.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    previous_provider = trace._TRACER_PROVIDER
    trace._TRACER_PROVIDER = provider
    try:
        yield exporter
    finally:
        trace._TRACER_PROVIDER = previous_provider
        provider.shutdown()
