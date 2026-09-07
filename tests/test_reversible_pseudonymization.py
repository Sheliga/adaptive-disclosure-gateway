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
    }
    values.update(context_overrides)
    return DisclosureRequest(text=text, task="summarize", context=GovernanceContext(**values))


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
    assert "500" not in result.external_payload


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


def test_different_requesters_do_not_share_pseudonym_mappings():
    pseudonymizer = _pseudonymizer()
    text = "Employee: Ana Souza\n"

    from_u1 = pseudonymizer.sanitize(_request(text, requester_id="u1"), Detector().detect(text))
    from_u2 = pseudonymizer.sanitize(_request(text, requester_id="u2"), Detector().detect(text))

    pseudonym_u1 = next(
        t.transformed for t in from_u1.transformations if t.category == "employee_name"
    )
    pseudonym_u2 = next(
        t.transformed for t in from_u2.transformations if t.category == "employee_name"
    )
    assert pseudonym_u1 != pseudonym_u2


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
    assert "8500" not in result.external_payload
    assert (
        "Engineering" in result.external_payload
    )  # PRESERVE still discloses non-sensitive-mapped fields
