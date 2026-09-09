"""T20 / issue #28, slice 2: ``application/requests.py`` -- the pure
governance-merge helper behind ``DisclosureApplicationService.build_application_request``.

``ContentSourceError``/``MissingTaskError`` themselves are exercised through
the service method (``tests/test_application_service.py``), which is the
only place they can actually be raised end to end; this file pins the pure
merge function in isolation.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.application.contracts import GovernanceOverrides
from adaptive_disclosure_gateway.application.requests import apply_example_governance_defaults
from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.models import TaskFamily
from adaptive_disclosure_gateway.domain import PseudonymScope

EXAMPLE = CorpusCaseInput(
    sample_id="example_001",
    text="Employee: Ana Souza\n",
    task="Summarize the department.",
    task_family=TaskFamily.DEPARTMENT_AGGREGATION_WITHOUT_IDENTITY,
    domain="hr",
    purpose="team_summary",
    requester_role="hr_analyst",
    provider_class="fake",
    policy_version="hr-v1",
    requested_pseudonym_scope=PseudonymScope.SESSION,
)


def test_example_defaults_fill_every_unset_scenario_field():
    merged = apply_example_governance_defaults(EXAMPLE, GovernanceOverrides())

    assert merged.domain == "hr"
    assert merged.purpose == "team_summary"
    assert merged.policy_version == "hr-v1"
    assert merged.requester_role == "hr_analyst"
    assert merged.requested_pseudonym_scope == PseudonymScope.SESSION


def test_provider_class_is_never_populated_from_the_example():
    """An example describes a *scenario*; which provider class a request may
    egress to is a *deployment* fact owned by whoever configured the
    service's Provider.

    Taking it from the example made every prepared example fail closed at
    the provider boundary (the corpus names ``external_llm``, the demo
    provider declares its own class), so the guided flow returned no answer
    at all -- see
    ``tests/test_application_service.py::test_a_prepared_example_actually_reaches_the_configured_provider``
    for the end-to-end pin.
    """
    merged = apply_example_governance_defaults(EXAMPLE, GovernanceOverrides())

    assert merged.provider_class is None


def test_explicit_caller_override_wins_over_the_example_default():
    caller_overrides = GovernanceOverrides(purpose="salary_analysis")

    merged = apply_example_governance_defaults(EXAMPLE, caller_overrides)

    assert merged.purpose == "salary_analysis"
    # Untouched fields still fall back to the example's own values.
    assert merged.domain == "hr"


def test_lifecycle_identifiers_are_never_populated_from_the_example():
    """domain/purpose/etc. may come from the example; requester_id and every
    lifecycle identifier never do -- those belong to the caller/deployer,
    not to a shared demo example.
    """
    example_with_identifiers = EXAMPLE.model_copy(
        update={
            "requester_id": "example-requester",
            "session_id": "example-session",
            "document_id": "example-document",
            "request_id": "example-request",
        }
    )

    merged = apply_example_governance_defaults(example_with_identifiers, GovernanceOverrides())

    assert merged.requester_id is None
    assert merged.session_id is None
    assert merged.document_id is None
    assert merged.request_id is None


def test_no_updates_returns_the_same_overrides_object_when_all_fields_already_set():
    fully_set = GovernanceOverrides(
        domain="finance",
        purpose="audit",
        policy_version="fin-v1",
        requester_role="auditor",
        provider_class="external_llm",
        requested_pseudonym_scope=PseudonymScope.REQUEST,
    )

    merged = apply_example_governance_defaults(EXAMPLE, fully_set)

    assert merged is fully_set
