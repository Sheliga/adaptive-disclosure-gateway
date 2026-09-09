"""T20 / issue #28, slice 3: CLI exit codes and the no-leak boundary on
every error path. See ``cli.py``'s module docstring for the exit-code
scheme: 0 completed (including blocked/failed-provider outcomes), 2 bad
input, 1 unexpected error.
"""

from __future__ import annotations

from adaptive_disclosure_gateway import cli
from tests.cli_support import EXAMPLES_DIR, RecordingProvider, build_service

SENSITIVE_CONTENT = "Employee: Ana Souza secret medical payload 123.456.789-09"


# --- 7. bad input paths exit 2 with a safe message and no file content -----


def test_missing_task_for_direct_text_exits_2_with_a_safe_message(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(["preview", "--text", "hello"], service=service)

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "task" in err.lower()


def test_no_content_source_exits_2(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(["preview", "--task", "summarize"], service=service)

    assert exit_code == 2


def test_two_content_sources_exits_2_and_never_echoes_either_content(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        ["preview", "--text", SENSITIVE_CONTENT, "--example", "hr_team_summary_001"],
        service=service,
    )

    assert exit_code == 2
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_CONTENT not in combined


def test_unknown_example_id_exits_2_and_names_only_the_id(capsys):
    service = build_service(RecordingProvider(), examples_directory=EXAMPLES_DIR)

    exit_code = cli.main(["preview", "--example", "does_not_exist"], service=service)

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "does_not_exist" in err


# --- 8. --file with an unsupported extension exits 2 with no content echo --


def test_unsupported_file_extension_exits_2_with_no_content_echoed(capsys, tmp_path):
    service = build_service(RecordingProvider())
    file_path = tmp_path / "record.pdf"
    file_path.write_bytes(SENSITIVE_CONTENT.encode("utf-8"))

    exit_code = cli.main(
        ["preview", "--file", str(file_path), "--task", "summarize"], service=service
    )

    assert exit_code == 2
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_CONTENT not in combined
    assert "Ana Souza" not in combined
    assert ".pdf" in combined


# --- argparse usage errors also exit 2 --------------------------------------


def test_unknown_flag_exits_2():
    service = build_service(RecordingProvider())

    exit_code = cli.main(["preview", "--not-a-real-flag", "x"], service=service)

    assert exit_code == 2


def test_missing_subcommand_exits_2():
    service = build_service(RecordingProvider())

    exit_code = cli.main([], service=service)

    assert exit_code == 2


def test_invalid_strategy_choice_exits_2():
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        ["preview", "--text", "hello", "--task", "x", "--strategy", "not-a-strategy"],
        service=service,
    )

    assert exit_code == 2


# --- 6. an unexpected exception prints no message/traceback, exits 1 -------


def test_unexpected_exception_from_the_service_prints_no_message_and_exits_1(capsys, monkeypatch):
    service = build_service(RecordingProvider())

    sensitive_marker = "super-secret-internal-detail-should-never-appear"

    def _boom(self, request):
        raise RuntimeError(sensitive_marker)

    monkeypatch.setattr(type(service), "preview", _boom)

    exit_code = cli.main(["preview", "--text", "hello", "--task", "summarize"], service=service)

    assert exit_code == 1
    out, err = capsys.readouterr()
    assert sensitive_marker not in out
    assert sensitive_marker not in err
    assert "RuntimeError" not in err
    assert err.strip() != ""


def test_unexpected_exception_exits_1_even_with_json_flag(capsys, monkeypatch):
    service = build_service(RecordingProvider())

    def _boom(self, request):
        raise ValueError("internal detail")

    monkeypatch.setattr(type(service), "preview", _boom)

    exit_code = cli.main(
        ["--json", "preview", "--text", "hello", "--task", "summarize"], service=service
    )

    assert exit_code == 1
    out, err = capsys.readouterr()
    assert "internal detail" not in out
    assert "internal detail" not in err
