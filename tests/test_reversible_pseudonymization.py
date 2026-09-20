"""Pins issue #3's acceptance criteria for Reversible Pseudonymization (B2):
stable pseudonyms per scope, no original/vault content in the external
payload, correct round-trip reconstruction (including a multi-entity
contract example), collision handling (covered at the vault level in
tests/test_vault.py) and policy-blockable reconstruction.
"""

from pathlib import Path

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
    PseudonymScope,
    SensitiveSpan,
)
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations import ReversiblePseudonymizer
from adaptive_disclosure_gateway.vault import InMemoryVault

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"


def _request(text: str, **context_overrides) -> DisclosureRequest:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "requester_role": "hr_analyst",
        "requester_id": "u1",
        "policy_version": "hr-v1",
        # hr_analyst's ceiling is SESSION (configs/policies/hr-v1.yaml) and
        # the model default requested scope is also SESSION, so most cases
        # below resolve to SESSION and therefore need a session_id (issue
        # #23 / T16 removed the old requester-identity fallback). Tests that
        # exercise a different resolved scope, or the missing-identifier
        # fail-closed path, override this explicitly.
        "session_id": "s1",
    }
    values.update(context_overrides)
    return DisclosureRequest(text=text, task="summarize", context=GovernanceContext(**values))


def _employee_name_pseudonym(result) -> str:
    return next(t.transformed for t in result.transformations if t.category == "employee_name")


def _pseudonymizer() -> ReversiblePseudonymizer:
    return ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )


def test_pseudonymize_action_replaces_value_and_does_not_leak_original():
    text = "Employee: Ana Souza\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = _pseudonymizer().sanitize(request, spans)

    assert "Ana Souza" not in result.external_payload
    transformation = next(t for t in result.transformations if t.category == "employee_name")
    assert transformation.action is DisclosureAction.PSEUDONYMIZE
    assert transformation.transformed is not None
    assert transformation.transformed in result.external_payload
    assert result.reconstruction_required is True


def test_medical_data_blocks_entire_request_and_suppresses_other_spans():
    text = "Employee: Ana Souza\nMedical notes: Reports chronic migraine.\n"
    request = _request(text)
    spans = Detector().detect(text)

    result = _pseudonymizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "Ana Souza" not in result.external_payload


def test_unmapped_category_fails_closed_instead_of_leaking():
    request = _request("some free text value here")
    spans = [SensitiveSpan(category="unknown_category", value="value here", start=15, end=25)]

    result = _pseudonymizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert "value here" not in result.external_payload


def test_unconfigured_generalize_category_fails_closed_instead_of_disclosing(monkeypatch):
    import adaptive_disclosure_gateway.transformations.reversible_pseudonymization as b2_module

    monkeypatch.setitem(b2_module.ACTIONS, "bonus", DisclosureAction.GENERALIZE)
    text = "Bonus: R$ 500.00 was paid.\n"
    request = _request(text)
    spans = [SensitiveSpan(category="bonus", value="R$ 500.00", start=7, end=16)]

    result = _pseudonymizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert "500.00" not in result.external_payload


def test_configured_generalize_category_with_unparseable_value_fails_closed_not_raises():
    # Issue #16 (2b): "salary" *is* configured for GENERALIZE, but a free-text
    # value the strategy cannot parse must block the request -- not let
    # GeneralizationError escape mid-slice with a half-built payload.
    text = "Salary: to be negotiated later\n"
    request = _request(text)
    spans = Detector().detect(text)
    assert any(s.category == "salary" for s in spans)  # detected, just unparseable

    result = _pseudonymizer().sanitize(request, spans)

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "to be negotiated later" not in result.external_payload


def test_span_with_missing_offsets_bypassing_model_is_blocked_not_leaked():
    text = "CPF: 123.456.789-09 recorded."
    request = _request(text)
    malformed = SensitiveSpan.model_construct(
        category="cpf", value="123.456.789-09", start=None, end=None, confidence=None
    )

    result = _pseudonymizer().sanitize(request, [malformed])

    assert result.status == "blocked"
    assert "123.456.789-09" not in result.external_payload


def test_pseudonyms_are_stable_for_the_same_value_within_the_same_scope():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    first = pseudonymizer.sanitize(_request(text), Detector().detect(text))
    second = pseudonymizer.sanitize(_request(text), Detector().detect(text))

    first_pseudonym = next(
        t.transformed for t in first.transformations if t.category == "employee_name"
    )
    second_pseudonym = next(
        t.transformed for t in second.transformations if t.category == "employee_name"
    )
    assert first_pseudonym == second_pseudonym


def test_two_users_sharing_a_role_no_longer_share_a_partition():
    # Before issue #23 / T16, a missing requester_id fell back to
    # requester_role, so two different users sharing a role and both lacking
    # a requester_id collapsed onto the very same vault partition. Both
    # requesters below share a role and omit requester_id entirely; only
    # their session identifier differs, exactly as two genuinely distinct
    # users' sessions would.
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    alice = pseudonymizer.sanitize(
        _request(text, requester_id=None, session_id="alice-session"), Detector().detect(text)
    )
    bob = pseudonymizer.sanitize(
        _request(text, requester_id=None, session_id="bob-session"), Detector().detect(text)
    )

    assert _employee_name_pseudonym(alice) != _employee_name_pseudonym(bob)


def test_round_trip_reconstruction_recovers_the_original_value():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"
    request = _request(text)
    result = pseudonymizer.sanitize(request, Detector().detect(text))
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")

    # Simulate a provider response echoing the pseudonym back.
    response_text = f"Please schedule a review with {pseudonym} next week."
    reconstructed = pseudonymizer.reconstruct(response_text, result, request.context)

    assert reconstructed == "Please schedule a review with Ana Souza next week."


def test_multi_entity_contract_round_trip_preserves_relationships():
    # A contract-style case with several distinct parties, each appearing
    # more than once: both employee_name lines are single-occurrence (the
    # labeled-line detector only matches one "Employee:" line per person),
    # but each CPF number also reappears later in free text, exercising
    # repeated-occurrence stability for two different people at once.
    text = (
        "Employee: Ana Souza\n"
        "CPF: 111.111.111-11\n"
        "Employee: Bruno Lima\n"
        "CPF: 222.222.222-22\n"
        "Department: Engineering\n"
        "Contract note: 111.111.111-11 will supervise 222.222.222-22 "
        "on the Engineering project.\n"
    )
    request = _request(text)
    pseudonymizer = _pseudonymizer()
    result = pseudonymizer.sanitize(request, Detector().detect(text))

    assert result.status == "allowed"
    for original in ("Ana Souza", "Bruno Lima", "111.111.111-11", "222.222.222-22"):
        assert original not in result.external_payload

    cpf_transforms = [t for t in result.transformations if t.category == "cpf"]
    assert len(cpf_transforms) == 4  # two occurrences each for two distinct CPFs

    ana_cpf_pseudonym = next(
        t.transformed for t in cpf_transforms if t.original == "111.111.111-11"
    )
    bruno_cpf_pseudonym = next(
        t.transformed for t in cpf_transforms if t.original == "222.222.222-22"
    )
    assert ana_cpf_pseudonym != bruno_cpf_pseudonym
    # Both occurrences of the same CPF must have collapsed to the same pseudonym.
    assert {t.transformed for t in cpf_transforms if t.original == "111.111.111-11"} == {
        ana_cpf_pseudonym
    }

    ana_name_pseudonym = next(
        t.transformed
        for t in result.transformations
        if t.category == "employee_name" and t.original == "Ana Souza"
    )
    bruno_name_pseudonym = next(
        t.transformed
        for t in result.transformations
        if t.category == "employee_name" and t.original == "Bruno Lima"
    )

    # Simulate a provider response that references each party by pseudonym,
    # more than once, in a way that only makes sense if the relationships
    # (who supervises whom) are preserved through reconstruction.
    response_text = (
        f"{ana_name_pseudonym} (CPF {ana_cpf_pseudonym}) supervises "
        f"{bruno_name_pseudonym} (CPF {bruno_cpf_pseudonym}). "
        f"{ana_cpf_pseudonym} is the responsible party for the Engineering project; "
        f"{bruno_cpf_pseudonym} reports to {ana_cpf_pseudonym}."
    )

    reconstructed = pseudonymizer.reconstruct(response_text, result, request.context)

    expected = (
        "Ana Souza (CPF 111.111.111-11) supervises "
        "Bruno Lima (CPF 222.222.222-22). "
        "111.111.111-11 is the responsible party for the Engineering project; "
        "222.222.222-22 reports to 111.111.111-11."
    )
    assert reconstructed == expected


def test_reconstruction_blocked_by_policy_returns_no_originals():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"
    request = _request(text)
    result = pseudonymizer.sanitize(request, Detector().detect(text))
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")

    unauthorized_context = GovernanceContext(
        domain="hr",
        purpose="team_summary",
        requester_role="hr_analyst",
        requester_id="u1",
        policy_version="does-not-exist",
    )
    response_text = f"Contact {pseudonym} about the leave request."

    reconstructed = pseudonymizer.reconstruct(response_text, result, unauthorized_context)

    assert reconstructed == response_text
    assert "Ana Souza" not in reconstructed


def test_external_payload_never_contains_original_values():
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
    request = _request(text)
    result = _pseudonymizer().sanitize(request, Detector().detect(text))

    assert "Ana Souza" not in result.external_payload
    assert "123.456.789-09" not in result.external_payload
    assert "8500.00" not in result.external_payload
    assert (
        "Engineering" in result.external_payload
    )  # PRESERVE still discloses non-sensitive-mapped fields


# --- Issue #23 / T16: real REQUEST/DOCUMENT/SESSION lifecycle semantics ----
#
# Below, "scope" always means the *resolved* scope (PolicyRepository.
# resolve_pseudonym_scope's output), not merely the requested one -- the
# hr_viewer-ceiling test specifically pins that a policy ceiling narrowing
# the requested scope changes the *identifier* the partition key uses, and
# therefore actually changes cross-request linkability, not only a label.


def test_request_scope_produces_different_pseudonyms_across_distinct_requests():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    first = pseudonymizer.sanitize(
        _request(text, requested_pseudonym_scope=PseudonymScope.REQUEST, request_id="req-1"),
        Detector().detect(text),
    )
    second = pseudonymizer.sanitize(
        _request(text, requested_pseudonym_scope=PseudonymScope.REQUEST, request_id="req-2"),
        Detector().detect(text),
    )

    assert _employee_name_pseudonym(first) != _employee_name_pseudonym(second)


def test_document_scope_is_stable_within_a_document_and_differs_across_documents():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    doc1_first = pseudonymizer.sanitize(
        _request(text, requested_pseudonym_scope=PseudonymScope.DOCUMENT, document_id="doc-1"),
        Detector().detect(text),
    )
    doc1_second = pseudonymizer.sanitize(
        _request(text, requested_pseudonym_scope=PseudonymScope.DOCUMENT, document_id="doc-1"),
        Detector().detect(text),
    )
    doc2 = pseudonymizer.sanitize(
        _request(text, requested_pseudonym_scope=PseudonymScope.DOCUMENT, document_id="doc-2"),
        Detector().detect(text),
    )

    assert _employee_name_pseudonym(doc1_first) == _employee_name_pseudonym(doc1_second)
    assert _employee_name_pseudonym(doc1_first) != _employee_name_pseudonym(doc2)


def test_session_scope_is_stable_within_a_session_and_differs_across_sessions():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    session1_first = pseudonymizer.sanitize(
        _request(text, session_id="sess-1"), Detector().detect(text)
    )
    session1_second = pseudonymizer.sanitize(
        _request(text, session_id="sess-1"), Detector().detect(text)
    )
    session2 = pseudonymizer.sanitize(_request(text, session_id="sess-2"), Detector().detect(text))

    assert _employee_name_pseudonym(session1_first) == _employee_name_pseudonym(session1_second)
    assert _employee_name_pseudonym(session1_first) != _employee_name_pseudonym(session2)


def test_organization_scope_pseudonyms_are_shared_across_requesters_and_sessions():
    # ORGANIZATION remains keyed at organization/domain scope, unchanged by
    # this issue -- it is shared by every requester in the domain regardless
    # of any per-request/document/session identifier.
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    first = pseudonymizer.sanitize(
        _request(
            text,
            requester_role="hr_admin",
            requester_id="u1",
            requested_pseudonym_scope=PseudonymScope.ORGANIZATION,
            session_id="s1",
        ),
        Detector().detect(text),
    )
    second = pseudonymizer.sanitize(
        _request(
            text,
            requester_role="hr_admin",
            requester_id="u2",
            requested_pseudonym_scope=PseudonymScope.ORGANIZATION,
            session_id="s2",
        ),
        Detector().detect(text),
    )

    assert _employee_name_pseudonym(first) == _employee_name_pseudonym(second)


def test_missing_request_id_blocks_when_request_scope_is_resolved():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"
    request = _request(text, requested_pseudonym_scope=PseudonymScope.REQUEST, request_id=None)

    result = pseudonymizer.sanitize(request, Detector().detect(text))

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "Ana Souza" not in result.external_payload


def test_missing_document_id_blocks_when_document_scope_is_resolved():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"
    request = _request(text, requested_pseudonym_scope=PseudonymScope.DOCUMENT, document_id=None)

    result = pseudonymizer.sanitize(request, Detector().detect(text))

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "Ana Souza" not in result.external_payload


def test_missing_session_id_blocks_when_session_scope_is_resolved():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"
    # Default requested scope is SESSION and hr_analyst's ceiling is SESSION.
    request = _request(text, session_id=None)

    result = pseudonymizer.sanitize(request, Detector().detect(text))

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert "Ana Souza" not in result.external_payload


def test_unresolvable_policy_defaults_to_request_scope_and_blocks_without_a_request_id():
    # Trap named in issue #23: PolicyRepository.resolve_pseudonym_scope's
    # fail-closed default for a missing/mismatched policy is REQUEST. That
    # was harmless while REQUEST behaved like SESSION; now it demands
    # request_id, so an unresolvable policy combined with no request_id
    # blocks -- fail closed twice, deliberately, rather than silently
    # resolving some other partition.
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"
    request = _request(text, policy_version="does-not-exist", request_id=None)

    result = pseudonymizer.sanitize(request, Detector().detect(text))

    assert result.status == "blocked"
    assert result.external_payload == ""


def test_hr_viewer_request_ceiling_actually_limits_cross_request_linkability():
    # This is the point of the whole issue: configs/policies/hr-v1.yaml caps
    # hr_viewer at REQUEST while the default scope is SESSION. That ceiling
    # must change which identifier partitions the vault -- and therefore
    # actual cross-request linkability -- not just the scope's label.
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    # hr_viewer requests the default SESSION scope but is capped to REQUEST,
    # so it must key on request_id and therefore differ across two requests
    # even though both belong to the same session.
    viewer_first = pseudonymizer.sanitize(
        _request(
            text,
            requester_role="hr_viewer",
            requester_id=None,
            request_id="req-1",
            session_id="sess-shared",
        ),
        Detector().detect(text),
    )
    viewer_second = pseudonymizer.sanitize(
        _request(
            text,
            requester_role="hr_viewer",
            requester_id=None,
            request_id="req-2",
            session_id="sess-shared",
        ),
        Detector().detect(text),
    )

    # hr_analyst is permitted SESSION scope -- across the same two "requests"
    # (the same session), its pseudonym must stay stable, in contrast to
    # hr_viewer above.
    analyst_first = pseudonymizer.sanitize(
        _request(
            text,
            requester_role="hr_analyst",
            requester_id=None,
            request_id="req-1",
            session_id="sess-shared",
        ),
        Detector().detect(text),
    )
    analyst_second = pseudonymizer.sanitize(
        _request(
            text,
            requester_role="hr_analyst",
            requester_id=None,
            request_id="req-2",
            session_id="sess-shared",
        ),
        Detector().detect(text),
    )

    assert _employee_name_pseudonym(viewer_first) != _employee_name_pseudonym(viewer_second)
    assert _employee_name_pseudonym(analyst_first) == _employee_name_pseudonym(analyst_second)


def test_request_scope_round_trip_reconstruction_recomputes_the_same_partition_key():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"
    request = _request(text, requested_pseudonym_scope=PseudonymScope.REQUEST, request_id="req-1")
    result = pseudonymizer.sanitize(request, Detector().detect(text))
    pseudonym = _employee_name_pseudonym(result)

    response_text = f"Please contact {pseudonym} today."
    reconstructed = pseudonymizer.reconstruct(response_text, result, request.context)

    assert reconstructed == "Please contact Ana Souza today."
