from adaptive_disclosure_gateway.domain import DisclosureAction, GovernanceContext


def test_governance_context_keeps_policy_version():
    context = GovernanceContext(
        domain="contracts",
        purpose="contract_review",
        requester_role="legal_analyst",
        policy_version="contracts-v1",
    )

    assert context.domain == "contracts"
    assert context.policy_version == "contracts-v1"


def test_disclosure_action_supports_policy_denial():
    assert DisclosureAction.DENY.value == "deny"
