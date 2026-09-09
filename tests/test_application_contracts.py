"""T20 / issue #28, slice 1: contract-shape pins for ``application/contracts.py``.

These check structural properties of the contract types themselves (field
sets present/absent), not behavior already covered by
``tests/test_application_summaries.py`` or ``tests/test_application_service.py``.
"""

from __future__ import annotations

import dataclasses

from adaptive_disclosure_gateway.application.contracts import (
    DisclosureStrategy,
    SafeGovernanceView,
    list_strategy_options,
    resolve_treatment,
    safe_governance_view,
)
from adaptive_disclosure_gateway.domain import GovernanceContext, PseudonymScope, Treatment


def test_recommended_strategy_resolves_to_policy_governed():
    assert resolve_treatment(DisclosureStrategy.RECOMMENDED) is Treatment.POLICY_GOVERNED


def test_every_explicit_strategy_maps_to_its_own_named_treatment():
    assert resolve_treatment(DisclosureStrategy.DIRECT) is Treatment.DIRECT
    assert (
        resolve_treatment(DisclosureStrategy.STATIC_SANITIZATION) is Treatment.STATIC_SANITIZATION
    )
    assert (
        resolve_treatment(DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION)
        is Treatment.REVERSIBLE_PSEUDONYMIZATION
    )
    assert resolve_treatment(DisclosureStrategy.TASK_AWARE) is Treatment.TASK_AWARE
    assert resolve_treatment(DisclosureStrategy.POLICY_GOVERNED) is Treatment.POLICY_GOVERNED


def test_disclosure_strategy_reuses_the_frozen_b0_b4_codes_verbatim():
    """CLAUDE.md: b0-b4 are frozen identifiers that must never change --
    DisclosureStrategy must reuse Treatment's own values, never mint new
    ones that happen to look similar.
    """
    assert DisclosureStrategy.DIRECT.value == Treatment.DIRECT.value == "b0"
    assert DisclosureStrategy.POLICY_GOVERNED.value == Treatment.POLICY_GOVERNED.value == "b4"


def test_safe_governance_view_has_no_requester_id_or_lifecycle_identifier_field_at_all():
    """Not just unset -- the type itself must carry no such field, so a
    future careless edit cannot add one back and forget to strip it before
    returning a result to the caller.
    """
    field_names = {f.name for f in dataclasses.fields(SafeGovernanceView)}
    forbidden = {"requester_id", "session_id", "document_id", "request_id"}
    assert not (field_names & forbidden), field_names & forbidden


def test_safe_governance_view_projects_only_the_safe_fields():
    context = GovernanceContext(
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
        requester_role="hr_analyst",
        requester_id="analyst-42",
        session_id="session-99",
        requested_pseudonym_scope=PseudonymScope.SESSION,
    )

    view = safe_governance_view(context)

    assert view.domain == "hr"
    assert view.purpose == "team_summary"
    assert view.policy_version == "hr-v1"
    assert view.provider_class == "external_llm"
    assert view.requester_role == "hr_analyst"
    assert view.requested_pseudonym_scope == PseudonymScope.SESSION
    # No sensitive/lifecycle identifier value leaks through serialization.
    dumped = str(dataclasses.asdict(view))
    assert "analyst-42" not in dumped
    assert "session-99" not in dumped


def test_list_strategy_options_covers_every_strategy_exactly_once():
    options = list_strategy_options()

    assert {option.strategy for option in options} == set(DisclosureStrategy)
    assert len(options) == len(set(DisclosureStrategy))


def test_list_strategy_options_marks_only_recommended_as_recommended():
    options = list_strategy_options()

    recommended = [option for option in options if option.recommended]
    assert len(recommended) == 1
    assert recommended[0].strategy is DisclosureStrategy.RECOMMENDED
    assert recommended[0].treatment is Treatment.POLICY_GOVERNED


def test_list_strategy_options_each_treatment_matches_resolve_treatment():
    for option in list_strategy_options():
        assert option.treatment is resolve_treatment(option.strategy)
