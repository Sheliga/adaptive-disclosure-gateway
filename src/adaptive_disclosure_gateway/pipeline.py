"""The single execution path every B0 -- Direct / B1 -- Static Sanitization /
B2 -- Reversible Pseudonymization comparison runs a case through (issue #26
/ T19).

Wires together, in one call, exactly the stages README.md's core flow and
audit model name:

    detect
    -> sanitize (whichever treatment was supplied)
    -> invoke_provider, unless the result is blocked
    -> reconstruct, if the treatment supports it
    -> build the structural audit record

No branch in ``run_disclosure_case`` is keyed on *which* treatment is
running. It only branches on outcomes every treatment already exposes
through the shared ``sanitize(request, spans) -> DisclosureResult`` contract:
``DisclosureResult.status`` (blocked vs. allowed) and whether the supplied
treatment object happens to implement ``reconstruct`` at all -- a capability
check, not a per-treatment special case, so a future B3/B4 treatment that
also implements ``reconstruct`` is handled identically without editing this
module. ``tests/test_pipeline.py`` pins this structurally: the call site may
not import a concrete treatment class, and may not compare against a
specific ``Treatment`` enum member.

Identifier contract (explicit, load-bearing): this function never invents,
defaults, or infers a pseudonym-scope lifecycle identifier
(``request_id``/``document_id``/``session_id``) on the caller's behalf, and
it does not modify ``request.context`` in any way before handing it to the
treatment. A treatment that resolves a scope needing an identifier the
caller's ``GovernanceContext`` does not carry fails closed by its own
contract (see ``reversible_pseudonymization._scope_key``) -- that is correct
disclosure control. If a case were blocked only because *this* function
forgot to pass an identifier the caller *did* supply, that would be a wiring
artifact, not disclosure control; supplying the right identifier for the
policy-resolved scope is entirely the caller's responsibility, pinned by
``tests/test_pipeline.py::test_pipeline_blocks_when_the_caller_omits_the_identifier_the_resolved_scope_needs``
and its sibling proving the same case succeeds once the identifier is
supplied.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from adaptive_disclosure_gateway.audit import AuditRecord, build_audit_record
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureRequest,
    DisclosureResult,
    GovernanceContext,
    SensitiveSpan,
    Treatment,
)
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer
from adaptive_disclosure_gateway.providers import (
    DEFAULT_TIMEOUT_SECONDS,
    Provider,
    ProviderRequest,
    ProviderResponse,
    invoke_provider,
)


class DisclosureTreatment(Protocol):
    """The shape every B0-B4 treatment implements: a ``treatment`` label
    (for audit purposes only -- never branched on) and the shared
    ``sanitize`` contract. Not ``runtime_checkable``: nothing here ever
    needs an ``isinstance`` check against this protocol, only against
    ``ReconstructingTreatment`` below.
    """

    treatment: Treatment

    def sanitize(
        self, request: DisclosureRequest, spans: list[SensitiveSpan]
    ) -> DisclosureResult: ...


@runtime_checkable
class ReconstructingTreatment(Protocol):
    """A treatment that can locally reconstruct a provider response --
    currently only B2 -- Reversible Pseudonymization. Checked with
    ``isinstance`` at the call site so reconstruction is driven by
    *capability*, not by which treatment this happens to be.
    """

    def reconstruct(
        self, response_text: str, result: DisclosureResult, context: GovernanceContext
    ) -> str: ...


@dataclass(frozen=True)
class ExecutionResult:
    """Everything one run of one case through one treatment produced.

    ``provider_response`` and ``reconstructed_text`` are ``None`` whenever
    the corresponding stage did not run -- a blocked request never reaches
    a provider, and a treatment without reconstruction capability never
    produces reconstructed text. ``audit`` is always present: even a
    blocked request gets a full structural audit record (see
    ``adaptive_disclosure_gateway.audit``).
    """

    disclosure_result: DisclosureResult
    provider_response: ProviderResponse | None
    reconstructed_text: str | None
    audit: AuditRecord


def run_disclosure_case(
    treatment: DisclosureTreatment,
    request: DisclosureRequest,
    provider: Provider,
    *,
    detector: Detector | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    capture_raw_values_for_controlled_experiment: bool = False,
) -> ExecutionResult:
    """Run ``request`` through ``treatment`` and, unless it is blocked,
    through ``provider`` via ``invoke_provider`` -- and, if ``treatment``
    supports it, through local reconstruction of the provider's response.

    Every treatment receives the same detected spans (via the same
    ``Detector``), regardless of whether it reads them: B0 discards them,
    B1/B2 consume them. This mirrors the pre-existing shared
    ``sanitize(request, spans)`` contract exactly, so plugging in B3/B4
    later requires no change here.

    ``expected_provider_class`` for ``invoke_provider`` comes from
    ``request.context.provider_class`` -- the value policy already
    evaluates against (see ``providers.invoke_provider``'s docstring) --
    never from the treatment or the provider itself.

    See the module docstring for the pseudonym-scope identifier contract:
    this function passes ``request.context`` through unchanged and invents
    nothing.
    """
    tracer = get_tracer()
    started = time.perf_counter()
    with tracer.start_as_current_span("pipeline.run_disclosure_case") as otel_span:
        otel_span.set_attribute("treatment", treatment.treatment.value)

        active_detector = detector or Detector()
        spans = active_detector.detect(request.text)
        result = treatment.sanitize(request, spans)

        provider_response: ProviderResponse | None = None
        reconstructed_text: str | None = None
        provider_class_used: str | None = None

        if result.status == "allowed":
            provider_request = ProviderRequest(payload=result.external_payload, task=request.task)
            provider_response = invoke_provider(
                provider,
                provider_request,
                expected_provider_class=request.context.provider_class,
                timeout=timeout,
            )
            provider_class_used = provider.provider_class

            if isinstance(treatment, ReconstructingTreatment):
                reconstructed_text = treatment.reconstruct(
                    provider_response.text, result, request.context
                )

        # Metadata only -- never the payload, the raw text, or any
        # reconstructed content.
        otel_span.set_attribute("pipeline.status", result.status)
        otel_span.set_attribute("pipeline.provider_called", provider_response is not None)
        otel_span.set_attribute("pipeline.reconstruction_attempted", reconstructed_text is not None)
        otel_span.set_attribute("pipeline.duration_ms", elapsed_ms_since(started))

        audit = build_audit_record(
            request=request,
            spans=spans,
            result=result,
            treatment=treatment.treatment,
            provider_response=provider_response,
            provider_class=provider_class_used,
            reconstructed_text=reconstructed_text,
            capture_raw_values_for_controlled_experiment=(
                capture_raw_values_for_controlled_experiment
            ),
        )

        return ExecutionResult(
            disclosure_result=result,
            provider_response=provider_response,
            reconstructed_text=reconstructed_text,
            audit=audit,
        )
