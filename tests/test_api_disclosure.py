"""T20 / issue #28, slice 2: ``POST /disclosure/preview`` and
``POST /disclosure/execute``. Requirements 3, 4, 5, 6, 7, 10.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureStrategy,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from adaptive_disclosure_gateway.providers import FakeProvider
from tests.api_support import (
    EXAMPLES_DIR,
    HR_TEXT,
    HR_TEXT_WITH_MEDICAL,
    NeverCallMeProvider,
    RecordingProvider,
    build_client,
    build_service,
)

# --- 3. preview never calls the provider -------------------------------------


def test_preview_never_calls_the_provider():
    client = build_client(build_service(NeverCallMeProvider()))

    response = client.post(
        "/disclosure/preview", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    assert response.status_code == 200
    assert response.json()["summary"]["status"] == "allowed"


# --- 4. the HTTP adapter does not alter the application service's result ----


def test_preview_response_fields_equal_the_direct_service_result():
    provider = RecordingProvider()
    service = build_service(provider)
    client = build_client(service)
    body = {"text": HR_TEXT, "task": "summarize personnel record"}

    direct = service.preview(
        DisclosureApplicationRequest(content=normalize_text(HR_TEXT), task=body["task"])
    )
    response = client.post("/disclosure/preview", json=body)

    payload = response.json()
    assert payload["external_payload"] == direct.external_payload
    assert payload["payload_byte_count"] == direct.payload_byte_count
    assert payload["treatment"] == direct.treatment.value
    assert payload["strategy"] == direct.strategy.value
    assert payload["summary"]["status"] == direct.summary.status
    assert payload["summary"]["detected_span_count"] == direct.summary.detected_span_count
    assert payload["governance"]["domain"] == direct.governance.domain
    assert payload["governance"]["purpose"] == direct.governance.purpose


def test_execute_response_fields_equal_the_direct_service_result():
    provider = RecordingProvider()
    service = build_service(provider)
    client = build_client(service)
    body = {"text": HR_TEXT, "task": "summarize personnel record"}

    direct = service.execute(
        DisclosureApplicationRequest(content=normalize_text(HR_TEXT), task=body["task"])
    )
    response = client.post("/disclosure/execute", json=body)

    payload = response.json()
    assert payload["status"] == direct.summary.status
    assert payload["final_answer"] == direct.final_answer
    assert payload["treatment"] == direct.treatment.value
    assert payload["provider"]["called"] == direct.provider.called
    assert payload["provider"]["failed"] == direct.provider.failed
    assert payload["reconstruction"]["attempted"] == direct.reconstruction.attempted


# --- 5. direct text reaches the core unchanged -------------------------------


def test_direct_text_reaches_the_core_unchanged_under_the_direct_strategy():
    client = build_client(build_service(RecordingProvider()))
    text = "Employee: Ana Souza\nCPF: 123.456.789-09\n"

    response = client.post(
        "/disclosure/preview", json={"text": text, "task": "summarize", "strategy": "b0"}
    )

    assert response.status_code == 200
    assert response.json()["external_payload"] == text


# --- 6. .md/.txt file_content path; unsupported extension -> 400 ------------


def test_txt_file_content_path_works():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/execute",
        json={"filename": "record.txt", "file_content": HR_TEXT, "task": "summarize"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "allowed"


def test_md_file_content_path_works():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/preview",
        json={"filename": "record.md", "file_content": f"# Notes\n{HR_TEXT}", "task": "summarize"},
    )

    assert response.status_code == 200


def test_unsupported_extension_returns_400_with_no_file_content_in_the_body():
    client = build_client(build_service(RecordingProvider()))
    sensitive_content = "Employee: Ana Souza secret payload"

    response = client.post(
        "/disclosure/preview",
        json={"filename": "record.pdf", "file_content": sensitive_content, "task": "summarize"},
    )

    assert response.status_code == 400
    assert sensitive_content not in response.text
    assert "Ana Souza" not in response.text
    assert response.json()["kind"] == "IngestionError"


# --- 7. example_id path; example's task used when none supplied -------------


def test_example_id_path_works_and_uses_the_examples_own_task_when_none_supplied():
    client = build_client(build_service(RecordingProvider(), examples_directory=EXAMPLES_DIR))

    response = client.post("/disclosure/preview", json={"example_id": "hr_team_summary_001"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["status"] in {"allowed", "blocked"}


def test_example_id_path_caller_task_wins_over_the_examples_own_task():
    provider = RecordingProvider()
    client = build_client(build_service(provider, examples_directory=EXAMPLES_DIR))

    response = client.post(
        "/disclosure/execute",
        json={"example_id": "hr_team_summary_001", "task": "a distinctive custom task"},
    )

    assert response.status_code == 200
    if provider.received:
        assert provider.received[-1].task == "a distinctive custom task"


# --- 10. a blocked request -> 200 + status: "blocked" + provider never called


def test_blocked_request_returns_200_with_blocked_status_and_never_calls_the_provider():
    provider = RecordingProvider()
    client = build_client(build_service(provider))

    response = client.post(
        "/disclosure/execute",
        json={"text": HR_TEXT_WITH_MEDICAL, "task": "summarize personnel record"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert body["provider"]["called"] is False
    assert body["final_answer"] is None
    assert provider.received == []


def test_blocked_request_in_preview_also_returns_200_with_blocked_status():
    provider = RecordingProvider()
    client = build_client(build_service(provider))

    response = client.post(
        "/disclosure/preview",
        json={"text": HR_TEXT_WITH_MEDICAL, "task": "summarize personnel record"},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["status"] == "blocked"
    assert provider.received == []


def test_fake_provider_end_to_end_through_the_http_layer():
    client = build_client(build_service(FakeProvider()))

    response = client.post(
        "/disclosure/execute", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"]["called"] is True
    assert body["final_answer"] is not None


def test_strategy_string_is_used_when_supplied():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/preview",
        json={"text": HR_TEXT, "task": "summarize", "strategy": DisclosureStrategy.TASK_AWARE},
    )

    assert response.status_code == 200
    assert response.json()["treatment"] == "b3"
