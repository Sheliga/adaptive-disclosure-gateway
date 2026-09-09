"""T20 / issue #28, slice 3: CLI and HTTP adapters emit the same JSON for
the same input -- proving one shared projection (``application/wire.py``),
not two independently-maintained ones.

This test module (unlike the rest of ``tests/test_cli_*.py``) legitimately
imports ``adaptive_disclosure_gateway.api`` and ``tests.api_support`` -- it
is a test proving the two adapters agree, not the CLI itself, so it is not
subject to the CLI's own "must work without fastapi" constraint (see
``tests/test_cli_architecture.py`` for that pin).
"""

from __future__ import annotations

import json

from adaptive_disclosure_gateway import cli
from tests.api_support import EXAMPLES_DIR, HR_TEXT, RecordingProvider, build_client, build_service


def test_cli_and_http_preview_json_are_identical_for_the_same_input(capsys):
    service = build_service(RecordingProvider())
    client = build_client(service)
    body = {"text": HR_TEXT, "task": "summarize personnel record"}

    http_response = client.post("/disclosure/preview", json=body)

    exit_code = cli.main(
        ["--json", "preview", "--text", body["text"], "--task", body["task"]], service=service
    )

    assert http_response.status_code == 200
    assert exit_code == 0
    cli_output = json.loads(capsys.readouterr().out)
    assert cli_output == http_response.json()


def test_cli_and_http_execute_json_are_identical_for_the_same_input(capsys):
    service = build_service(RecordingProvider())
    client = build_client(service)
    body = {"text": HR_TEXT, "task": "summarize personnel record"}

    http_response = client.post("/disclosure/execute", json=body)

    exit_code = cli.main(
        ["--json", "execute", "--text", body["text"], "--task", body["task"]], service=service
    )

    assert http_response.status_code == 200
    assert exit_code == 0
    cli_output = json.loads(capsys.readouterr().out)
    http_output = http_response.json()
    # total_ms is real wall-clock timing (never reproducible between two
    # independent execute() calls, even for identical input) -- excluded
    # from this equality check; every other field must match exactly.
    cli_output.pop("total_ms")
    http_output.pop("total_ms")
    assert cli_output == http_output


def test_cli_and_http_health_json_are_identical(capsys):
    service = build_service(RecordingProvider())
    client = build_client(service)

    http_response = client.get("/health")
    exit_code = cli.main(["--json", "health"], service=service)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == http_response.json()


def test_cli_and_http_examples_json_are_identical(capsys):
    service = build_service(RecordingProvider(), examples_directory=EXAMPLES_DIR)
    client = build_client(service)

    http_response = client.get("/examples")
    exit_code = cli.main(["--json", "examples"], service=service)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == http_response.json()


def test_cli_and_http_strategies_json_are_identical(capsys):
    service = build_service(RecordingProvider())
    client = build_client(service)

    http_response = client.get("/strategies")
    exit_code = cli.main(["--json", "strategies"], service=service)

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == http_response.json()
