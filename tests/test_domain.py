import pytest
from pydantic import ValidationError

from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    GovernanceContext,
    PseudonymScope,
    SensitiveSpan,
    Treatment,
)


def test_governance_context_keeps_policy_version():
    context = GovernanceContext(
        domain="contracts",
        purpose="contract_review",
        requester_role="legal_analyst",
        policy_version="contracts-v1",
    )

    assert context.domain == "contracts"
    assert context.policy_version == "contracts-v1"


def test_disclosure_action_supports_explicit_request_blocking():
    assert DisclosureAction.BLOCK_REQUEST.value == "block_request"


def test_default_requested_pseudonym_scope_is_session():
    context = GovernanceContext(
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
    )

    assert context.requested_pseudonym_scope is PseudonymScope.SESSION


def test_pseudonym_scope_rejects_unknown_values():
    with pytest.raises(ValidationError):
        GovernanceContext(
            domain="hr",
            purpose="team_summary",
            policy_version="hr-v1",
            requested_pseudonym_scope="forever",
        )


# Issue #17: SensitiveSpan.start/end used to be optional, which let a span
# reach the transformation boundary with missing offsets that were then
# silently coerced to 0 -- producing an "allowed" payload that still
# contained the original sensitive value under a nominal REMOVE decision.
# These pin that offsets are now required and structurally validated at
# construction time, so such a span cannot be built at all. Checks that
# depend on the source text (in-bounds `end`, value/offset match) cannot
# live here -- the model has no access to the text -- and are covered at the
# transformation boundary instead (tests/test_b1_sanitizer.py).


def test_sensitive_span_rejects_missing_offsets():
    with pytest.raises(ValidationError):
        SensitiveSpan(category="cpf", value="123.456.789-09")


def test_sensitive_span_rejects_negative_start():
    with pytest.raises(ValidationError):
        SensitiveSpan(category="cpf", value="123.456.789-09", start=-1, end=10)


def test_sensitive_span_rejects_inverted_offsets():
    with pytest.raises(ValidationError):
        SensitiveSpan(category="cpf", value="123.456.789-09", start=10, end=5)


def test_sensitive_span_rejects_zero_length_span():
    with pytest.raises(ValidationError):
        SensitiveSpan(category="cpf", value="123.456.789-09", start=5, end=5)


# T15: Treatment gives the B0-B4 experimental codes semantic names, but the
# values are the frozen identifiers that traceability across docs, cards and
# telemetry depends on (docs/experimental-design.md). This pins each member's
# value against the frozen code, so a careless rename that also touches the
# value would fail here instead of silently breaking that traceability.
def test_treatment_values_are_frozen_experimental_codes():
    assert Treatment.DIRECT.value == "b0"
    assert Treatment.STATIC_SANITIZATION.value == "b1"
    assert Treatment.REVERSIBLE_PSEUDONYMIZATION.value == "b2"
    assert Treatment.TASK_AWARE.value == "b3"
    assert Treatment.POLICY_GOVERNED.value == "b4"
