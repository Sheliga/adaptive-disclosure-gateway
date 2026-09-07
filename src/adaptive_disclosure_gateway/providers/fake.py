from __future__ import annotations

import hashlib
from typing import Any, ClassVar

from .base import ProviderRequest, ProviderResponse, count_transmitted_bytes


class FakeProvider:
    """Deterministic, offline stand-in for an external LLM provider.

    Used as the default provider across Milestone 1's B0 -- Direct through
    B2 -- Reversible Pseudonymization (docs/implementation-status.md,
    docs/experimental-design.md's "Provider model, snapshot and decoding
    configuration" held-constant requirement) so that a comparison between
    treatments is never confounded by external model variance, and so tests
    never require network access.

    Determinism: ``generate`` is a pure function of ``request.payload`` and
    ``request.task`` -- the same request always produces the exact same
    response text, byte-for-byte, with no randomness, clock or process
    state involved. ``model_id``, ``model_snapshot`` and ``decoding_config``
    are fixed class attributes, so two independently constructed
    ``FakeProvider`` instances -- as two separate calls in an experiment run
    would use -- report identical reproducibility metadata.
    """

    provider_class = "fake"

    model_id: ClassVar[str] = "fake-provider"
    model_snapshot: ClassVar[str] = "fake-provider-2026-09-07"
    decoding_config: ClassVar[dict[str, Any]] = {
        "temperature": 0.0,
        "max_tokens": 512,
        "sampling": "greedy",
    }

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        digest = hashlib.sha256(f"{request.task}\x1f{request.payload}".encode()).hexdigest()[:16]
        text = (
            f"[fake:{digest}] acknowledged task {request.task!r} over {len(request.payload)} chars"
        )

        return ProviderResponse(
            text=text,
            model_id=self.model_id,
            model_snapshot=self.model_snapshot,
            decoding_config=dict(self.decoding_config),
            transmitted_bytes=count_transmitted_bytes(request.payload),
        )
