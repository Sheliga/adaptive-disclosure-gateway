from __future__ import annotations

import time

from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    DisclosureResult,
    PolicyDecision,
    SensitiveSpan,
    Transformation,
    Treatment,
)
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer

# Direct (B0): the control treatment every other treatment is measured
# against (issue #25, docs/experimental-design.md's B0->B1 comparison). It
# is deliberately the unsafe baseline: the external payload is the input
# text, unmodified, and no detection, policy or transformation logic
# participates in producing it. Do not "improve" this with any safety
# behavior -- that would destroy its value as a control and silently bias
# every comparison against it.
#
# Stricter isolation than B1: B1 still imports detection.overlap to resolve
# overlapping spans before slicing the text. B0 never slices the text at
# all, so it needs no detection dependency either (see
# tests/test_treatment_isolation.py).

# Sentinel category used for B0's single audit entry: no detection ran, so
# there is no per-category breakdown to report -- only that the whole text
# was disclosed unchanged.
_AUDIT_CATEGORY = "direct_disclosure"


class DirectDiscloser:
    """Direct (B0): sends ``request.text`` to the external provider exactly
    as received.

    Shares the same ``sanitize(request, spans) -> DisclosureResult`` contract
    as ``StaticSanitizer`` (B1) and ``ReversiblePseudonymizer`` (B2) so one
    call site can drive all three treatments over the same case; ``spans``
    is accepted only for that reason and is never read -- B0's payload does
    not depend on detection.

    Still auditable: rather than returning an empty audit trail (which would
    make the audit stage itself a confound between treatments), the result
    records exactly one decision/transformation pair stating that the full
    text was preserved unchanged.
    """

    treatment = Treatment.DIRECT

    # Capability marker consumed by pipeline.py's UnsafeControlTreatment
    # protocol (checked via isinstance, never by comparing treatment.treatment
    # to Treatment.DIRECT -- see tests/test_pipeline.py's structural pins):
    # exempts B0 alone from the shared pipeline's fail-closed check for
    # sensitive content in request.task. True only here -- B1/B2 (and any
    # future non-control treatment) must not carry this attribute, so they
    # stay subject to that check by default.
    unsafe_control_baseline = True

    def sanitize(self, request: DisclosureRequest, spans: list[SensitiveSpan]) -> DisclosureResult:
        del spans  # never read: B0's payload depends only on request.text
        tracer = get_tracer()
        started = time.perf_counter()
        with tracer.start_as_current_span("direct_disclosure.sanitize") as otel_span:
            # Metadata only -- never the payload or the raw text, which for
            # B0 are the same string (see tests/test_telemetry_privacy.py).
            otel_span.set_attribute("treatment", self.treatment.value)
            otel_span.set_attribute("direct_disclosure.blocked", False)
            otel_span.set_attribute("direct_disclosure.duration_ms", elapsed_ms_since(started))

            return DisclosureResult(
                external_payload=request.text,
                decisions=[
                    PolicyDecision(
                        category=_AUDIT_CATEGORY,
                        action=DisclosureAction.PRESERVE,
                        reason=(
                            "B0 direct baseline: no detection or transformation "
                            "applied, the full input is disclosed unchanged"
                        ),
                        allowed_actions=[DisclosureAction.PRESERVE],
                    )
                ],
                transformations=[
                    Transformation(
                        category=_AUDIT_CATEGORY,
                        original=request.text,
                        transformed=request.text,
                        action=DisclosureAction.PRESERVE,
                    )
                ],
                status="allowed",
            )
