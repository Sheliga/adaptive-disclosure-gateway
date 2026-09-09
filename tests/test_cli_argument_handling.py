"""T20 / issue #28, slice 3: defects found by walking the CLI the way a
person actually types it, rather than the way its own tests happened to
call it.

Every test here failed against the first implementation:

1. ``--json`` was declared only on the top-level parser, so it worked as
   ``adg --json preview ...`` but was an ``unrecognized arguments`` usage
   error as ``adg preview ... --json`` -- the position every other flag on
   the command takes.
2. A missing/unreadable ``--file`` surfaced as the generic "an unexpected
   error occurred" with exit 1, instead of being reported as the bad input
   it is (exit 2) with a message a person can act on.
3. argparse's own ``unrecognized arguments:`` message echoes the offending
   argv entries verbatim -- and for this CLI an unrecognized *positional*
   entry is, in the obvious mistyping (``adg preview "<document text>"``),
   the user's document. argv is already visible to ``ps`` and shell history,
   so this is not a new exposure channel, but this project's no-leak rule
   (CLAUDE.md) is that an error message never carries content, and the CLI's
   stderr is routinely captured into logs where argv is not.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway import cli

from .cli_support import HR_TEXT, SENSITIVE_CPF, SENSITIVE_NAME, build_service


def _run(capsys, argv, service=None):
    code = cli.main(argv, service=service if service is not None else build_service())
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_json_flag_is_accepted_after_the_subcommand(capsys):
    """``adg preview --text ... --json`` -- every other flag on the command
    goes after the subcommand, so this one must too.
    """
    code, out, _err = _run(capsys, ["preview", "--text", HR_TEXT, "--task", "summarize", "--json"])

    assert code == cli.EXIT_OK
    assert '"contract_version"' in out


def test_json_flag_is_still_accepted_before_the_subcommand(capsys):
    """The original position must keep working -- fixing the position above
    must not break the one that already did.
    """
    code, out, _err = _run(capsys, ["--json", "preview", "--text", HR_TEXT, "--task", "summarize"])

    assert code == cli.EXIT_OK
    assert '"contract_version"' in out


def test_json_is_off_by_default_in_both_positions(capsys):
    """Declaring --json on both the top-level parser and each subparser is
    the classic argparse trap: a naive second declaration re-applies its own
    ``False`` default and silently overwrites the value already parsed from
    ``adg --json preview``. Pin that it does not.
    """
    code, out, _err = _run(capsys, ["preview", "--text", HR_TEXT, "--task", "summarize"])

    assert code == cli.EXIT_OK
    assert '"contract_version"' not in out
    assert out.startswith("strategy:")


def test_a_missing_file_is_bad_input_not_an_unexpected_error(capsys, tmp_path: Path):
    missing = tmp_path / "does-not-exist.md"

    code, _out, err = _run(capsys, ["preview", "--file", str(missing), "--task", "summarize"])

    assert code == cli.EXIT_BAD_INPUT
    assert "an unexpected error occurred" not in err
    assert "does-not-exist.md" in err


def test_an_unreadable_file_is_bad_input_not_an_unexpected_error(capsys, tmp_path: Path):
    """A directory passed where a file was expected is the same class of
    caller mistake as a missing path -- both are OSError from read_bytes.
    """
    directory = tmp_path / "notes.md"
    directory.mkdir()

    code, _out, err = _run(capsys, ["preview", "--file", str(directory), "--task", "summarize"])

    assert code == cli.EXIT_BAD_INPUT
    assert "an unexpected error occurred" not in err


def test_an_unrecognized_positional_argument_never_echoes_its_content(capsys):
    """The obvious mistyping -- pasting the document as a positional instead
    of after --text -- must not print the document back out.
    """
    code, out, err = _run(capsys, ["preview", HR_TEXT, "--task", "summarize"])

    assert code == cli.EXIT_BAD_INPUT
    assert SENSITIVE_NAME not in out + err
    assert SENSITIVE_CPF not in out + err


def test_an_unrecognized_option_is_still_named_so_a_typo_is_diagnosable(capsys):
    """Suppressing the content echo must not make a mistyped *flag*
    undiagnosable -- an entry that looks like an option is safe to name (it
    is a flag name, not content) and is the whole value of the message.
    """
    code, out, err = _run(capsys, ["preview", "--text", HR_TEXT, "--tsk", "summarize"])

    assert code == cli.EXIT_BAD_INPUT
    assert "--tsk" in out + err
    assert SENSITIVE_NAME not in out + err
