"""T20 / issue #28, slice 2, no-leak boundary. Requirements 8 and 9.

Asserts against the actual fixture values over the *full raw response
text* -- not just specific fields -- for preview, execute, and every error
response, exactly like ``tests/test_application_service.py``'s own style.
"""

from __future__ import annotations

from tests.api_support import (
    EXAMPLES_DIR,
    HR_TEXT,
    HR_TEXT_WITH_MEDICAL,
    RecordingProvider,
    build_client,
    build_service,
)

SENSITIVE_NAME = "Ana Souza"
SENSITIVE_CPF = "123.456.789-09"
MAPPING_SHAPED = "Ana Souza:"


def test_no_raw_sensitive_value_in_preview_response():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/preview", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    raw = response.text
    assert SENSITIVE_NAME not in raw
    assert SENSITIVE_CPF not in raw
    assert MAPPING_SHAPED not in raw


def test_no_raw_sensitive_value_in_execute_response():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/execute", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    raw = response.text
    assert SENSITIVE_NAME not in raw
    assert SENSITIVE_CPF not in raw
    assert MAPPING_SHAPED not in raw


def test_no_raw_sensitive_value_in_blocked_execute_response():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/execute",
        json={"text": HR_TEXT_WITH_MEDICAL, "task": "summarize personnel record"},
    )

    raw = response.text
    assert SENSITIVE_NAME not in raw
    assert "chronic migraine" not in raw


def test_no_raw_sensitive_value_in_a_400_ingestion_error_response():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/preview",
        json={"filename": "record.pdf", "file_content": HR_TEXT, "task": "summarize"},
    )

    assert response.status_code == 400
    raw = response.text
    assert SENSITIVE_NAME not in raw
    assert SENSITIVE_CPF not in raw


def test_no_raw_sensitive_value_in_a_404_example_not_found_response():
    client = build_client(build_service(RecordingProvider(), examples_directory=EXAMPLES_DIR))

    response = client.post("/disclosure/preview", json={"example_id": "does_not_exist"})

    assert response.status_code == 404
    assert "does_not_exist" in response.text


def test_no_raw_sensitive_value_in_a_content_source_error_response():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/preview",
        json={"text": HR_TEXT, "example_id": "hr_team_summary_001", "task": "summarize"},
    )

    assert response.status_code == 400
    raw = response.text
    assert SENSITIVE_NAME not in raw
    assert SENSITIVE_CPF not in raw


# --- 9. the 422 validation-error body never echoes the submitted input ------


def test_validation_error_body_never_echoes_the_submitted_sensitive_input():
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/preview",
        # `text` must be a string -- an int forces a 422, while embedding a
        # sensitive-looking string as an *invalid* field elsewhere so the
        # scan below is meaningful even though this exact field fails.
        json={"text": 123456789, "task": SENSITIVE_CPF},
    )

    assert response.status_code == 422
    raw = response.text
    assert "123456789" not in raw
    assert SENSITIVE_CPF not in raw
    body = response.json()
    assert "input" not in str(body)
    for error in body["detail"]:
        assert set(error) == {"loc", "type", "msg"}


def test_validation_error_body_never_echoes_a_sensitive_looking_extra_field():
    """A caller-supplied field that fails validation for a different reason
    (here: an unknown/forbidden extra field carrying sensitive-looking
    text) must not have its value echoed either.
    """
    client = build_client(build_service(RecordingProvider()))

    response = client.post(
        "/disclosure/preview",
        json={"task": "summarize", "unexpected_field": SENSITIVE_NAME},
    )

    assert response.status_code == 422
    assert SENSITIVE_NAME not in response.text
