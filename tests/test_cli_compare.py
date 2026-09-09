"""T20 / issue #28's "Compare strategies" slice: ``adg compare``.

Mirrors ``tests/test_cli_disclosure.py``'s central "adapter is thin" pin:
the CLI's ``--json`` output must equal the same wire model built directly
from the application service's own ``compare_strategies`` result.
"""

from __future__ import annotations

import json

from adaptive_disclosure_gateway import cli
from adaptive_disclosure_gateway.application.contracts import (
    CANONICAL_COMPARISON_ORDER,
    DisclosureApplicationRequest,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text
from adaptive_disclosure_gateway.application.wire import CompareResponse
from tests.cli_support import HR_TEXT, NeverCallMeProvider, RecordingProvider, build_service


def test_compare_never_calls_the_provider(capsys):
    service = build_service(NeverCallMeProvider())

    exit_code = cli.main(
        ["--json", "compare", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert len(body["entries"]) == 5


def test_compare_returns_entries_in_canonical_order(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        ["--json", "compare", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    body = json.loads(capsys.readouterr().out)
    assert [entry["strategy"] for entry in body["entries"]] == [
        strategy.value for strategy in CANONICAL_COMPARISON_ORDER
    ]


def test_compare_json_output_equals_the_wire_model_of_the_direct_service_result(capsys):
    provider = RecordingProvider()
    service = build_service(provider)

    direct = service.compare_strategies(
        DisclosureApplicationRequest(
            content=normalize_text(HR_TEXT), task="summarize personnel record"
        )
    )
    expected = CompareResponse.from_domain(direct).model_dump()

    exit_code = cli.main(
        ["--json", "compare", "--text", HR_TEXT, "--task", "summarize personnel record"],
        service=service,
    )

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == expected


def test_compare_does_not_advertise_a_strategy_flag():
    """``adg compare`` never runs only one strategy, so it deliberately does
    not accept ``--strategy`` at all -- unlike ``adg preview``/``adg execute``
    (see ``cli.py``'s ``_add_disclosure_arguments``).
    """
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        [
            "compare",
            "--text",
            HR_TEXT,
            "--task",
            "summarize personnel record",
            "--strategy",
            "b2",
        ],
        service=service,
    )

    assert exit_code == 2


def test_compare_human_output_shows_all_five_strategies_and_baseline_marker(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        ["compare", "--text", HR_TEXT, "--task", "summarize personnel record"], service=service
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    for code in ("b0", "b1", "b2", "b3", "b4"):
        assert code in out
    assert "UNSAFE" in out or "unsafe" in out.lower()


def test_compare_human_output_never_shows_the_payload_without_show_payload(capsys):
    service = build_service(RecordingProvider())

    exit_code = cli.main(
        ["compare", "--text", HR_TEXT, "--task", "summarize personnel record"], service=service
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "external_payload" not in out


def test_compare_human_output_shows_the_payload_with_show_payload(capsys):
    service = build_service(RecordingProvider())

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
    out = capsys.readouterr().out
    assert "external_payload" in out
    # B0's payload is the raw document -- deliberately (see the no-leak
    # test module for the full rationale); with --show-payload it appears.
    assert HR_TEXT.strip().splitlines()[0] in out
