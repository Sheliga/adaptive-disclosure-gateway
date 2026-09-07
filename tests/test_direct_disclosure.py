"""Pins B0 -- Direct (issue #25): the control treatment against which every
other treatment is measured. It sends the input to the external provider
unmodified -- no detection, no policy gate, no transformation -- but must
still produce an auditable ``DisclosureResult``, exactly like B1 and B2
(docs/experimental-design.md's B0->B1 comparison depends on B0 existing at
all).
"""

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
)
from adaptive_disclosure_gateway.transformations.direct_disclosure import DirectDiscloser

SECRET_TEXT = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)


def _request(text: str) -> DisclosureRequest:
    return DisclosureRequest(
        text=text,
        task="summarize personnel record",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )


def test_direct_discloses_the_input_exactly_unchanged():
    result = DirectDiscloser().sanitize(_request(SECRET_TEXT), spans=[])

    assert result.external_payload == SECRET_TEXT
    assert result.status == "allowed"


def test_direct_ignores_supplied_spans_and_still_discloses_the_full_text_unchanged():
    # Same request/result contract as B1/B2 (a shared call site can pass
    # detected spans to any of the three), but B0 must not act on them --
    # unlike B1/B2, no detection participates in producing its payload.
    request = _request(SECRET_TEXT)
    spans = Detector().detect(SECRET_TEXT)

    result = DirectDiscloser().sanitize(request, spans)

    assert result.external_payload == SECRET_TEXT


def test_direct_audit_trail_records_that_no_transformation_was_applied():
    result = DirectDiscloser().sanitize(_request(SECRET_TEXT), spans=[])

    assert result.decisions, "B0 must record an explicit decision, not an empty audit trail"
    assert all(decision.action is DisclosureAction.PRESERVE for decision in result.decisions)

    assert result.transformations, "B0 must record that the text passed through untransformed"
    assert all(
        t.action is DisclosureAction.PRESERVE and t.transformed == t.original == SECRET_TEXT
        for t in result.transformations
    )
