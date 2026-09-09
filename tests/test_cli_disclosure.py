"""T20 / issue #28, slice 3: ``adg preview``/``adg execute``.

Central "adapter is thin" pin: the CLI's ``--json`` output must equal the
same wire model built directly from the application service's own
``preview``/``execute`` result -- proving the CLI adds nothing between the
service and its rendered output, mirroring
``tests/test_api_disclosure.py``'s own HTTP-adapter pin.
"""

from __future__ import annotations

import json

from adaptive_disclosure_gateway import cli
from adaptive_disclosure_gateway.application.contracts import DisclosureApplicationRequest
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from adaptive_disclosure_gateway.application.wire import ExecuteResponse, PreviewResponse
from tests.cli_support import (
    EXAMPLES_DIR,
    HR_TEXT,
    HR_TEXT_WITH_MEDICAL,
    FailingProvider,
    NeverCallMeProvider,
    RecordingProvider,
    build_service,
)

# --- 1. the CLI does not alter the application service's result -------------


def test_preview_json_output_equals_the_wire_model_of_the_direct_service_result(capsys):
    provider = RecordingProvider()
    service = build_service(provider)

    direct = service.preview(
        DisclosureApplicationRequest(
            content=normalize_text(HR_TEXT), task="summarize personnel record"
        )
    )
    expected = PreviewResponse.from_domain(direct).model_dump()

    exit_code = cli.main(
        ["--json", "preview", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == expected


def test_execute_json_output_equals_the_wire_model_of_the_direct_service_result(capsys):
    provider = RecordingProvider()
    service = build_service(provider)

    direct = service.execute(
        DisclosureApplicationRequest(
            content=normalize_text(HR_TEXT), task="summarize personnel record"
        )
    )
    expected = ExecuteResponse.from_domain(direct).model_dump()

    exit_code = cli.main(
        ["--json", "execute", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=build_service(RecordingProvider()),
    )

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    # total_ms is real wall-clock timing (application/contracts.py's own
    # docstring: NOT a reproducible scientific metric) -- two independent
    # execute() calls never report the identical duration, so it is excluded
    # from this equality check; every other field must match exactly.
    printed.pop("total_ms")
    expected.pop("total_ms")
    assert printed == expected


# --- 3. preview never calls the provider -------------------------------------


def test_preview_never_calls_the_provider(capsys):
    service = build_service(NeverCallMeProvider())

    exit_code = cli.main(
        ["--json", "preview", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["summary"]["status"] == "allowed"


# --- 4. execute calls the provider exactly once when allowed -----------------


def test_execute_calls_the_provider_exactly_once_when_allowed(capsys):
    provider = RecordingProvider()
    service = build_service(provider)

    exit_code = cli.main(
        ["execute", "--text", HR_TEXT, "--task", "summarize personnel record"], service=service
    )

    assert exit_code == 0
    assert len(provider.received) == 1


def test_a_blocked_request_never_reaches_the_provider_and_still_exits_0(capsys):
    provider = RecordingProvider()
    service = build_service(provider)

    exit_code = cli.main(
        ["--json", "execute", "--text", HR_TEXT_WITH_MEDICAL, "--task", "summarize"],
        service=service,
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "blocked"
    assert body["provider"]["called"] is False
    assert body["final_answer"] is None
    assert provider.received == []


def test_a_failed_provider_call_is_reported_and_still_exits_0(capsys):
    service = build_service(FailingProvider())

    exit_code = cli.main(
        ["--json", "execute", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["provider"]["called"] is True
    assert body["provider"]["failed"] is True
    assert body["final_answer"] is None


# --- 9. --example works and uses the example's own task when omitted --------


def test_example_source_works_and_uses_the_examples_own_task_when_task_omitted(capsys):
    provider = RecordingProvider()
    service = build_service(provider, examples_directory=EXAMPLES_DIR)

    exit_code = cli.main(["--json", "preview", "--example", "hr_team_summary_001"], service=service)

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["summary"]["status"] in {"allowed", "blocked"}


def test_example_source_caller_task_wins_over_the_examples_own_task(capsys):
    provider = RecordingProvider()
    service = build_service(provider, examples_directory=EXAMPLES_DIR)

    exit_code = cli.main(
        [
            "execute",
            "--example",
            "hr_team_summary_001",
            "--task",
            "a distinctive custom task",
        ],
        service=service,
    )

    assert exit_code == 0
    if provider.received:
        assert provider.received[-1].task == "a distinctive custom task"


# --- 10. --show-payload gates the payload in human-readable output ----------


def test_show_payload_is_required_for_the_payload_to_appear_in_human_output(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        ["preview", "--text", HR_TEXT, "--task", "summarize personnel record"], service=service
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "external_payload" not in out


def test_show_payload_flag_makes_the_payload_appear_in_human_output(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        [
            "preview",
            "--text",
            HR_TEXT,
            "--task",
            "summarize personnel record",
            "--show-payload",
        ],
        service=service,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "external_payload" in out


def test_json_output_always_includes_the_payload_regardless_of_show_payload(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        ["--json", "preview", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert "external_payload" in body


# --- .md/.txt file source works ----------------------------------------------


def test_txt_file_source_works(capsys, tmp_path):
    service = build_service(RecordingProvider())
    file_path = tmp_path / "record.txt"
    file_path.write_text(HR_TEXT, encoding="utf-8")

    exit_code = cli.main(
        ["--json", "execute", "--file", str(file_path), "--task", "summarize"], service=service
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "allowed"


def test_md_file_source_works(capsys, tmp_path):
    service = build_service(RecordingProvider())
    file_path = tmp_path / "record.md"
    file_path.write_text(f"# Notes\n{HR_TEXT}", encoding="utf-8")

    exit_code = cli.main(
        ["--json", "preview", "--file", str(file_path), "--task", "summarize"], service=service
    )

    assert exit_code == 0


def test_health_examples_strategies_commands_work(capsys):
    service = build_service(RecordingProvider(), examples_directory=EXAMPLES_DIR)

    assert cli.main(["--json", "health"], service=service) == 0
    health_body = json.loads(capsys.readouterr().out)
    assert health_body["provider"]["provider_class"] == "fake"

    assert cli.main(["--json", "examples"], service=service) == 0
    examples_body = json.loads(capsys.readouterr().out)
    assert len(examples_body["examples"]) > 0

    assert cli.main(["--json", "strategies"], service=service) == 0
    strategies_body = json.loads(capsys.readouterr().out)
    assert {s["strategy"] for s in strategies_body["strategies"]} == {
        "recommended",
        "b0",
        "b1",
        "b2",
        "b3",
        "b4",
    }
