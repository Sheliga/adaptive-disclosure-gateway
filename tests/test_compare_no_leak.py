"""T20 / issue #28's "Compare strategies" slice: no-leak boundary across the
service, HTTP and CLI surfaces.

CRITICAL nuance -- read before "fixing" any of this: B0 -- Direct's own
``external_payload`` is, by design, the raw submitted document, containing
raw sensitive values verbatim. That is intended behavior, identical to the
existing contract ``preview()`` already has for B0 (``external_payload`` =
"exactly what would be sent"), returned to the same caller who supplied the
content, and it is the entire educational point of this comparison -- see
``application/contracts.py``'s and ``application/service.py``'s module
docstrings. So the assertions below are precise, not naive:

- B0's ``external_payload`` is pinned to equal the submitted text verbatim
  (raw values included) -- this is INTENDED, not a bug to "fix" later.
- Every OTHER field of the response -- every other entry's own payload,
  every summary, every governance/provider_mode field -- is asserted to
  never carry a raw sensitive value.
- No original<->pseudonym mapping (a raw value alongside its pseudonym in
  one structure) appears anywhere.
- No ``requester_id``/``session_id``/``document_id``/``request_id`` appears
  anywhere.
- The CLI's default (no ``--show-payload``) human-readable output never
  prints the raw document, for B0 or any other entry.
"""

from __future__ import annotations

import dataclasses
import json

from adaptive_disclosure_gateway import cli
from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureStrategy,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from tests.api_support import build_client
from tests.api_support import build_service as build_api_service
from tests.cli_support import (
    HR_TEXT,
    MAPPING_SHAPED,
    SENSITIVE_CPF,
    SENSITIVE_NAME,
    RecordingProvider,
)
from tests.cli_support import build_service as build_cli_service

DISTINCTIVE_REQUESTER_ID = "requester-secret-analyst-77"
DISTINCTIVE_SESSION_ID = "session-secret-88"
DISTINCTIVE_DOCUMENT_ID = "document-secret-99"
DISTINCTIVE_REQUEST_ID = "request-secret-00"

_DISTINCTIVE_IDENTIFIERS = (
    DISTINCTIVE_REQUESTER_ID,
    DISTINCTIVE_SESSION_ID,
    DISTINCTIVE_DOCUMENT_ID,
    DISTINCTIVE_REQUEST_ID,
)


def _app_request(
    text: str, task: str = "summarize personnel record"
) -> DisclosureApplicationRequest:
    return DisclosureApplicationRequest(content=normalize_text(text), task=task)


# --- service layer ------------------------------------------------------------


def test_service_b0_entry_external_payload_is_deliberately_the_raw_submitted_text():
    service = build_cli_service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))

    b0_entry = comparison.entries[0]
    assert b0_entry.strategy is DisclosureStrategy.DIRECT
    assert b0_entry.external_payload == HR_TEXT


def test_service_no_field_other_than_b0_payload_carries_a_raw_sensitive_value():
    service = build_cli_service(RecordingProvider())

    comparison = service.compare_strategies(_app_request(HR_TEXT))
    assert comparison.entries[0].strategy is DisclosureStrategy.DIRECT

    dumped = dataclasses.asdict(comparison)
    dumped["entries"][0]["external_payload"] = "<b0-payload-excluded-from-this-scan>"
    scanned = str(dumped)

    assert SENSITIVE_NAME not in scanned
    assert SENSITIVE_CPF not in scanned
    assert MAPPING_SHAPED not in scanned


def test_service_result_never_carries_a_lifecycle_identifier():
    service = build_cli_service(
        RecordingProvider(),
        requester_id=DISTINCTIVE_REQUESTER_ID,
        session_id=DISTINCTIVE_SESSION_ID,
        document_id=DISTINCTIVE_DOCUMENT_ID,
        request_id=DISTINCTIVE_REQUEST_ID,
    )

    comparison = service.compare_strategies(_app_request(HR_TEXT))
    scanned = str(dataclasses.asdict(comparison))

    for identifier in _DISTINCTIVE_IDENTIFIERS:
        assert identifier not in scanned


# --- HTTP layer -----------------------------------------------------------------


def test_http_compare_b0_entry_external_payload_is_deliberately_the_raw_submitted_text():
    client = build_client(build_api_service(RecordingProvider()))

    response = client.post(
        "/disclosure/compare", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    body = response.json()
    b0_entry = body["entries"][0]
    assert b0_entry["strategy"] == "b0"
    assert b0_entry["external_payload"] == HR_TEXT


def test_http_compare_no_field_other_than_b0_payload_carries_a_raw_sensitive_value():
    client = build_client(build_api_service(RecordingProvider()))

    response = client.post(
        "/disclosure/compare", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    body = response.json()
    assert body["entries"][0]["strategy"] == "b0"
    body["entries"][0]["external_payload"] = "<b0-payload-excluded-from-this-scan>"
    scanned = json.dumps(body)

    assert SENSITIVE_NAME not in scanned
    assert SENSITIVE_CPF not in scanned
    assert MAPPING_SHAPED not in scanned


def test_http_compare_response_never_carries_a_lifecycle_identifier():
    client = build_client(
        build_api_service(
            RecordingProvider(),
            requester_id=DISTINCTIVE_REQUESTER_ID,
            session_id=DISTINCTIVE_SESSION_ID,
            document_id=DISTINCTIVE_DOCUMENT_ID,
            request_id=DISTINCTIVE_REQUEST_ID,
        )
    )

    response = client.post(
        "/disclosure/compare", json={"text": HR_TEXT, "task": "summarize personnel record"}
    )

    raw = response.text
    for identifier in _DISTINCTIVE_IDENTIFIERS:
        assert identifier not in raw


# --- CLI layer ------------------------------------------------------------------


def test_cli_compare_human_output_never_shows_the_raw_document_without_show_payload(capsys):
    service = build_cli_service(RecordingProvider())

    exit_code = cli.main(
        ["compare", "--text", HR_TEXT, "--task", "summarize personnel record"], service=service
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    # B0's own payload is the raw document -- without --show-payload, no
    # entry's payload (B0's included) is printed at all.
    assert SENSITIVE_NAME not in out
    assert SENSITIVE_CPF not in out
    assert HR_TEXT not in out


def test_cli_compare_json_output_deliberately_includes_b0s_raw_payload_but_nothing_else_raw(capsys):
    service = build_cli_service(RecordingProvider())

    exit_code = cli.main(
        ["--json", "compare", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    b0_entry = body["entries"][0]
    assert b0_entry["strategy"] == "b0"
    assert b0_entry["external_payload"] == HR_TEXT

    body["entries"][0]["external_payload"] = "<b0-payload-excluded-from-this-scan>"
    scanned = json.dumps(body)
    assert SENSITIVE_NAME not in scanned
    assert SENSITIVE_CPF not in scanned
    assert MAPPING_SHAPED not in scanned


def test_cli_compare_show_payload_human_output_still_has_no_sensitive_value_outside_b0():
    """With --show-payload, B0's block legitimately prints the raw document
    -- but the human-readable rendering never prints anything from a policy
    decision's own reasoning text or any other entry's payload that would
    carry a raw value.
    """
    import io
    from contextlib import redirect_stdout

    service = build_cli_service(RecordingProvider())
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cli.main(
            [
                "compare",
                "--text",
                HR_TEXT,
                "--task",
                "summarize personnel record",
                "--show-payload",
            ],
            service=service,
        )
    assert exit_code == 0
    out = buffer.getvalue()

    # Split on each strategy's own block header and check every block other
    # than b0's for the raw sensitive values.
    blocks = out.split("=== b")
    non_b0_blocks = [f"b{block}" for block in blocks[1:] if not block.startswith("0 ")]
    for block in non_b0_blocks:
        assert SENSITIVE_NAME not in block
        assert SENSITIVE_CPF not in block


def test_cli_compare_never_prints_a_lifecycle_identifier(capsys):
    service = build_cli_service(
        RecordingProvider(),
        requester_id=DISTINCTIVE_REQUESTER_ID,
        session_id=DISTINCTIVE_SESSION_ID,
        document_id=DISTINCTIVE_DOCUMENT_ID,
        request_id=DISTINCTIVE_REQUEST_ID,
    )

    exit_code = cli.main(
        ["--json", "compare", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    for identifier in _DISTINCTIVE_IDENTIFIERS:
        assert identifier not in out
