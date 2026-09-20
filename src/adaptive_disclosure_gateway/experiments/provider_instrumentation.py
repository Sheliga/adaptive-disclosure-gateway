"""Provider-call timing/volume instrumentation for T10's experiment runner.

``pipeline.run_disclosure_case`` has no span around the provider invocation
(by design -- see docs/experimental-design.md and the module docstring of
``pipeline.py``: the provider boundary is intentionally the narrowest
possible surface). Rather than adding one to production code, this module
wraps *any* ``Provider`` in a runner-only delegate that still satisfies the
``Provider`` protocol exactly (``provider_class`` attribute, ``generate``
method) and records latency/volume metadata around each call.

This is runner code: it does not change what a provider receives or
returns, and never inspects the payload for content -- only its length and
elapsed wall-clock time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from adaptive_disclosure_gateway.observability import elapsed_ms_since
from adaptive_disclosure_gateway.providers import (
    Provider,
    ProviderRequest,
    ProviderResponse,
    count_transmitted_bytes,
)


@dataclass(frozen=True)
class ProviderCallMetrics:
    """Metadata about one ``generate()`` call -- never the payload, task, or
    response text itself, only lengths and identifiers (CLAUDE.md's no-leak
    invariant).

    ``payload_bytes`` is the disclosure-controlled payload volume (issue #8's
    "separate disclosure-controlled payload volume from prompt/task
    scaffolding"); ``total_request_bytes`` additionally includes ``task``,
    giving the total-provider-request-volume metric the same issue allows
    reporting alongside it.
    """

    latency_ms: float
    payload_bytes: int
    task_bytes: int
    total_request_bytes: int
    response_bytes: int
    model_id: str
    model_snapshot: str
    # Provider-reported token usage, carried straight through from
    # ``ProviderResponse`` (T22 / issue #30) so the runner schema records the
    # provider API's own numbers rather than a heuristic estimate. ``None``
    # means the provider reported no usage at all -- which is exactly the
    # case under ``FakeProvider`` (no tokenizer, no usage accounting; see
    # docs/research/post-pilot-protocol-v1.md section 9.2) -- and is a
    # different claim from ``0``. There is deliberately no cost field: this
    # codebase records usage and no pricing, so a consumer reports cost as
    # unavailable instead of deriving one from a table that would silently
    # go stale.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class TimingProviderDelegate:
    """Wraps a ``Provider`` and records one ``ProviderCallMetrics`` per
    ``generate()`` call it forwards.

    Satisfies the ``Provider`` protocol itself (duck-typed: ``invoke_provider``
    never does an ``isinstance`` check against it), so it is a drop-in
    replacement for the wrapped provider from ``pipeline.run_disclosure_case``'s
    point of view. A fresh instance should be constructed per case execution
    so ``last_call`` unambiguously reflects that one case's call.
    """

    def __init__(self, wrapped: Provider) -> None:
        self._wrapped = wrapped
        self.provider_class = wrapped.provider_class
        self.last_call: ProviderCallMetrics | None = None

    @property
    def native_timeout_seconds(self) -> float | None:
        """Passes through the wrapped provider's native transport timeout,
        if it declares one (T22 / issue #30, review blocker 2), so
        ``providers.caller_timeout_for_provider`` still derives the correct
        caller-side deadline even when it is handed an already-wrapped
        delegate rather than the bare provider.
        """
        return getattr(self._wrapped, "native_timeout_seconds", None)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        started = time.perf_counter()
        response = self._wrapped.generate(request)
        latency_ms = elapsed_ms_since(started)
        payload_bytes = count_transmitted_bytes(request.payload)
        task_bytes = len(request.task.encode("utf-8"))
        self.last_call = ProviderCallMetrics(
            latency_ms=latency_ms,
            payload_bytes=payload_bytes,
            task_bytes=task_bytes,
            total_request_bytes=payload_bytes + task_bytes,
            response_bytes=len(response.text.encode("utf-8")),
            model_id=response.model_id,
            model_snapshot=response.model_snapshot,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_creation_input_tokens=response.cache_creation_input_tokens,
            cache_read_input_tokens=response.cache_read_input_tokens,
        )
        return response
