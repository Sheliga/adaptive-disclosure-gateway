import pytest
from pydantic import ValidationError

from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    GovernanceContext,
    PseudonymScope,
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
