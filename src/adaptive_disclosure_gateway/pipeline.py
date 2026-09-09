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
    DisclosureAction,
    DisclosureRequest,
    DisclosureResult,
    GovernanceContext,
    PolicyDecision,
    SensitiveSpan,
    Treatment,
)
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer
from adaptive_disclosure_gateway.providers import (
    DEFAULT_TIMEOUT_SECONDS,
    Provider,
    ProviderError,
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


@runtime_checkable
class UnsafeControlTreatment(Protocol):
    """Capability marker for a treatment that is an intentionally unsafe raw
    disclosure control -- today only the B0 -- Direct baseline (see
    ``transformations/direct_disclosure.py``'s module docstring for why
    "improving" it would bias every comparison against it).

    This is the exemption from the task-inspection fail-closed check below:
    every other treatment's ``sanitize`` contract only ever inspects
    ``request.text`` (see the module docstring's identifier-contract note),
    so a sensitive value that exists *only* in ``request.task`` used to
    reach the provider untouched. The fix runs the same ``Detector`` over
    ``request.task`` and fails the whole request closed if it detects
    anything -- but the unsafe control baseline must keep sending
    ``request.task`` completely raw, exactly like it does ``request.text``,
    or it would stop being a valid experimental control.

    Checked with ``isinstance``, exactly like ``ReconstructingTreatment``
    above: a capability check on the treatment object, never a branch keyed
    to a specific ``Treatment`` enum member (see
    ``tests/test_pipeline.py::test_pipeline_call_site_never_branches_on_which_treatment_is_running``,
    and the regression pin at
    ``tests/test_pipeline.py::test_b0_direct_still_sends_a_sensitive_task_to_the_provider_unchanged_as_the_unsafe_control``).
    """

    unsafe_control_baseline: bool


@dataclass(frozen=True)
class ExecutionResult:
    """Everything one run of one case through one treatment produced.

    ``provider_response`` and ``reconstructed_text`` are ``None`` whenever
    the corresponding stage did not run -- a blocked request never reaches
    a provider, and a treatment without reconstruction capability never
    produces reconstructed text. ``audit`` is always present: even a
    blocked request gets a full structural audit record (see
    ``adaptive_disclosure_gateway.audit``).

    ``spans`` are the spans the detector actually returned over
    ``request.text`` during *this* run -- the same list the treatment's own
    ``sanitize`` was handed. Carried here (T20 / issue #28) so a consumer
    that needs both halves of the decision phase can read them off the
    result it already has, instead of re-running detection/sanitization a
    second time and then arguing that the second run must have agreed with
    the first. A caller that wants the decision phase *without* a provider
    call calls :func:`decide_disclosure` directly instead.
    """

    disclosure_result: DisclosureResult
    spans: list[SensitiveSpan]
    provider_response: ProviderResponse | None
    reconstructed_text: str | None
    audit: AuditRecord


def _blocked_for_sensitive_task(task_spans: list[SensitiveSpan]) -> DisclosureResult:
    """Fail-closed result for a request whose ``task`` -- not its ``text`` --
    carries sensitive content.

    Every treatment's ``sanitize(request, spans)`` contract only ever
    inspects ``request.text``: ``spans`` are always spans detected over
    ``request.text``, never over ``request.task``. So a sensitive value that
    exists *only* in the task previously sailed straight through to
    ``ProviderRequest.task`` untouched, for every treatment that reaches
    ``invoke_provider`` (B1, B2 -- see ``UnsafeControlTreatment`` above for
    why B0 is deliberately exempt).

    Blocking, not silently sanitizing the task, is the deliberate choice
    here: a task carrying sensitive data is a governance violation (the
    caller built a prompt out of data that should have gone through
    disclosure control, not scaffolding held constant across treatments per
    docs/experimental-design.md), and blocking is the defensible fail-closed
    reading -- the same posture this codebase already takes for a malformed
    span or an unresolvable pseudonym scope, rather than silently rewriting
    a field this pipeline was never asked to transform.
    """
    categories = sorted({span.category for span in task_spans})
    decisions = [
        PolicyDecision(
            category=category,
            action=DisclosureAction.BLOCK_REQUEST,
            reason=(
                "request.task contains detected sensitive content in this "
                "category; the shared pipeline fails the whole request "
                "closed rather than silently sanitizing the task -- only "
                "request.text goes through a treatment's own sanitize() "
                "detection/action mapping"
            ),
            allowed_actions=[DisclosureAction.BLOCK_REQUEST],
        )
        for category in categories
    ]
    return DisclosureResult(
        external_payload="",
        decisions=decisions,
        transformations=[],
        status="blocked",
    )


@dataclass(frozen=True)
class DisclosureDecision:
    """What the decision phase of one case produced, before any provider
    call: the spans the detector actually returned over ``request.text`` and
    the treatment's own ``DisclosureResult`` -- already including the
    fail-closed task check below.

    Extracted (T20 / issue #28, slice 1) so a future preview use case (no
    provider call at all) can run exactly this phase without duplicating it:
    ``run_disclosure_case`` below now calls :func:`decide_disclosure` itself
    rather than inlining this logic a second time. This is *not* a new
    stage: it is the same detect -> sanitize -> task-check sequence that has
    always run first inside ``run_disclosure_case``'s own span, moved
    verbatim into its own function.
    """

    spans: list[SensitiveSpan]
    result: DisclosureResult


def decide_disclosure(
    treatment: DisclosureTreatment,
    request: DisclosureRequest,
    *,
    detector: Detector | None = None,
) -> DisclosureDecision:
    """Run the decision phase alone: detect over ``request.text``, call
    ``treatment.sanitize(request, spans)``, then the fail-closed check that
    re-detects over ``request.task`` and blocks the whole request (except
    for ``UnsafeControlTreatment`` -- see its docstring) if it finds
    anything there.

    CRITICAL: this function must never open an OpenTelemetry span of its
    own. ``experiments/stage_timing.py`` depends on ``detection.detect`` and
    ``<treatment>.sanitize`` being *direct children* of the
    ``pipeline.run_disclosure_case`` span (siblings of each other, neither
    nested inside the other, nor inside anything else). ``run_disclosure_case``
    calls this function from inside its own span for exactly that reason;
    a caller that calls this function with no span of its own open (e.g. a
    preview use case) gets ``detection.detect``/``<treatment>.sanitize`` as
    root spans instead -- see
    ``tests/test_pipeline.py::test_decide_disclosure_opens_no_span_of_its_own``.
    """
    active_detector = detector or Detector()
    spans = active_detector.detect(request.text)
    result = treatment.sanitize(request, spans)

    # A sensitive value can exist only in request.task, which no
    # treatment's sanitize() ever inspects. Run the same Detector over
    # it and fail the whole request closed if it finds anything -- but
    # never for the unsafe control baseline, which must keep sending
    # request.task completely raw (see UnsafeControlTreatment above).
    if result.status == "allowed" and not isinstance(treatment, UnsafeControlTreatment):
        task_spans = active_detector.detect(request.task)
        if task_spans:
            result = _blocked_for_sensitive_task(task_spans)

    return DisclosureDecision(spans=spans, result=result)


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

        decision = decide_disclosure(treatment, request, detector=detector)
        spans = decision.spans
        result = decision.result

        provider_response: ProviderResponse | None = None
        reconstructed_text: str | None = None
        provider_class_used: str | None = None
        provider_attempted = False
        provider_failure_kind: str | None = None

        if result.status == "allowed":
            provider_request = ProviderRequest(payload=result.external_payload, task=request.task)
            provider_class_used = provider.provider_class
            try:
                provider_response = invoke_provider(
                    provider,
                    provider_request,
                    expected_provider_class=request.context.provider_class,
                    timeout=timeout,
                )
            except ProviderError as exc:
                # Fail closed, observably: a provider error or timeout must
                # not crash this call with no audit record at all. Record
                # that the provider failed, by failure *kind* only (the
                # exception's class name) -- never its message, which a
                # third-party provider client could have populated with
                # request content (invoke_provider's own docstring already
                # breaks that chain with `from None`; this call site must
                # not resurface it either). No fallback to B0 -- Direct:
                # provider_response/reconstructed_text simply stay
                # None/unset.
                #
                # Whether the audit should say the provider was "called" is
                # read from the exception itself (``provider_invoked``) --
                # the one fact only ``invoke_provider`` knows for certain,
                # since it is the only code that knows whether
                # ``provider.generate`` was actually submitted before this
                # failure happened. This deliberately does not special-case
                # ``ProviderClassMismatchError`` by isinstance: any future
                # pre-flight check invoke_provider grows before the
                # ``generate`` call carries the same attribute automatically,
                # without this call site needing to change.
                provider_attempted = exc.provider_invoked
                provider_failure_kind = type(exc).__name__
            else:
                provider_attempted = True
                if isinstance(treatment, ReconstructingTreatment):
                    reconstructed_text = treatment.reconstruct(
                        provider_response.text, result, request.context
                    )

        # Metadata only -- never the payload, the raw text, or any
        # reconstructed content.
        otel_span.set_attribute("pipeline.status", result.status)
        otel_span.set_attribute("pipeline.provider_called", provider_attempted)
        otel_span.set_attribute("pipeline.provider_failed", provider_failure_kind is not None)
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
            provider_attempted=provider_attempted,
            provider_failure_kind=provider_failure_kind,
            capture_raw_values_for_controlled_experiment=(
                capture_raw_values_for_controlled_experiment
            ),
        )

        return ExecutionResult(
            disclosure_result=result,
            spans=spans,
            provider_response=provider_response,
            reconstructed_text=reconstructed_text,
            audit=audit,
        )
