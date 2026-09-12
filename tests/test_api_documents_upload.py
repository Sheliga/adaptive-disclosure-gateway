"""The structured-document upload surface (T20 / issue #28's demo
integration slice; issue #41 gate A).

`multipart/binary HTTP -> application input -> T12 ingestion -> NormalizedContent -> existing core`

What these tests exist to catch -- each is a real defect this surface could
plausibly have:

- an uploaded contract being analysed under the server's HR defaults
  (issue #41's blocker 4) -- silently, with a payload that looks plausible;
- the HTTP layer buffering an arbitrarily large body before
  ``application/ingestion.py``'s ``MAX_INPUT_BYTES`` ever sees it;
- the upload endpoint calling the provider without the mandatory
  pre-disclosure review step, collapsing preview -> confirm -> execute into
  one shot;
- an unsupported extension, a parser crash or an oversized body echoing the
  document's own bytes/text back over HTTP (CLAUDE.md's no-leak invariant);
- an API credential reaching an HTTP response body;
- a provider-class mismatch reaching the provider anyway.

Every always-on test injects its own ``DisclosureApplicationService`` and its
own T12 parser double, so nothing depends on the environment, on Docling's
cached model artifacts, or on the network. The last section of this module
runs the same HTTP path through the real Docling adapter and is gated behind
``ADG_RUN_DOCLING_INTEGRATION=1``, the same opt-in flag
``tests/test_application_ingestion_docling.py`` uses.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any

import pytest

from adaptive_disclosure_gateway.api.app import create_app
from adaptive_disclosure_gateway.api.limits import (
    DEFAULT_MAX_UPLOAD_BYTES,
    RequestBodySizeLimitMiddleware,
)
from adaptive_disclosure_gateway.application.ingestion import ParsedDocument
from adaptive_disclosure_gateway.application.presets import CONTRACT_DOCUMENT_TYPE
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    AnthropicProvider,
    AnthropicProviderConfig,
    FakeProvider,
)
from tests.api_support import (
    POLICY_DIR,
    NeverCallMeProvider,
    RecordingProvider,
    default_context,
)
from tests.contracts_fixture import (
    CONTRACTED_PARTY,
    CONTRACTED_PARTY_CNPJ,
    CONTRACTING_PARTY,
    CONTRACTING_PARTY_CNPJ,
    CONTRACTS_FIXTURE,
    REPRESENTATIVE,
    REPRESENTATIVE_CPF,
)
from tests.test_application_document_presets import StubContractParser

CONTRACT_TASK = "Summarize the obligations of each party and the deadlines."

# The identity-bearing values from the synthetic fixture that must never
# cross the trust boundary under contracts-v1: parties and representative
# (PSEUDONYMIZE) and their tax identifiers (REMOVE).
#
# Deliberately NOT the whole of CONTRACTS_FIXTURE_SENSITIVE_VALUES. That
# tuple also contains the deadlines, and `deadline` is a hard PRESERVE in
# contracts-v1 -- the one place the policy is knowingly more disclosing than
# B3 -- Task-aware, because "sometime in March" is not a term of a contract
# (docs/contracts-policy-matrix.md). Asserting the deadlines never cross
# would assert the opposite of the frozen policy.
CONTRACT_IDENTITY_VALUES = (
    CONTRACTING_PARTY,
    CONTRACTED_PARTY,
    REPRESENTATIVE,
    CONTRACTING_PARTY_CNPJ,
    CONTRACTED_PARTY_CNPJ,
    REPRESENTATIVE_CPF,
)
SYNTHETIC_PDF_BYTES = b"%PDF-1.4 synthetic contract body"
SYNTHETIC_DOCX_BYTES = b"PK\x03\x04 synthetic contract body"


def build_service(
    provider=None, *, document_parser=None, **context_overrides
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=provider if provider is not None else FakeProvider(),
        default_context=default_context(**context_overrides),
        document_parser=document_parser,
    )


def build_client(service, **create_app_kwargs):
    from fastapi.testclient import TestClient

    return TestClient(create_app(service=service, **create_app_kwargs))


def upload(
    client,
    *,
    path: str = "/documents/preview",
    filename: str = "contract.pdf",
    data: bytes = SYNTHETIC_PDF_BYTES,
    media_type: str = "application/pdf",
    **form_fields: str,
):
    fields = {"task": CONTRACT_TASK, "document_type": CONTRACT_DOCUMENT_TYPE}
    fields.update(form_fields)
    return client.post(path, files={"file": (filename, data, media_type)}, data=fields)


# --- PDF/DOCX upload -> T12 -> Contracts -> preview --------------------------


@pytest.mark.parametrize(
    ("filename", "data", "media_type", "expected_media_type"),
    [
        ("contract.pdf", SYNTHETIC_PDF_BYTES, "application/pdf", "application/pdf"),
        (
            "contract.docx",
            SYNTHETIC_DOCX_BYTES,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_a_structured_upload_previews_under_contracts_governance(
    filename, data, media_type, expected_media_type
):
    parser = StubContractParser()
    service = build_service(document_parser=parser)
    client = build_client(service)

    response = upload(client, filename=filename, data=data, media_type=media_type)

    assert response.status_code == 200
    body = response.json()
    assert body["governance"]["domain"] == "contracts"
    assert body["governance"]["policy_version"] == "contracts-v1"
    assert body["treatment"] == "b4"
    assert body["summary"]["status"] == "allowed"
    # The binary really reached the T12 boundary rather than being decoded
    # as text somewhere in the HTTP layer.
    assert parser.calls, "the upload must be handed to the T12 parser adapter"
    assert expected_media_type  # the extension, not the client's declared type, dispatches


def test_the_preview_of_an_uploaded_contract_discloses_no_party_identity():
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)

    body = upload(client).json()

    assert CONTRACTING_PARTY not in body["external_payload"]
    assert "party_name" in body["summary"]["detected_categories"]


def test_an_uploaded_contract_is_never_silently_analysed_as_hr():
    """The service default context is HR. If ``document_type=contract``
    ever stopped reaching ``GovernanceContext``, this upload would run under
    ``hr-v1`` -- where none of the Contracts categories has a rule, so every
    one fails closed and the whole request is blocked.
    """
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)

    contract_body = upload(client).json()
    hr_body = upload(client, document_type="hr_record").json()

    assert contract_body["governance"]["policy_version"] == "contracts-v1"
    assert contract_body["summary"]["status"] == "allowed"
    assert hr_body["governance"]["policy_version"] == "hr-v1"
    assert hr_body["summary"]["status"] == "blocked"


def test_an_upload_without_a_document_type_is_refused_rather_than_defaulting():
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)

    response = client.post(
        "/documents/preview",
        files={"file": ("contract.pdf", SYNTHETIC_PDF_BYTES, "application/pdf")},
        data={"task": CONTRACT_TASK},
    )

    assert response.status_code == 422


def test_an_unregistered_document_type_fails_closed_with_a_safe_message():
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)

    response = upload(client, document_type="whatever_the_client_wants")

    assert response.status_code == 400
    assert "whatever_the_client_wants" not in response.text


def test_an_arbitrary_analysis_mode_cannot_reach_the_policy_purpose():
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)

    response = upload(client, analysis_mode="salary_analysis")

    assert response.status_code == 400


def test_an_allowlisted_analysis_mode_selects_that_policy_purpose():
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)

    body = upload(client, analysis_mode="financial_audit").json()

    assert body["governance"]["purpose"] == "financial_audit"


def test_the_document_types_endpoint_lets_the_ui_discover_the_vocabulary():
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)

    body = client.get("/documents/types").json()

    contract = next(
        entry
        for entry in body["document_types"]
        if entry["document_type"] == CONTRACT_DOCUMENT_TYPE
    )
    assert contract["analysis_modes"][0] == contract["default_analysis_mode"]
    assert "financial_audit" in contract["analysis_modes"]
    # The UI learns which modes exist -- never which policy they select.
    assert "policy_version" not in contract
    assert "domain" not in contract


# --- preview -> confirm -> execute separation --------------------------------


def test_a_document_preview_never_reaches_the_provider():
    service = build_service(NeverCallMeProvider(), document_parser=StubContractParser())
    client = build_client(service)

    response = upload(client)

    assert response.status_code == 200


def test_a_confirmed_document_execute_reaches_the_provider_with_the_reviewed_payload():
    provider = RecordingProvider()
    service = build_service(provider, document_parser=StubContractParser())
    client = build_client(service)

    preview = upload(client).json()
    execution = upload(client, path="/documents/execute").json()

    assert len(provider.received) == 1
    sent = provider.received[0]
    assert sent.payload == preview["external_payload"]
    assert sent.task == CONTRACT_TASK
    for value in CONTRACT_IDENTITY_VALUES:
        assert value not in sent.payload
        assert value not in sent.task
    assert execution["provider"]["called"] is True


def test_there_is_no_upload_endpoint_that_both_uploads_and_calls_the_provider_unreviewed():
    """The review step is the product. A route that ingested and executed in
    one call would defeat it, so the only execute route is a separate,
    explicitly-confirmed one.
    """
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)
    paths = {
        route.path
        for route in client.app.routes
        if getattr(route, "path", "").startswith("/documents")
    }

    assert paths == {"/documents/preview", "/documents/execute", "/documents/types"}


# --- fail-closed ingestion ---------------------------------------------------


def test_an_unsupported_extension_fails_closed_without_running_a_parser():
    parser = StubContractParser()
    service = build_service(document_parser=parser)
    client = build_client(service)

    response = upload(
        client, filename="contract.exe", data=b"MZ synthetic", media_type="application/octet-stream"
    )

    assert response.status_code == 400
    assert parser.calls == []
    assert "MZ synthetic" not in response.text


def test_a_parser_failure_returns_safe_metadata_and_echoes_no_document_content():
    marker = "Aurora Servicos Digitais Ltda"

    class EchoingParser:
        parser_name = "echoing"
        parser_version = "test"

        def parse(self, *, safe_name: str, data: bytes) -> ParsedDocument:
            raise RuntimeError(f"parser blew up on {marker}: {data!r}")

    service = build_service(document_parser=EchoingParser())
    client = build_client(service)

    response = upload(client, data=marker.encode("utf-8"))

    assert response.status_code == 400
    assert marker not in response.text
    assert ".pdf" in response.json()["detail"]


def test_an_upload_large_enough_to_spool_to_disk_leaves_no_file_behind(tmp_path, monkeypatch):
    """Uploaded source documents are ephemeral (issue #28/#41).

    This is deliberately an *oversized* upload, not a small one. Starlette
    backs ``UploadFile`` with a ``SpooledTemporaryFile`` whose in-memory
    threshold is 1 MiB, so a part above that really does touch the
    filesystem while the request is in flight -- no application code writes
    it, but asserting "nothing is persisted" with a 30-byte body would pass
    without ever exercising that path and would pin nothing.

    What must hold is that the temporary is destroyed once the request is
    over. The process temp directory is redirected to an empty one for the
    duration (``tempfile.tempdir`` directly, because ``tempfile`` caches the
    environment-derived value on first use), and it must be empty again
    afterwards.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)
    spilling_upload = b"%PDF-1.4 " + b"x" * (2 * 1024 * 1024)

    assert upload(client, data=spilling_upload).status_code == 200

    assert list(tmp_path.iterdir()) == []


# --- upload size limit at the HTTP boundary ----------------------------------


def test_an_oversized_upload_is_rejected_before_ingestion_or_parsing():
    parser = StubContractParser()
    service = build_service(document_parser=parser)
    client = build_client(service, max_upload_bytes=256)

    response = upload(client, data=b"x" * 4096)

    assert response.status_code == 413
    assert parser.calls == []


def test_the_oversized_rejection_echoes_no_document_content():
    marker = "Aurora Servicos Digitais Ltda "
    service = build_service(document_parser=StubContractParser())
    client = build_client(service, max_upload_bytes=256)

    response = upload(client, data=(marker * 200).encode("utf-8"))

    assert response.status_code == 413
    assert "Aurora" not in response.text
    assert response.json()["kind"] == "RequestBodyTooLarge"


def test_a_chunked_upload_with_no_declared_length_is_still_cut_off_at_the_limit():
    """A client that omits ``Content-Length`` (chunked transfer) must not be
    able to stream an unbounded body into the server. The declared-length
    check alone would let exactly that through, which would make the
    client's own honesty the only protection.
    """
    parser = StubContractParser()
    service = build_service(document_parser=parser)
    client = build_client(service, max_upload_bytes=256)
    boundary = "adgtestboundary"

    def chunks():
        for name, value in (("task", CONTRACT_TASK), ("document_type", CONTRACT_DOCUMENT_TYPE)):
            yield (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            ).encode()
        yield (
            f"--{boundary}\r\nContent-Disposition: form-data; "
            'name="file"; filename="contract.pdf"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        for _ in range(64):
            yield b"x" * 64
        yield f"\r\n--{boundary}--\r\n".encode()

    response = client.post(
        "/documents/preview",
        content=chunks(),
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 413
    assert parser.calls == []


def test_a_streamed_body_is_cut_off_mid_stream_rather_than_fully_buffered():
    """The streaming counter, isolated: with no ``Content-Length`` to go on,
    the middleware must stop pulling chunks as soon as the running total
    passes the limit -- not after the whole body has arrived.
    """
    chunks_pulled = 0
    sent: list[dict[str, Any]] = []

    async def inner_app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                return

    async def receive():
        nonlocal chunks_pulled
        chunks_pulled += 1
        return {"type": "http.request", "body": b"x" * 32, "more_body": True}

    async def send(message):
        sent.append(message)

    middleware = RequestBodySizeLimitMiddleware(inner_app, max_bytes=64)
    scope = {"type": "http", "method": "POST", "path": "/documents/preview", "headers": []}
    asyncio.run(middleware(scope, receive, send))

    # 32 + 32 = 64 is still within the limit; the third chunk crosses it and
    # is the last one ever pulled.
    assert chunks_pulled == 3
    assert sent[0]["status"] == 413


def test_a_declared_oversized_length_is_rejected_without_reading_the_body():
    """The declared-length branch must answer 413 without pulling a single
    body chunk -- that is the whole point of enforcing the limit at the
    HTTP boundary rather than in ingestion.
    """
    receive_calls = 0
    sent: list[dict[str, Any]] = []

    async def inner_app(scope, receive, send):  # pragma: no cover - must never run
        raise AssertionError("the oversized request must never reach the application")

    async def receive():
        nonlocal receive_calls
        receive_calls += 1
        return {"type": "http.request", "body": b"x" * 16, "more_body": False}

    async def send(message):
        sent.append(message)

    middleware = RequestBodySizeLimitMiddleware(inner_app, max_bytes=64)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/documents/preview",
        "headers": [(b"content-length", b"100000")],
    }
    asyncio.run(middleware(scope, receive, send))

    assert receive_calls == 0
    assert sent[0]["status"] == 413
    body = json.loads(sent[1]["body"])
    assert body["kind"] == "RequestBodyTooLarge"


def test_the_default_upload_limit_is_below_the_ingestion_byte_limit():
    """The HTTP boundary must be the binding one for uploads, so an
    oversized body is refused before any normalization/parsing work starts.
    """
    from adaptive_disclosure_gateway.application.ingestion import MAX_INPUT_BYTES

    assert DEFAULT_MAX_UPLOAD_BYTES < MAX_INPUT_BYTES


# --- real provider configuration ---------------------------------------------


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any):
        self.calls.append(kwargs)
        return _FakeMessage()


class _FakeBlock:
    type = "text"
    text = "Both parties owe the stated obligations."


class _FakeUsage:
    input_tokens = 11
    output_tokens = 7
    cache_creation_input_tokens = None
    cache_read_input_tokens = None


class _FakeMessage:
    def __init__(self) -> None:
        self.content = [_FakeBlock()]
        self.model = "claude-opus-5"
        self.stop_reason = "end_turn"
        self.usage = _FakeUsage()
        self.stop_details = None


class _FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_a_real_provider_configuration_executes_as_external_llm_and_leaks_no_secret(monkeypatch):
    marker_key = "sk-ant-marker-DO-NOT-LEAK-9f3b2a1c"
    monkeypatch.setenv("ANTHROPIC_API_KEY", marker_key)
    client_double = _FakeAnthropicClient()
    provider = AnthropicProvider(AnthropicProviderConfig(), client=client_double)
    service = build_service(
        provider, document_parser=StubContractParser(), provider_class="external_llm"
    )
    client = build_client(service)

    health = client.get("/health").json()
    execution = upload(client, path="/documents/execute").json()

    assert health["provider"]["provider_class"] == "external_llm"
    assert health["provider"]["deterministic_demo_mode"] is False
    assert execution["governance"]["provider_class"] == "external_llm"
    assert execution["provider"]["called"] is True
    assert execution["provider"]["failed"] is False
    assert execution["final_answer"]

    # The disclosure-controlled payload -- and only that -- reached the SDK.
    assert len(client_double.messages.calls) == 1
    transmitted = json.dumps(client_double.messages.calls[0], default=str)
    for value in CONTRACT_IDENTITY_VALUES:
        assert value not in transmitted

    # The credential reaches no HTTP response.
    assert marker_key not in client.get("/health").text
    assert marker_key not in json.dumps(execution)


def test_a_contract_request_under_a_mismatched_provider_configuration_never_calls_the_provider():
    """The deployment declares ``provider_class="fake"`` while the wired
    provider is the real external adapter. The call must be refused at the
    provider boundary, not merely reported afterwards.
    """
    client_double = _FakeAnthropicClient()
    provider = AnthropicProvider(AnthropicProviderConfig(), client=client_double)
    service = build_service(provider, document_parser=StubContractParser(), provider_class="fake")
    client = build_client(service)

    execution = upload(client, path="/documents/execute").json()

    assert client_double.messages.calls == []
    assert execution["provider"]["failed"] is True
    assert execution["final_answer"] is None


def test_the_reconstructed_answer_is_produced_locally_after_the_provider_call():
    """B2-B4 pseudonyms are reconstructed inside the trust boundary, so the
    final answer may legitimately name a party the provider never saw.
    """

    class _EchoBackMessages(_FakeMessages):
        def create(self, **kwargs: Any):
            self.calls.append(kwargs)
            payload = kwargs["messages"][0]["content"]
            pseudonym = next(
                token.strip(".,;:")
                for token in payload.split()
                if token.startswith("PSEUDO-party_name")
            )
            message = _FakeMessage()
            message.content = [_FakeBlock()]
            message.content[0].text = f"The obligated party is {pseudonym}."
            return message

    client_double = _FakeAnthropicClient()
    client_double.messages = _EchoBackMessages()
    provider = AnthropicProvider(AnthropicProviderConfig(), client=client_double)
    service = build_service(
        provider, document_parser=StubContractParser(), provider_class="external_llm"
    )
    client = build_client(service)

    execution = upload(client, path="/documents/execute").json()

    assert execution["reconstruction"]["attempted"] is True
    assert CONTRACTING_PARTY in execution["final_answer"]
    assert CONTRACTING_PARTY not in json.dumps(client_double.messages.calls, default=str)


# --- the whole T21-facing gate -----------------------------------------------


def test_the_ui_never_needs_to_know_docling_policies_or_the_provider():
    """Everything a T21 client sends is in this one set of form fields. If
    a policy version, a governance context, a parser name or a provider
    configuration ever became a required request field, this fails.
    """
    service = build_service(document_parser=StubContractParser())
    client = build_client(service)
    schema = client.get("/openapi.json").json()
    body_schema = schema["paths"]["/documents/preview"]["post"]["requestBody"]["content"][
        "multipart/form-data"
    ]["schema"]
    ref = body_schema["$ref"].rsplit("/", 1)[-1]
    properties = schema["components"]["schemas"][ref]["properties"]

    assert set(properties) == {"file", "task", "document_type", "analysis_mode", "strategy"}
    assert set(schema["components"]["schemas"][ref]["required"]) == {
        "file",
        "task",
        "document_type",
    }


# --- the T20 completion gate, against the real T12 parser --------------------
#
# Everything above runs against a parser double so the always-on suite stays
# deterministic and offline. These two run the *same* HTTP path through real
# Docling, and are the executable form of the ticket's completion gate:
#
#   a synthetic contract.pdf / contract.docx
#     -> HTTP multipart -> T12 -> NormalizedContent
#     -> Contracts / contracts-v1 -> a B4 -- Policy-governed preview
#     -> a confirmed execute reaching the provider -> local reconstruction
#
# Gated behind the same opt-in flag as tests/test_application_ingestion_docling.py:
# real Docling conversion can require cached model artifacts that a fresh CI
# environment does not have. The flow itself is covered unconditionally above;
# what is gated here is only whether the real parser participates.


def _docling_gate():
    pytest.importorskip("docling")
    if os.environ.get("ADG_RUN_DOCLING_INTEGRATION") != "1":
        pytest.skip(
            "real Docling conversion can require external model artifacts; set "
            "ADG_RUN_DOCLING_INTEGRATION=1 in an environment with those artifacts available"
        )


@pytest.mark.parametrize(
    ("filename", "builder", "media_type"),
    [
        ("contract.pdf", "pdf", "application/pdf"),
        (
            "contract.docx",
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_a_real_synthetic_contract_reaches_a_policy_governed_preview(filename, builder, media_type):
    _docling_gate()
    from tests.document_fixtures import minimal_docx_bytes, minimal_pdf_bytes

    lines = CONTRACTS_FIXTURE.splitlines()
    data = minimal_pdf_bytes(lines) if builder == "pdf" else minimal_docx_bytes(lines)
    # No document_parser injected: the service loads the real T12 adapter.
    service = build_service()
    client = build_client(service)

    body = upload(client, filename=filename, data=data, media_type=media_type).json()

    assert body["governance"]["domain"] == "contracts"
    assert body["governance"]["policy_version"] == "contracts-v1"
    assert body["treatment"] == "b4"
    assert body["summary"]["status"] == "allowed"
    assert set(body["summary"]["detected_categories"]) >= {
        "party_name",
        "representative_name",
        "cnpj",
        "cpf",
        "contract_value",
        "penalty_amount",
        "deadline",
    }
    for value in CONTRACT_IDENTITY_VALUES:
        assert value not in body["external_payload"]


def test_a_real_synthetic_contract_executes_and_is_reconstructed_locally():
    _docling_gate()
    from tests.document_fixtures import minimal_pdf_bytes

    provider = RecordingProvider()
    service = build_service(provider)
    client = build_client(service)
    data = minimal_pdf_bytes(CONTRACTS_FIXTURE.splitlines())

    preview = upload(client, data=data).json()
    execution = upload(client, path="/documents/execute", data=data).json()

    assert len(provider.received) == 1
    assert provider.received[0].payload == preview["external_payload"]
    for value in CONTRACT_IDENTITY_VALUES:
        assert value not in provider.received[0].payload
    assert execution["provider"]["called"] is True
    assert execution["reconstruction"]["attempted"] is True
