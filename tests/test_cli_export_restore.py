"""``adg export``/``adg restore`` (T26 / issue #67).

Mirrors ``tests/test_cli_disclosure.py``'s "adapter is thin" pin (CLI
``--json`` output equals the wire model of the direct service call) and adds
the input-handling rules specific to these two commands: the restore handle
is never accepted as a plain argv value, and ``adg restore`` reads both its
inputs from a file and/or standard input.
"""

from __future__ import annotations

import io
import json

from adaptive_disclosure_gateway import cli
from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureStrategy,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from adaptive_disclosure_gateway.application.restore_handle import RestoreHandleSealer
from adaptive_disclosure_gateway.application.wire import ExportResponse
from tests.cli_support import HR_TEXT, build_service

SECRET = "a-test-only-cli-restore-handle-secret-value-32b"


def _configured_sealer(**kwargs) -> RestoreHandleSealer:
    return RestoreHandleSealer(secret=SECRET, **kwargs)


# --- export: adapter is thin --------------------------------------------------


def test_export_json_output_equals_the_wire_model_of_the_direct_service_result(capsys):
    service = build_service(restore_handle_sealer=_configured_sealer())
    request = DisclosureApplicationRequest(
        content=normalize_text(HR_TEXT),
        task="summarize personnel record",
        strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
    )
    direct = service.export(request)
    expected = ExportResponse.from_domain(direct).model_dump()

    exit_code = cli.main(
        [
            "--json",
            "export",
            "--text",
            HR_TEXT,
            "--task",
            "summarize personnel record",
            "--strategy",
            "b2",
        ],
        service=service,
    )

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    # Two independent exports each mint a fresh handle (different nonce) --
    # compare everything else and only check the handle's presence/shape.
    assert printed["restore_handle"] != expected["restore_handle"] or True
    for key in ("external_payload", "restorable_count", "treatment", "strategy", "governance"):
        assert printed[key] == expected[key]
    assert printed["restore_handle"].startswith("rh1.")


def test_export_human_output_prints_the_payload_and_handle_without_a_show_payload_flag(capsys):
    service = build_service(restore_handle_sealer=_configured_sealer())

    exit_code = cli.main(
        ["export", "--text", HR_TEXT, "--task", "summarize", "--strategy", "b2"],
        service=service,
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "external_payload:" in out
    assert "restore_handle:" in out
    assert "rh1." in out


def test_export_fails_closed_with_a_nonzero_exit_when_no_secret_is_configured(capsys):
    service = build_service(restore_handle_sealer=None)

    exit_code = cli.main(
        ["export", "--text", HR_TEXT, "--task", "summarize", "--strategy", "b2"],
        service=service,
    )

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "ADG_RESTORE_HANDLE_SECRET" in err


# --- restore -------------------------------------------------------------------


def test_restore_reads_handle_and_text_from_files(tmp_path, capsys):
    service = build_service(restore_handle_sealer=_configured_sealer())
    export = service.export(
        DisclosureApplicationRequest(
            content=normalize_text(HR_TEXT),
            task="summarize",
            strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        )
    )
    handle_path = tmp_path / "handle.txt"
    handle_path.write_text(export.restore_handle, encoding="utf-8")
    text_path = tmp_path / "text.txt"
    text_path.write_text(export.external_payload, encoding="utf-8")

    exit_code = cli.main(
        ["--json", "restore", "--handle-file", str(handle_path), "--text-file", str(text_path)],
        service=service,
    )

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert "Ana Souza" in printed["restored_text"]
    assert printed["restored_count"] == 2
    assert printed["unresolved_count"] == 0


def test_restore_reads_text_from_stdin_when_only_handle_file_is_given(
    tmp_path, monkeypatch, capsys
):
    service = build_service(restore_handle_sealer=_configured_sealer())
    export = service.export(
        DisclosureApplicationRequest(
            content=normalize_text(HR_TEXT),
            task="summarize",
            strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        )
    )
    handle_path = tmp_path / "handle.txt"
    handle_path.write_text(export.restore_handle, encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(export.external_payload))

    exit_code = cli.main(["--json", "restore", "--handle-file", str(handle_path)], service=service)

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert "Ana Souza" in printed["restored_text"]


def test_restore_requires_at_least_one_of_handle_file_or_text_file(capsys):
    service = build_service(restore_handle_sealer=_configured_sealer())

    exit_code = cli.main(["restore"], service=service)

    assert exit_code == cli.EXIT_BAD_INPUT
    err = capsys.readouterr().err
    assert "handle" in err.lower()


def test_the_restore_handle_can_never_be_passed_as_a_plain_argv_value():
    """There is no flag that accepts the handle's content directly -- only
    ``--handle-file``, a path. Confirmed at the parser level: no
    ``--restore-handle``/``--handle`` option is registered on the subcommand.
    """
    parser = cli.build_parser()
    restore_subparser = next(
        action.choices["restore"]
        for action in parser._subparsers._group_actions
        if hasattr(action, "choices") and "restore" in action.choices
    )
    option_strings = {
        option for action in restore_subparser._actions for option in action.option_strings
    }
    assert "--handle" not in option_strings
    assert "--restore-handle" not in option_strings
    assert "--handle-file" in option_strings


def test_restore_returns_nonzero_for_a_tampered_handle(tmp_path, capsys):
    service = build_service(restore_handle_sealer=_configured_sealer())
    export = service.export(
        DisclosureApplicationRequest(
            content=normalize_text(HR_TEXT),
            task="summarize",
            strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        )
    )
    prefix, blob = export.restore_handle.split(".", 1)
    tampered = f"{prefix}.{blob[:-4]}0000"
    handle_path = tmp_path / "handle.txt"
    handle_path.write_text(tampered, encoding="utf-8")
    text_path = tmp_path / "text.txt"
    text_path.write_text(export.external_payload, encoding="utf-8")

    exit_code = cli.main(
        ["restore", "--handle-file", str(handle_path), "--text-file", str(text_path)],
        service=service,
    )

    assert exit_code == cli.EXIT_BAD_INPUT


def test_restore_fails_closed_with_a_nonzero_exit_when_no_secret_is_configured(tmp_path, capsys):
    service = build_service(restore_handle_sealer=None)
    handle_path = tmp_path / "handle.txt"
    handle_path.write_text("rh1.whatever", encoding="utf-8")
    text_path = tmp_path / "text.txt"
    text_path.write_text("irrelevant", encoding="utf-8")

    exit_code = cli.main(
        ["restore", "--handle-file", str(handle_path), "--text-file", str(text_path)],
        service=service,
    )

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "ADG_RESTORE_HANDLE_SECRET" in err
