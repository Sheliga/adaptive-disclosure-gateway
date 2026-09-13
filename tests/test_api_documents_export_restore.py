"""``POST /documents/export`` and ``POST /documents/restore`` (T26 / issue
#67): the HTTP surface for exporting a disclosed structured-document
representation together with a sealed restore handle, and for restoring
pseudonyms from arbitrary submitted text through that handle alone.

Mirrors ``tests/test_api_documents_upload.py``'s style: every always-on test
injects its own ``DisclosureApplicationService`` (real core, stub T12
parser, stub provider) and its own ``RestoreHandleSealer``, so nothing here
depends on the environment.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from adaptive_disclosure_gateway.api.app import create_app
from adaptive_disclosure_gateway.application.presets import CONTRACT_DOCUMENT_TYPE
from adaptive_disclosure_gateway.application.restore_handle import RestoreHandleSealer
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.policies import PolicyRepository
from tests.api_support import POLICY_DIR, NeverCallMeProvider, default_context
from tests.contracts_fixture import CONTRACTING_PARTY, CONTRACTS_FIXTURE
from tests.test_application_document_presets import StubContractParser

CONTRACT_TASK = "Summarize the obligations of each party and the deadlines."
SECRET = "a-test-only-restore-handle-secret-value-32bytes"

HR_TEXT = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
HR_TEXT_WITH_MEDICAL = HR_TEXT + "Medical notes: Reports chronic migraine.\n"


def build_service(
    provider=None, *, document_parser=None, restore_handle_sealer=None, **context_overrides
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=provider if provider is not None else NeverCallMeProvider(),
        default_context=default_context(**context_overrides),
        document_parser=document_parser,
        restore_handle_sealer=restore_handle_sealer,
    )


def build_client(service, **create_app_kwargs) -> TestClient:
    return TestClient(create_app(service=service, **create_app_kwargs))


def export_upload(client, *, data: bytes = CONTRACTS_FIXTURE.encode("utf-8"), **form_fields):
    fields = {"task": CONTRACT_TASK, "document_type": CONTRACT_DOCUMENT_TYPE}
    fields.update(form_fields)
    return client.post(
        "/documents/export", files={"file": ("contract.pdf", data, "application/pdf")}, data=fields
    )


def _configured_sealer(**kwargs) -> RestoreHandleSealer:
    return RestoreHandleSealer(secret=SECRET, **kwargs)


# --- export ----------------------------------------------------------------------


def test_export_returns_200_with_a_disclosed_payload_and_a_handle():
    service = build_service(
        document_parser=StubContractParser(), restore_handle_sealer=_configured_sealer()
    )
    client = build_client(service)

    response = export_upload(client)

    assert response.status_code == 200
    body = response.json()
    assert CONTRACTING_PARTY not in body["external_payload"]
    assert body["restore_handle"]
    assert body["restorable_count"] > 0
    assert "expires_at" in body


def test_export_response_never_contains_the_original_value():
    service = build_service(
        document_parser=StubContractParser(), restore_handle_sealer=_configured_sealer()
    )
    client = build_client(service)

    response = export_upload(client)

    assert CONTRACTING_PARTY not in response.text


def test_export_never_calls_the_provider():
    # NeverCallMeProvider (from tests.api_support) raises if .generate is
    # ever invoked -- the default provider here, so a 200 with no assertion
    # error is itself the proof.
    service = build_service(
        document_parser=StubContractParser(), restore_handle_sealer=_configured_sealer()
    )
    client = build_client(service)

    response = export_upload(client)
    assert response.status_code == 200


def test_export_is_refused_with_400_for_a_blocked_document_type():
    service = build_service(
        document_parser=StubContractParser(), restore_handle_sealer=_configured_sealer()
    )
    client = build_client(service)

    # hr_record governance over a Contracts-shaped document blocks every
    # detected category (see test_an_uploaded_contract_is_never_silently_analysed_as_hr).
    response = export_upload(client, document_type="hr_record")

    assert response.status_code == 400


def test_export_returns_503_when_no_restore_handle_secret_is_configured():
    service = build_service(document_parser=StubContractParser(), restore_handle_sealer=None)
    client = build_client(service)

    response = export_upload(client)

    assert response.status_code == 503


def test_health_and_preview_still_work_when_no_restore_handle_secret_is_configured():
    service = build_service(document_parser=StubContractParser(), restore_handle_sealer=None)
    client = build_client(service)

    assert client.get("/health").status_code == 200
    fields = {"task": CONTRACT_TASK, "document_type": CONTRACT_DOCUMENT_TYPE}
    response = client.post(
        "/documents/preview",
        files={"file": ("contract.pdf", CONTRACTS_FIXTURE.encode("utf-8"), "application/pdf")},
        data=fields,
    )
    assert response.status_code == 200


# --- restore -----------------------------------------------------------------------


def test_restore_recovers_originals_present_in_the_submitted_text():
    sealer = _configured_sealer()
    service = build_service(document_parser=StubContractParser(), restore_handle_sealer=sealer)
    client = build_client(service)

    export_body = export_upload(client).json()

    response = client.post(
        "/documents/restore",
        json={
            "text": export_body["external_payload"],
            "restore_handle": export_body["restore_handle"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert CONTRACTING_PARTY in body["restored_text"]
    assert body["restored_count"] > 0
    assert body["unresolved_count"] == 0
    assert set(body) == {
        "contract_version",
        "restored_text",
        "restored_count",
        "unresolved_count",
    }


def test_restore_returns_400_for_a_tampered_handle():
    sealer = _configured_sealer()
    service = build_service(document_parser=StubContractParser(), restore_handle_sealer=sealer)
    client = build_client(service)

    export_body = export_upload(client).json()
    prefix, blob = export_body["restore_handle"].split(".", 1)
    tampered = f"{prefix}.{blob[:-4]}0000"

    response = client.post(
        "/documents/restore", json={"text": "irrelevant", "restore_handle": tampered}
    )

    assert response.status_code == 400


def test_restore_returns_503_when_no_restore_handle_secret_is_configured():
    service = build_service(document_parser=StubContractParser(), restore_handle_sealer=None)
    client = build_client(service)

    response = client.post(
        "/documents/restore", json={"text": "irrelevant", "restore_handle": "rh1.whatever"}
    )

    assert response.status_code == 503


def test_restore_request_body_rejects_unknown_fields():
    service = build_service(
        document_parser=StubContractParser(), restore_handle_sealer=_configured_sealer()
    )
    client = build_client(service)

    response = client.post(
        "/documents/restore",
        json={"text": "x", "restore_handle": "rh1.y", "unexpected": "field"},
    )

    assert response.status_code == 422
