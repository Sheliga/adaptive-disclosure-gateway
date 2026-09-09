"""T20 / issue #28, slice 3, no-leak boundary on the CLI adapter. Mirrors
``tests/test_api_no_leak.py``'s style: asserts against the actual fixture
sensitive values over the *full captured stdout+stderr* -- not just
specific fields -- for preview, execute, ``--json``, ``--show-payload``
omitted, and every error path.
"""

from __future__ import annotations

from adaptive_disclosure_gateway import cli
from tests.cli_support import (
    EXAMPLES_DIR,
    HR_TEXT,
    HR_TEXT_WITH_MEDICAL,
    MAPPING_SHAPED,
    SENSITIVE_CPF,
    SENSITIVE_NAME,
    RecordingProvider,
    build_service,
)


def _run(argv, service):
    exit_code = cli.main(argv, service=service)
    return exit_code


def test_no_raw_sensitive_value_in_preview_human_output_without_show_payload(capsys):
    service = build_service(RecordingProvider())

    exit_code = _run(
        ["preview", "--text", HR_TEXT, "--task", "summarize personnel record"], service
    )

    assert exit_code == 0
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_NAME not in combined
    assert SENSITIVE_CPF not in combined
    assert MAPPING_SHAPED not in combined


def test_no_raw_sensitive_value_in_preview_json_output(capsys):
    service = build_service(RecordingProvider())

    exit_code = _run(
        ["--json", "preview", "--text", HR_TEXT, "--task", "summarize personnel record"], service
    )

    assert exit_code == 0
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_NAME not in combined
    assert SENSITIVE_CPF not in combined
    assert MAPPING_SHAPED not in combined


def test_no_raw_sensitive_value_in_preview_json_output_even_with_show_payload(capsys):
    service = build_service(RecordingProvider())

    exit_code = _run(
        [
            "--json",
            "preview",
            "--text",
            HR_TEXT,
            "--task",
            "summarize personnel record",
            "--show-payload",
        ],
        service,
    )

    assert exit_code == 0
    combined = "".join(capsys.readouterr())
    # external_payload is the treatment's own transformed output (e.g. a
    # pseudonym), never the raw original -- so the RAW sensitive values must
    # still never appear even though the payload itself is now included.
    assert SENSITIVE_NAME not in combined
    assert SENSITIVE_CPF not in combined
    assert MAPPING_SHAPED not in combined


def test_no_raw_sensitive_value_in_execute_output(capsys):
    service = build_service(RecordingProvider())

    exit_code = _run(
        ["--json", "execute", "--text", HR_TEXT, "--task", "summarize personnel record"], service
    )

    assert exit_code == 0
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_NAME not in combined
    assert SENSITIVE_CPF not in combined
    assert MAPPING_SHAPED not in combined


def test_no_raw_sensitive_value_in_blocked_execute_output(capsys):
    service = build_service(RecordingProvider())

    exit_code = _run(
        [
            "--json",
            "execute",
            "--text",
            HR_TEXT_WITH_MEDICAL,
            "--task",
            "summarize personnel record",
        ],
        service,
    )

    assert exit_code == 0
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_NAME not in combined
    assert "chronic migraine" not in combined


def test_no_raw_sensitive_value_in_a_bad_input_error_path(capsys, tmp_path):
    service = build_service(RecordingProvider())
    file_path = tmp_path / "record.pdf"
    file_path.write_text(HR_TEXT, encoding="utf-8")

    exit_code = _run(["preview", "--file", str(file_path), "--task", "summarize"], service)

    assert exit_code == 2
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_NAME not in combined
    assert SENSITIVE_CPF not in combined


def test_no_raw_sensitive_value_in_a_content_source_error_path(capsys):
    service = build_service(RecordingProvider())

    exit_code = _run(
        ["preview", "--text", HR_TEXT, "--example", "hr_team_summary_001", "--task", "summarize"],
        service,
    )

    assert exit_code == 2
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_NAME not in combined
    assert SENSITIVE_CPF not in combined


def test_no_raw_sensitive_value_in_an_unknown_example_error_path(capsys):
    service = build_service(RecordingProvider(), examples_directory=EXAMPLES_DIR)

    exit_code = _run(["preview", "--example", "does_not_exist"], service)

    assert exit_code == 2
    combined = "".join(capsys.readouterr())
    assert SENSITIVE_NAME not in combined
    assert SENSITIVE_CPF not in combined
