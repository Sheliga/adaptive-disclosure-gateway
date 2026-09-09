"""The CLI adapter over ``DisclosureApplicationService`` (T20 / issue #28,
slice 3): "a CLI suitable for local development, controlled runs and
debugging".

    CLI adapter  ->  DisclosureApplicationService  ->  existing core
    HTTP adapter ->  (the same service)            ->  (the same core)

Every command below does exactly this: parse argv, call exactly one
application-service method, render the result, map a known exception to an
exit code. Nothing else -- no treatment selection, no policy reasoning, no
summary building, no payload manipulation. Compare ``api/app.py``, this
module's sibling adapter, which follows the identical shape over HTTP.

This module deliberately never imports anything under
``adaptive_disclosure_gateway.api`` (which imports ``fastapi`` transitively
through ``api/__init__.py``) or ``fastapi``/``starlette`` directly, so the
CLI works in an environment with no ``fastapi`` installed at all -- pinned
by ``tests/test_cli_architecture.py``. It uses only stdlib ``argparse``: no
new third-party dependency (``click``/``typer``/``rich``) was added for
this.

``--json`` output is never a second, hand-rolled JSON shape: it is the
same allowlisted wire projection (``application/wire.py``) the HTTP API
serializes, via each model's own ``model_dump_json`` -- so CLI and HTTP
output are byte-identical for the same input. See ``application/wire.py``'s
module docstring for why that projection lives in the application layer
rather than being duplicated per adapter.

Exit codes:

- ``0`` -- the use case completed. This includes a **blocked** disclosure
  and a **failed provider call**: both are legitimate recorded outcomes,
  reported in the output, exactly as the HTTP adapter returns 200 for them.
  Adapter consistency is the point -- a CLI script polling for "did this
  fail" must not have to special-case a blocked/failed-provider result as an
  error just because this adapter is a terminal instead of HTTP.
- ``2`` -- bad input: ``IngestionError``, ``ContentSourceError``,
  ``MissingTaskError``, ``ExampleNotFoundError``, or an argparse usage error
  (unknown flag, missing required subcommand, invalid choice).
- ``1`` -- an unexpected error from deeper in the stack.

No-leak boundary (CLAUDE.md) on this adapter's error path: a bad-input
exception's own message is printed as-is because those exception types
already guarantee it names only a category/extension/count/id -- never
content (see each exception's own docstring in ``application/ingestion.py``/
``application/requests.py``/``application/examples.py``). An *unexpected*
exception's message is never printed -- only a fixed, generic string --
because an exception from deep in the stack (detection, a treatment, the
vault) could carry document content in its own ``str()``; this boundary must
not trust that it doesn't, exactly the same reasoning as the HTTP adapter's
catch-all ``Exception`` handler in ``api/app.py``. Errors go to stderr;
results go to stdout.

``--file`` reads the file's bytes into memory and passes them straight to
``service.build_application_request`` as ``file_bytes`` -- it is never
persisted, copied, or written anywhere else by this module.

``--show-payload`` gates whether the human-readable ``preview`` renderer
prints ``external_payload``. The payload itself is not sensitive relative to
the caller -- it is exactly what ``--json``/the HTTP API return to the same
caller who supplied the content, and returning it is the whole point of a
"review before sending" preview. But a CLI prints to a terminal, which may
be logged, captured in a screen share, or scrolled back into shell history
in a way an HTTP JSON response body is not, so this adapter makes the
human-readable rendering opt-in rather than dumping it by default. ``--json``
output always includes it, matching the HTTP contract exactly.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from adaptive_disclosure_gateway.application import wire
from adaptive_disclosure_gateway.application.contracts import (
    DisclosureExecution,
    DisclosurePreview,
    DisclosureStrategy,
    GovernanceOverrides,
    StrategyOption,
)
from adaptive_disclosure_gateway.application.examples import ExampleNotFoundError, ExampleSummary
from adaptive_disclosure_gateway.application.ingestion import IngestionError
from adaptive_disclosure_gateway.application.requests import ContentSourceError, MissingTaskError
from adaptive_disclosure_gateway.application.service import (
    DisclosureApplicationService,
    ServiceHealth,
)
from adaptive_disclosure_gateway.application.settings import build_default_service
from adaptive_disclosure_gateway.domain import PseudonymScope

EXIT_OK = 0
EXIT_UNEXPECTED_ERROR = 1
EXIT_BAD_INPUT = 2


# Every exception build_application_request/service.load_example may raise
# for bad caller input -- see the module docstring's no-leak boundary. Never
# includes anything provider- or core-raised: those are unexpected errors.
class FileReadError(Exception):
    """Raised when ``--file`` names a path this process cannot read at all
    (missing, a directory, permission denied). Distinct from
    ``IngestionError``, which is about content this CLI *did* read and the
    application layer refused to normalize: reading from disk is a CLI
    concern the application boundary deliberately has no part in (it accepts
    bytes, never a path). Messages name the path and the OSError kind only.
    """


_BAD_INPUT_EXCEPTIONS = (
    FileReadError,
    IngestionError,
    ContentSourceError,
    MissingTaskError,
    ExampleNotFoundError,
)

_EPILOG = """\
exit codes:
  0  the use case completed (including a blocked disclosure or a failed
     provider call -- both are legitimate recorded outcomes, not errors)
  2  bad input (unsupported content, missing task, unknown example, or a
     usage error such as an invalid flag or choice)
  1  an unexpected error
"""


# --- argument parsing -------------------------------------------------------


def _add_content_source_arguments(parser: argparse.ArgumentParser) -> None:
    # Deliberately three independent optional arguments, not an argparse
    # mutually-exclusive group: which single source is valid is application
    # logic already enforced by service.build_application_request (raising
    # ContentSourceError) -- re-implementing "exactly one required" here
    # would duplicate that rule in argparse and could disagree with it.
    group = parser.add_argument_group("content source (exactly one required)")
    group.add_argument("--text", help="disclose this literal text")
    group.add_argument(
        "--file", type=Path, metavar="PATH", help="disclose the contents of this .txt/.md file"
    )
    group.add_argument("--example", metavar="EXAMPLE_ID", help="disclose this prepared example")


def _add_governance_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("governance overrides")
    group.add_argument("--purpose")
    group.add_argument("--requester-role")
    group.add_argument("--requester-id")
    group.add_argument("--provider-class")
    group.add_argument("--policy-version")
    group.add_argument(
        "--pseudonym-scope", choices=[scope.value for scope in PseudonymScope], default=None
    )
    group.add_argument("--session-id")
    group.add_argument("--document-id")
    group.add_argument("--request-id")
    group.add_argument("--domain")


def _add_json_argument(parser: argparse.ArgumentParser, *, suppress_default: bool) -> None:
    """Declare ``--json`` on ``parser``.

    It is declared twice on purpose -- once on the top-level parser and once
    on every subparser -- so both ``adg --json preview ...`` and
    ``adg preview ... --json`` work. Every *other* flag on a command goes
    after the subcommand, so a user naturally types this one there too, and
    a top-level-only declaration made that an ``unrecognized arguments``
    usage error.

    ``suppress_default`` guards the classic argparse trap that makes the
    double declaration wrong if done naively: a subparser re-applies its own
    ``store_true`` default, silently overwriting a ``True`` the top-level
    parser already parsed from ``adg --json preview``. ``SUPPRESS`` makes the
    subparser set the attribute only when the flag is actually present, so
    the top-level value survives untouched -- pinned by
    ``tests/test_cli_argument_handling.py::test_json_is_off_by_default_in_both_positions``.
    """
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS if suppress_default else False,
        help="print the same wire model the HTTP API returns",
    )


def _add_disclosure_arguments(parser: argparse.ArgumentParser) -> None:
    _add_json_argument(parser, suppress_default=True)
    _add_content_source_arguments(parser)
    parser.add_argument("--task", help="the task the disclosed content is for")
    parser.add_argument(
        "--strategy",
        choices=[strategy.value for strategy in DisclosureStrategy],
        default=DisclosureStrategy.RECOMMENDED.value,
    )
    _add_governance_arguments(parser)
    parser.add_argument(
        "--show-payload",
        action="store_true",
        help="also print the external payload in human-readable output (see module docstring)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adg",
        description="Adaptive Disclosure Gateway CLI -- local development, controlled runs "
        "and debugging over the same DisclosureApplicationService the HTTP API uses.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_json_argument(parser, suppress_default=False)

    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("health", "provider/treatment introspection"),
        ("examples", "list prepared examples"),
        ("strategies", "list available B0-B4 strategies"),
    ):
        _add_json_argument(subparsers.add_parser(name, help=help_text), suppress_default=True)

    preview_parser = subparsers.add_parser(
        "preview", help="run only the decision phase; never calls the provider"
    )
    _add_disclosure_arguments(preview_parser)

    execute_parser = subparsers.add_parser(
        "execute", help="run the request through the real pipeline, provider call included"
    )
    _add_disclosure_arguments(execute_parser)

    return parser


def _governance_overrides_from_args(args: argparse.Namespace) -> GovernanceOverrides:
    return GovernanceOverrides(
        purpose=args.purpose,
        requester_role=args.requester_role,
        requester_id=args.requester_id,
        provider_class=args.provider_class,
        policy_version=args.policy_version,
        requested_pseudonym_scope=PseudonymScope(args.pseudonym_scope)
        if args.pseudonym_scope is not None
        else None,
        session_id=args.session_id,
        document_id=args.document_id,
        request_id=args.request_id,
        domain=args.domain,
    )


def _build_application_request(service: DisclosureApplicationService, args: argparse.Namespace):
    filename: str | None = None
    file_bytes: bytes | None = None
    if args.file is not None:
        # Read into memory only -- never persisted or copied elsewhere (see
        # module docstring). `.name` is the basename, matching what the HTTP
        # adapter's `filename` field carries.
        try:
            file_bytes = args.file.read_bytes()
        except OSError as exc:
            # A path that does not exist, is a directory, or cannot be read
            # is a caller mistake, not an unexpected failure -- reporting it
            # as the generic "an unexpected error occurred" (exit 1) told a
            # user nothing and mis-classified it. Names the path (the
            # caller's own argv, and the only thing that makes the message
            # actionable) and the OSError kind -- never file content, which
            # was never read. `from None` breaks the chain so no stdlib
            # message reaches the caller either.
            raise FileReadError(
                f"could not read --file {args.file}: {type(exc).__name__}"
            ) from None
        filename = args.file.name

    return service.build_application_request(
        text=args.text,
        filename=filename,
        file_bytes=file_bytes,
        example_id=args.example,
        task=args.task,
        strategy=DisclosureStrategy(args.strategy),
        governance=_governance_overrides_from_args(args),
    )


# --- human-readable rendering -----------------------------------------------


def _print_health_human(health: ServiceHealth) -> None:
    print(f"provider_class: {health.provider_class}")
    print(f"model_id: {health.model_id}")
    print(f"model_snapshot: {health.model_snapshot}")
    print(f"deterministic_demo_mode: {health.deterministic_demo_mode}")
    print(f"treatments_available: {', '.join(t.value for t in health.treatments_available)}")


def _print_examples_human(examples: tuple[ExampleSummary, ...]) -> None:
    if not examples:
        print("(no examples configured)")
        return
    for example in examples:
        print(
            f"{example.example_id}  domain={example.domain}  purpose={example.purpose}  "
            f"task={example.task!r}  chars={example.character_count}"
        )


def _print_strategies_human(options: tuple[StrategyOption, ...]) -> None:
    for option in options:
        marker = " (recommended)" if option.recommended else ""
        print(f"{option.strategy.value} -> {option.treatment.value}{marker}")


def _print_preview_human(preview: DisclosurePreview, *, show_payload: bool) -> None:
    print(f"strategy: {preview.strategy.value}")
    print(f"treatment: {preview.treatment.value}")
    print(f"status: {preview.summary.status}")
    print("categories:")
    if not preview.summary.categories:
        print("  (none detected)")
    for category in preview.summary.categories:
        print(
            f"  - {category.category}: {category.outcome.value} "
            f"(occurrences={category.occurrence_count}, "
            f"crosses_trust_boundary={category.crosses_trust_boundary})"
        )
    print(f"payload_byte_count: {preview.payload_byte_count}")
    if show_payload:
        print("external_payload:")
        print(preview.external_payload)


def _print_execute_human(execution: DisclosureExecution) -> None:
    print(f"strategy: {execution.strategy.value}")
    print(f"treatment: {execution.treatment.value}")
    print(f"status: {execution.summary.status}")
    print(f"provider_called: {execution.provider.called}")
    print(f"provider_failed: {execution.provider.failed}")
    if execution.provider.failure_kind is not None:
        print(f"provider_failure_kind: {execution.provider.failure_kind}")
    print(f"reconstruction_attempted: {execution.reconstruction.attempted}")
    print(f"final_answer: {execution.final_answer}")


# --- command handlers --------------------------------------------------------


def _cmd_health(service: DisclosureApplicationService, args: argparse.Namespace) -> int:
    health = service.describe_health()
    if args.json:
        print(wire.HealthResponse.from_domain(health).model_dump_json(indent=2))
    else:
        _print_health_human(health)
    return EXIT_OK


def _cmd_examples(service: DisclosureApplicationService, args: argparse.Namespace) -> int:
    examples = service.list_examples()
    if args.json:
        print(wire.ExamplesResponse.from_domain(examples).model_dump_json(indent=2))
    else:
        _print_examples_human(examples)
    return EXIT_OK


def _cmd_strategies(service: DisclosureApplicationService, args: argparse.Namespace) -> int:
    options = service.list_strategies()
    if args.json:
        print(wire.StrategiesResponse.from_domain(options).model_dump_json(indent=2))
    else:
        _print_strategies_human(options)
    return EXIT_OK


def _cmd_preview(service: DisclosureApplicationService, args: argparse.Namespace) -> int:
    request = _build_application_request(service, args)
    preview = service.preview(request)
    if args.json:
        print(wire.PreviewResponse.from_domain(preview).model_dump_json(indent=2))
    else:
        _print_preview_human(preview, show_payload=args.show_payload)
    return EXIT_OK


def _cmd_execute(service: DisclosureApplicationService, args: argparse.Namespace) -> int:
    request = _build_application_request(service, args)
    execution = service.execute(request)
    if args.json:
        print(wire.ExecuteResponse.from_domain(execution).model_dump_json(indent=2))
    else:
        _print_execute_human(execution)
    return EXIT_OK


_COMMAND_HANDLERS = {
    "health": _cmd_health,
    "examples": _cmd_examples,
    "strategies": _cmd_strategies,
    "preview": _cmd_preview,
    "execute": _cmd_execute,
}


# --- entry point --------------------------------------------------------------


def _report_unrecognized(parser: argparse.ArgumentParser, extras: Sequence[str]) -> None:
    """Report unrecognized argv entries without echoing content.

    An entry that starts with ``-`` is an option *name* -- never content --
    so naming it is both safe and the entire diagnostic value of the message
    (``--tsk`` instead of ``--task`` is otherwise very hard to spot). Every
    other entry is a bare positional value, which for this CLI is most
    plausibly the document someone pasted in the wrong place, so only the
    count of those is reported. Never the values.
    """
    named = [extra for extra in extras if extra.startswith("-")]
    parts: list[str] = []
    if named:
        parts.append(f"unrecognized option(s): {' '.join(named)}")
    positional_count = len(extras) - len(named)
    if positional_count:
        parts.append(
            f"{positional_count} unexpected positional argument(s) "
            "(content is deliberately not echoed -- pass text with --text, "
            "a file with --file, or an example with --example)"
        )
    print(parser.format_usage().rstrip(), file=sys.stderr)
    print(f"adg: error: {'; '.join(parts)}", file=sys.stderr)


def main(
    argv: Sequence[str] | None = None, *, service: DisclosureApplicationService | None = None
) -> int:
    """Parse ``argv``, run exactly one command against ``service`` (the
    default demo service from ``application/settings.py`` when ``None``),
    and return an exit code. See the module docstring for the exit-code
    scheme and the no-leak boundary applied to every error path below.
    """
    parser = build_parser()
    try:
        # parse_known_args, not parse_args: argparse's own "unrecognized
        # arguments: ..." message echoes the offending argv entries
        # verbatim, and for this CLI the obvious mistyping (pasting the
        # document as a positional instead of after --text) makes those
        # entries the user's document. Collecting the extras ourselves lets
        # _report_unrecognized below name the ones that are safe to name and
        # count the rest -- see its docstring.
        args, extras = parser.parse_known_args(argv)
    except SystemExit as exc:
        # argparse itself already printed a usage message to stderr and
        # calls sys.exit(2) (or 0 for --help) -- convert that into a normal
        # return so main() never raises SystemExit itself, matching
        # create_app's own injectable, exception-free construction style.
        # Reachable for usage errors argparse detects on its own (an invalid
        # --strategy choice, a missing subcommand), never for unrecognized
        # arguments, which parse_known_args hands back instead of raising.
        return exc.code if isinstance(exc.code, int) else EXIT_BAD_INPUT

    if extras:
        _report_unrecognized(parser, extras)
        return EXIT_BAD_INPUT

    resolved_service = service if service is not None else build_default_service()
    handler = _COMMAND_HANDLERS[args.command]

    try:
        return handler(resolved_service, args)
    except _BAD_INPUT_EXCEPTIONS as exc:
        # Safe by construction -- see the module docstring's no-leak
        # boundary and each exception type's own docstring.
        print(str(exc), file=sys.stderr)
        return EXIT_BAD_INPUT
    except Exception:  # noqa: BLE001 -- fail-closed catch-all, message deliberately discarded
        # Deliberately never this exception's own message or traceback --
        # see the module docstring's no-leak boundary, point 3.
        print("an unexpected error occurred", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    sys.exit(main())
