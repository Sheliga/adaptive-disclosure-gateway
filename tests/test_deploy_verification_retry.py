"""Behavioral tests for the Hostinger polling retry/backoff logic inside
deploy.yml's "Verify deployment" step (Issue #99, incident in deploy run
35673821758: a single transient HTTP 500 from the containers endpoint, under
the old `curl --fail-with-body` + `set -e` combination, aborted verification
outright even though the create/replace request had already been accepted
and a re-run of the exact same SHA succeeded seconds later).

Unlike tests/test_deploy_workflow.py (which only parses the committed YAML
and greps its text), this module actually EXECUTES the "Verify deployment"
step's `run:` script under `bash`, with a fake `curl` on PATH that serves
scripted HTTP responses / transport failures from a queue instead of hitting
the real Hostinger API, and a `sleep` shell function override that advances
bash's own $SECONDS instead of blocking, so the ~720s budget / ~15s interval
can be exercised in well under a second of real wall-clock time.

The script is extracted from the live YAML (yaml.safe_load) rather than
duplicated as a separate fixture -- the only substitution made is the single
`${{ steps.vm.outputs.id }}` GitHub Actions expression the step contains, so
what actually runs here is (module a fixed VM id and a sleep override) byte
-for-byte the same script GitHub Actions would run. This is also why the
verification logic must stay INLINE in deploy.yml rather than move to a
helper script file: `workflow_dispatch` rollback checks out an OLDER commit
while still running the CURRENT workflow YAML, so a helper file the older
commit doesn't have would break rollback. TestRollbackSafety below pins that
the step has no such external dependency.

Requires `bash` and `jq` (both preinstalled on the ubuntu-latest runner
test.yml's `test` job already uses). Locally, if either is missing, the
whole module is skipped -- except under CI (`CI=true`), where a missing tool
is a real environment defect and must fail loudly, never skip silently.

HARNESS HARDENING (fail-closed): during development, a bug in
`_install_fake_curl` (an unterminated heredoc silently swallowing the
`chmod +x` into the heredoc body -- see its docstring) once left the fake
curl non-executable, bash's PATH search fell through to the REAL system
curl, and a test that scripted a 401 response ended up actually calling the
live Hostinger API with a nonsense VM id and a sentinel token -- and got a
genuine 401 back, which the test then happily accepted as if it had come
from the fake. Independent measures stand between "the fake curl mechanism
regressed" and "a test silently talks to the real internet":
  1. `_run_verify` asserts the result is never 97 (the guard's exit code),
     with the full stderr in the failure message, and asserts the fake
     curl's own call log is non-empty after every run -- two independent
     signals that execution really reached the fake.
  2. `ADG_VPS_HOSTNAME` is overridden to `adg-verify-test.invalid` (an
     RFC 2606 reserved, permanently non-resolving name) instead of the real
     production hostname the workflow YAML carries, so even a total
     mechanism failure that slipped past every guard could not reach
     production's public URLs -- only fail on DNS.

BUDGET HARDENING (Issue #99 follow-up round 2): 720s used to be checked
only at the top of each loop iteration, but one iteration can contain a
containers curl, a ready curl, a root curl and a sleep -- each individually
capped, but not against the SHARED remaining budget -- so an iteration
starting near the deadline could overrun it by roughly the sum of those
caps while still reporting "timed out after 720s". The workflow step now
recomputes the remaining budget before every one of those four operations
and bounds each one to it (see deploy.yml's own comment for the exact
mechanism). Exercising this from the harness required the fake curl to be
able to simulate REQUEST-TIME ELAPSING, not just wall-clock sleeps -- but
the fake curl is a separate process/executable, so it cannot reach into the
parent shell's own `$SECONDS` directly. `curl` is now a bash FUNCTION
(`_CURL_FUNCTION_PRELUDE`, exported like the existing `sleep` override)
that invokes the real fake-curl EXECUTABLE by its known absolute path and
lets it write an "elapsed seconds" value to a side file
(`FAKE_CURL_ELAPSED_FILE`) -- but the function itself does NOT try to
advance `$SECONDS`: every real curl call in deploy.yml is written as
`status=$(curl ...)`, which ALWAYS forks a subshell, and a subshell's own
variable changes (including to $SECONDS) are discarded the instant it
exits and never reach the parent (confirmed directly; this was the actual
first version of this fix, and it silently didn't work). Instead, a DEBUG
trap (`_fake_curl_time_sync`), set up once in the top-level shell, applies
any pending elapsed value from that side file to $SECONDS before whatever
command runs next -- i.e. in the parent's own context, where it actually
sticks -- without disturbing `$?` (confirmed directly: the
`if status=$(curl ...); then ... else curl_rc=$?; fi` pattern deploy.yml
relies on throughout still sees the real underlying exit code). Because
`curl` becomes a function, `command -v curl` no longer resolves to a path
at all (it prints just the name), so the old guard -- which compared that
output against an absolute path -- could never pass again and had to be
redesigned (see `_GUARD_PRELUDE`): it now checks that `curl` resolves as a
shell FUNCTION (`type -t curl`) and, independently, that the underlying
fake executable file exists and is executable at its known absolute path
-- so a broken function definition and a broken/missing executable are
both still exit-97 fail-closed conditions, not just a broken PATH entry.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "deploy.yml"

_FAKE_VM_ID = "42"
_TARGET_SHA = "deadbeefcafef00d1234567890abcdef12345678"
_OLD_SHA = "0ld5ha0000000000000000000000000000000000"
_SENTINEL_TOKEN = "tok-SENTINEL-9f86d081884c7d659a2f"  # test fixture, not a real credential
_SENTINEL_5XX_BODY = "SENTINEL-5XX-BODY-MUST-NEVER-BE-PRINTED-b6f6"

# Resolved to an absolute path rather than passed as the bare string "bash":
# on Windows, subprocess/CreateProcess searches C:\Windows\System32 before it
# ever consults PATH, and System32 on a machine with "Windows Subsystem for
# Linux" installed contains its own bash.exe launcher stub for WSL -- which
# fails outright if no WSL distro is registered. shutil.which() searches PATH
# in order like a shell would, so it reliably finds Git Bash instead.
_BASH = shutil.which("bash")
_HAS_BASH = _BASH is not None
_HAS_JQ = shutil.which("jq") is not None
_IN_CI = os.environ.get("CI") == "true"

pytestmark = pytest.mark.skipif(
    not (_HAS_BASH and _HAS_JQ) and not _IN_CI,
    reason=(
        "bash and/or jq not available on PATH locally. These tests execute the real "
        "extracted shell script (with a fake curl but real jq/bash) rather than mock "
        "the workflow's own logic, so both tools are required. test.yml's `test` job "
        "runs on ubuntu-latest, which preinstalls both, so CI is never allowed to skip "
        "this module -- only a local machine missing the tools is."
    ),
)


# ---------------------------------------------------------------------------
# Workflow extraction helpers
# ---------------------------------------------------------------------------


def _workflow() -> dict:
    return yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))


def _deploy_job() -> dict:
    return _workflow()["jobs"]["deploy"]


def _verify_step() -> dict:
    for step in _deploy_job()["steps"]:
        if step.get("name") == "Verify deployment":
            return step
    raise AssertionError("deploy.yml must have a 'Verify deployment' step")


def _extracted_script() -> str:
    run = _verify_step()["run"]
    # The only GitHub Actions expression this step's script may contain is
    # the resolved VM id. If a future edit adds a second kind of `${{ }}`
    # expression, this assertion fails loudly instead of silently running a
    # script that still has an unsubstituted `${{ ... }}` literal in it.
    assert run.count("${{") == run.count("steps.vm.outputs.id"), (
        "Verify deployment step contains a ${{ }} expression this test harness does "
        f"not know how to substitute yet: {run!r}"
    )
    return run.replace("${{ steps.vm.outputs.id }}", _FAKE_VM_ID)


_SLEEP_PRELUDE = textwrap.dedent(
    """\
    sleep() {
      printf '%s\\n' "$1" >> "$FAKE_SLEEP_LOG"
      SECONDS=$((SECONDS + ${1%.*}))
    }
    export -f sleep
    """
)

# `curl` is a bash FUNCTION, not a PATH entry, so the fake curl executable
# (FAKE_CURL_EXECUTABLE_PATH, the same file _install_fake_curl writes) can
# report how many seconds a scripted response should be treated as having
# taken. The executable writes that elapsed value to FAKE_CURL_ELAPSED_FILE
# on every call (defaulting to 0 when a scripted response doesn't specify
# one), so ordinary tests that never set `elapsed` behave exactly as before
# (curl calls "take no time"; only `sleep` advances the budget).
#
# Every curl call deploy.yml actually makes is written as
# `status=$(curl ...)` or `... = $(curl ... || echo 000)` -- i.e. ALWAYS
# inside a command substitution, which ALWAYS forks a subshell to run its
# command. That matters a great deal here: a `curl` FUNCTION that tried to
# advance $SECONDS *itself*, inside its own body, would be doing so inside
# that forked subshell -- and a subshell's variable changes, SECONDS
# included, are simply discarded the instant it exits; they never reach the
# parent shell (verified directly: exactly this "function tries to
# self-mutate SECONDS" version silently no-ops -- $SECONDS in the parent
# never moves). So `curl` here does nothing but dispatch to the real
# executable and return its exit status; SECONDS is advanced separately, by
# a DEBUG trap (_fake_curl_time_sync) set up once in this TOP-LEVEL,
# non-subshell shell. A DEBUG trap fires before every subsequent command
# that shell executes -- so the one right after `status=$(curl ...)`
# completes (e.g. deploy.yml's very next line) picks up whatever the just-
# finished subshell left in FAKE_CURL_ELAPSED_FILE and applies it in the
# PARENT's own context, where the mutation actually sticks (also verified
# directly). It also does not disturb `$?`: deploy.yml's
# `if status=$(curl ...); then ... else curl_rc=$?; fi` pattern still sees
# the real underlying exit code with the trap active (verified directly
# too), so it is fully transparent to deploy.yml's own control flow.
_CURL_FUNCTION_PRELUDE = textwrap.dedent(
    """\
    _fake_curl_time_sync() {
      if [ -s "$FAKE_CURL_ELAPSED_FILE" ]; then
        local pending
        pending=$(cat "$FAKE_CURL_ELAPSED_FILE")
        if [ -n "$pending" ] && [ "$pending" != "0" ]; then
          SECONDS=$((SECONDS + ${pending%.*}))
          printf '0' > "$FAKE_CURL_ELAPSED_FILE"
        fi
      fi
    }
    trap _fake_curl_time_sync DEBUG

    curl() {
      "$FAKE_CURL_EXECUTABLE_PATH" "$@"
    }
    export -f curl
    """
)

# Fail-closed guard, run before a single line of the extracted script.
# Because `curl` is now a shell FUNCTION rather than a PATH entry,
# `command -v curl` (the old guard's oracle) would just print the name
# "curl" -- never a path -- so it can no longer be compared against an
# absolute path at all, and the guard had to be redesigned around two
# independent, still fail-closed checks:
#   1. `type -t curl` must report "function" -- confirms the override in
#      _CURL_FUNCTION_PRELUDE actually took effect (not skipped, not
#      shadowed, not unset).
#   2. the underlying fake executable must exist and be executable at its
#      known absolute path (FAKE_CURL_EXECUTABLE_PATH) -- confirms the file
#      the function is ABOUT to invoke is really there, the same property
#      the previous round's guard checked, just via a direct file test
#      instead of PATH resolution.
# If either check fails, abort (exit 97) before a single real operation --
# including the mandatory containers call -- runs, so no code path exists
# where a broken harness could still reach the real Hostinger API.
_GUARD_PRELUDE = textwrap.dedent(
    """\
    if [ "$(type -t curl)" != "function" ]; then
      echo "HARNESS: curl is not overridden as a shell function (type: $(type -t curl 2>&1 || echo '<none>'))" >&2
      exit 97
    fi
    if [ ! -x "$FAKE_CURL_EXECUTABLE_PATH" ]; then
      echo "HARNESS: fake curl executable is missing or not executable at $FAKE_CURL_EXECUTABLE_PATH" >&2
      exit 97
    fi
    """
)


def _bash_canonical_dir(bash: str, dir_posix: str) -> str:
    """Bash's own canonical path for `dir_posix`, via `cd` + `pwd` -- not
    via `command -v` (no longer meaningful once `curl` is a function, and
    would have been circular even before: a broken fake curl would resolve
    to the real one on both sides of that comparison) and not via a naive
    Python-side backslash-to-slash rewrite of the Windows path (bash/MSYS
    can normalize a path under the Windows TEMP directory as /tmp/...,
    not a drive-letter path with slashes swapped). `cd`/`pwd` reads bash's
    filesystem-mount view of a directory that is known to exist, entirely
    independent of whether anything inside it is executable or even
    present, so it stays a trustworthy oracle even when the fake curl
    installation itself is broken."""
    result = subprocess.run(
        [bash, "-c", f'cd "{dir_posix}" && pwd'],
        capture_output=True,
        text=True,
        check=True,
    )
    resolved = result.stdout.strip()
    assert resolved, f"bash could not resolve a canonical path for {dir_posix!r}"
    return resolved


# ---------------------------------------------------------------------------
# Fake curl
# ---------------------------------------------------------------------------

# Dispatches on the URL (containers / ready / root), pops the next scripted
# response for that endpoint from an indexed queue directory, and records
# every call (URL + whether an Authorization header was passed -- never the
# header's value -- + the --max-time value it was invoked with) to
# FAKE_CURL_LOG. A "transport" entry exits non-zero with no usable HTTP
# status (curl's own behavior for DNS/refused/TLS/timeout), an "http" entry
# writes the scripted body to the `-o` file (if any) and the scripted status
# via the `-w` format, exactly like real curl without `--fail`, matching the
# real curl invocations in deploy.yml.
#
# Each scripted response may also carry an "elapsed" seconds value (an
# optional per-call file next to "kind"/"code"; 0 when absent). Since this
# executable is a separate process, it cannot advance the calling shell's
# own $SECONDS itself -- it writes the value to FAKE_CURL_ELAPSED_FILE
# instead, and the `curl` bash function wrapping this executable
# (_CURL_FUNCTION_PRELUDE) reads that file back and does the actual
# $SECONDS advancement in the parent shell, the same indirection the
# existing `sleep` override already relies on.
_FAKE_CURL_SCRIPT = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    url=""
    out_file=""
    want_write=0
    has_auth=0
    max_time=""

    i=1
    while [ "$i" -le "$#" ]; do
      a="${!i}"
      case "$a" in
        -H)
          i=$((i + 1))
          hdr="${!i}"
          case "$hdr" in
            Authorization:*) has_auth=1 ;;
          esac
          ;;
        -o)
          i=$((i + 1))
          out_file="${!i}"
          ;;
        -w)
          i=$((i + 1))
          want_write=1
          ;;
        --max-time)
          i=$((i + 1))
          max_time="${!i}"
          ;;
        http*://*)
          url="$a"
          ;;
      esac
      i=$((i + 1))
    done

    printf 'url=%s auth=%s max_time=%s\\n' "$url" "$has_auth" "$max_time" >> "$FAKE_CURL_LOG"

    case "$url" in
      *"/containers") ep="containers" ;;
      *"/api/ready") ep="ready" ;;
      *) ep="root" ;;
    esac

    idx_file="$FAKE_CURL_STATE/${ep}.idx"
    idx=0
    [ -f "$idx_file" ] && idx=$(cat "$idx_file")
    resp_dir="$FAKE_CURL_STATE/${ep}/${idx}"

    if [ ! -d "$resp_dir" ]; then
      echo "fake curl: no scripted response left for endpoint ${ep} (call index ${idx})" >&2
      # No scripted elapsed time for a call that was never actually
      # scripted -- reset the side channel to 0 so a stale value from a
      # previous call can't leak into this (failing) one.
      printf '0' > "$FAKE_CURL_ELAPSED_FILE"
      exit 97
    fi

    echo $((idx + 1)) > "$idx_file"

    kind=$(cat "$resp_dir/kind")
    code=$(cat "$resp_dir/code")

    elapsed="0"
    if [ -f "$resp_dir/elapsed" ]; then
      elapsed=$(cat "$resp_dir/elapsed")
    fi
    printf '%s' "$elapsed" > "$FAKE_CURL_ELAPSED_FILE"

    if [ "$kind" = "transport" ]; then
      if [ -n "$out_file" ]; then
        : > "$out_file"
      fi
      if [ "$want_write" -eq 1 ]; then
        printf '000'
      fi
      exit "$code"
    fi

    if [ -n "$out_file" ]; then
      cp "$resp_dir/body" "$out_file"
    fi
    if [ "$want_write" -eq 1 ]; then
      printf '%s' "$code"
    fi
    exit 0
    """
)


def _install_fake_curl(bin_dir_posix: str) -> None:
    """Writes and chmods the fake curl entirely through bash itself (rather
    than Path.write_text + Path.chmod from the Python side), because on
    Windows/Git-Bash only bash's own `chmod +x`, run inside the same MSYS
    session that will later exec the file, reliably marks it executable for
    that session -- Python's os.chmod only toggles the DOS read-only
    attribute and is not sufficient here."""
    # Built via an unindented join, not an indented textwrap.dedent f-string:
    # once _FAKE_CURL_SCRIPT (itself starting at column 0) is interpolated
    # in, dedent() sees a mix of indented wrapper lines and zero-indent
    # script lines and computes a common-prefix of "", i.e. it strips
    # nothing -- so the "FAKE_CURL_EOF" terminator line would keep its
    # leading whitespace and no longer match the (unindented) `<<'...'`
    # heredoc opener. bash then never finds the terminator, `chmod +x` is
    # swallowed into the heredoc body instead of executing, the fake curl is
    # left without the executable bit, and bash's PATH search silently
    # falls through to the real system curl for every call -- which is
    # exactly what happened here (a genuine 401 came back from the real
    # Hostinger API for a nonsense VM id/token) before this was fixed.
    setup_lines = [
        "set -euo pipefail",
        f'mkdir -p "{bin_dir_posix}"',
        f"cat > \"{bin_dir_posix}/curl\" <<'FAKE_CURL_EOF'",
        _FAKE_CURL_SCRIPT,
        "FAKE_CURL_EOF",
        f'chmod +x "{bin_dir_posix}/curl"',
        "",
    ]
    setup = "\n".join(setup_lines)
    subprocess.run([_BASH, "-c", setup], check=True, capture_output=True, text=True)


def _queue(state_dir: Path, endpoint: str, events: list[tuple]) -> None:
    """Writes the scripted response queue for one endpoint. Each event is
    either `("http", code, body)` or `("http", code, body, elapsed)`, or
    `("transport", exit_code)` or `("transport", exit_code, elapsed)` --
    `elapsed` (seconds the fake curl reports having "taken" for this call,
    via FAKE_CURL_ELAPSED_FILE) defaults to 0 when omitted, so every
    pre-existing call site that never mentions it keeps behaving exactly as
    before (curl calls "take no time"; only `sleep` advances the budget)."""
    ep_dir = state_dir / endpoint
    ep_dir.mkdir(parents=True, exist_ok=True)
    for index, event in enumerate(events):
        resp_dir = ep_dir / str(index)
        resp_dir.mkdir()
        kind = event[0]
        if kind == "http":
            if len(event) == 4:
                _, code, body, elapsed = event
            else:
                _, code, body = event
                elapsed = 0
            (resp_dir / "kind").write_text("http", encoding="utf-8")
            (resp_dir / "code").write_text(str(code), encoding="utf-8")
            (resp_dir / "body").write_text(body, encoding="utf-8")
            (resp_dir / "elapsed").write_text(str(elapsed), encoding="utf-8")
        elif kind == "transport":
            if len(event) == 3:
                _, exit_code, elapsed = event
            else:
                _, exit_code = event
                elapsed = 0
            (resp_dir / "kind").write_text("transport", encoding="utf-8")
            (resp_dir / "code").write_text(str(exit_code), encoding="utf-8")
            (resp_dir / "elapsed").write_text(str(elapsed), encoding="utf-8")
        else:  # pragma: no cover - test-authoring guard
            raise ValueError(f"unknown event kind {kind!r}")


def _healthy_containers_json(sha: str = _TARGET_SHA) -> str:
    return (
        '[{"name":"adg-api","state":"running","health":"healthy",'
        f'"status":"Up 2 minutes (healthy)","image":"ghcr.io/sheliga/adg-api:{sha}"}}]'
    )


def _run_verify(
    tmp_path: Path,
    *,
    containers: list[tuple],
    ready: list[tuple] = (),
    root: list[tuple] = (),
    target_sha: str = _TARGET_SHA,
    token: str = _SENTINEL_TOKEN,
) -> tuple[subprocess.CompletedProcess, Path, Path]:
    bin_dir = tmp_path / "bin"
    _install_fake_curl(bin_dir.as_posix())

    state_dir = tmp_path / "state"
    _queue(state_dir, "containers", list(containers))
    _queue(state_dir, "ready", list(ready))
    _queue(state_dir, "root", list(root))

    call_log = tmp_path / "calls.log"
    sleep_log = tmp_path / "sleeps.log"
    elapsed_file = tmp_path / "curl_elapsed"
    call_log.write_text("", encoding="utf-8")
    sleep_log.write_text("", encoding="utf-8")
    elapsed_file.write_text("0", encoding="utf-8")

    # ADG_DOCKER_PROJECT is workflow-level env, not job-level -- merge both
    # so a future move between the two doesn't silently break this harness.
    job_env = dict(_workflow().get("env") or {})
    job_env.update(_deploy_job().get("env") or {})
    script = _CURL_FUNCTION_PRELUDE + _GUARD_PRELUDE + _SLEEP_PRELUDE + _extracted_script()

    env = os.environ.copy()
    # bin_dir stays on PATH as a second, independent line of defense: `curl`
    # resolving as a shell function always wins over PATH resolution in
    # bash, but if that function definition ever failed to take effect for
    # some reason, a PATH search would still land on this same fake
    # executable (named literally "curl") rather than the real system one.
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["HOSTINGER_API_TOKEN"] = token
    env["ADG_TARGET_SHA"] = target_sha
    # RFC 2606 reserved, permanently non-resolving hostname -- deliberately
    # NOT the real production hostname the workflow YAML carries (see the
    # module docstring's "HARNESS HARDENING" note). If every other guard
    # here somehow failed and the real curl got invoked anyway, this still
    # keeps the public ready/root checks off the real production VPS.
    env["ADG_VPS_HOSTNAME"] = "adg-verify-test.invalid"
    env["ADG_DOCKER_PROJECT"] = str(job_env["ADG_DOCKER_PROJECT"])
    env["FAKE_CURL_STATE"] = state_dir.as_posix()
    env["FAKE_CURL_LOG"] = call_log.as_posix()
    env["FAKE_SLEEP_LOG"] = sleep_log.as_posix()
    env["FAKE_CURL_ELAPSED_FILE"] = elapsed_file.as_posix()
    env["FAKE_CURL_EXECUTABLE_PATH"] = _bash_canonical_dir(_BASH, bin_dir.as_posix()) + "/curl"

    result = subprocess.run(
        [_BASH, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    # Fail-closed harness assertions, centralized so no individual test can
    # forget them and accidentally pass against a broken fake curl (or,
    # worse, the real Hostinger API). Deliberately raised as plain
    # AssertionErrors with a distinct "HARNESS FAILURE" prefix so they read
    # unambiguously differently from an ordinary test assertion failure.
    if result.returncode == 97:
        raise AssertionError(
            "HARNESS FAILURE: the fake-curl guard tripped -- curl is not correctly "
            f"overridden. stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    if not _calls_to(call_log, "/containers"):
        raise AssertionError(
            "HARNESS FAILURE: no containers call reached the fake curl (call log is "
            f"empty) -- stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    return result, call_log, sleep_log


def _calls_to(call_log: Path, suffix: str) -> list[str]:
    lines = call_log.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if suffix in line]


def _sleeps(sleep_log: Path) -> list[str]:
    return [line for line in sleep_log.read_text(encoding="utf-8").splitlines() if line]


_MAX_TIME_RE = re.compile(r"max_time=(\d+)")


def _max_times(call_log: Path) -> list[int]:
    """Every `--max-time` value the workflow script actually passed to
    curl, across every call the fake curl logged (containers, ready and
    root alike)."""
    return [int(m) for m in _MAX_TIME_RE.findall(call_log.read_text(encoding="utf-8"))]


def _assert_no_leak(result: subprocess.CompletedProcess, call_log: Path, sleep_log: Path) -> None:
    """Centralized, fail-closed assertions applied after every _run_verify
    call: no sensitive value ever reaches stdout/stderr/the call log, and
    (Issue #99 budget-hardening round) every curl's --max-time and every
    sleep the script issued stayed within its normal ceiling and above
    zero -- i.e. the shared 720s budget was actually respected, never
    silently ignored or allowed to go negative."""
    combined = result.stdout + result.stderr
    assert _SENTINEL_TOKEN not in combined, f"token leaked into output: {combined!r}"
    assert _SENTINEL_5XX_BODY not in combined, f"5xx body leaked into output: {combined!r}"
    call_text = call_log.read_text(encoding="utf-8")
    assert _SENTINEL_TOKEN not in call_text, "token leaked into the fake curl call log"

    for max_time in _max_times(call_log):
        assert 1 <= max_time <= 30, f"logged max_time out of [1, 30] bounds: {max_time}"
    for sleep_value in _sleeps(sleep_log):
        sleep_int = int(sleep_value)
        assert 1 <= sleep_int <= 15, f"logged sleep out of [1, 15] bounds: {sleep_value!r}"


# Enough 5xx/transport events to outlast the 720s budget at the pinned 15s
# poll interval (48 iterations), with a couple of spare entries so an
# off-by-one in the loop boundary doesn't make the fake curl queue run dry
# and masquerade as an unrelated transport failure.
_TIMEOUT_EVENT_COUNT = 50


# ---------------------------------------------------------------------------
# A. transient 5xx then success
# ---------------------------------------------------------------------------


class TestTransient5xxThenSuccess:
    @pytest.mark.parametrize("code", [500, 502, 503])
    def test_first_5xx_does_not_end_verification(self, tmp_path, code) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                ("http", code, _SENTINEL_5XX_BODY),
                ("http", 200, _healthy_containers_json()),
            ],
            ready=[("http", 200, "")],
            root=[("http", 200, "")],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "deployment verified" in result.stdout
        assert str(code) in result.stdout, "the transient status should be logged"
        assert len(_calls_to(call_log, "/containers")) == 2
        assert len(_calls_to(call_log, "/api/ready")) == 1
        assert len(_sleeps(sleep_log)) == 1, "exactly one retry sleep between the 5xx and success"
        assert _sleeps(sleep_log) == ["15"]
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# B. repeated 5xx until deadline
# ---------------------------------------------------------------------------


class TestRepeated5xxUntilTimeout:
    def test_times_out_with_clear_message_and_no_body_leak(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 500, _SENTINEL_5XX_BODY)] * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert "timed out after repeated Hostinger API 5xx responses" in result.stdout
        containers_calls = len(_calls_to(call_log, "/containers"))
        assert f"transient 5xx responses: {containers_calls}" in result.stdout
        assert "transport failures: 0" in result.stdout
        assert len(_sleeps(sleep_log)) == containers_calls
        # Budget was actually exhausted, not the fake queue running dry.
        assert "no scripted response left" not in result.stderr
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# C/D. 401 / 403 fail fast
# ---------------------------------------------------------------------------


class TestAuthFailuresFailFast:
    @pytest.mark.parametrize("code", [401, 403])
    def test_fails_immediately_with_exactly_one_call_and_no_sleep(self, tmp_path, code) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", code, '{"message":"unauthorized"}')],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert (
            f"::error::Hostinger containers API returned HTTP {code}; "
            "authentication/authorization failure" in combined
        )
        all_calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
        assert len(all_calls) == 1, (
            f"auth failure must not make any public ready/root call either: {all_calls!r}"
        )
        assert len(_calls_to(call_log, "/containers")) == 1
        assert _sleeps(sleep_log) == []
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# E. other non-retryable statuses fail fast
# ---------------------------------------------------------------------------


class TestOtherNonRetryableStatusesFailFast:
    @pytest.mark.parametrize("code", [404, 422, 302])
    def test_fails_immediately_without_retry(self, tmp_path, code) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", code, '{"message":"nope"}')],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "::error::" in combined
        assert str(code) in combined
        assert len(_calls_to(call_log, "/containers")) == 1
        assert _sleeps(sleep_log) == []
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# F. healthy containers but public checks not ready yet
# ---------------------------------------------------------------------------


class TestPublicChecksNotReadyYet:
    def test_ready_not_200_then_ready_ok_succeeds(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                ("http", 200, _healthy_containers_json()),
                ("http", 200, _healthy_containers_json()),
            ],
            ready=[("http", 503, ""), ("http", 200, "")],
            root=[("http", 200, ""), ("http", 200, "")],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "deployment verified" in result.stdout
        assert "containers healthy but public URL not yet 200" in result.stdout
        assert len(_calls_to(call_log, "/containers")) == 2
        assert len(_sleeps(sleep_log)) == 1
        _assert_no_leak(result, call_log, sleep_log)

    def test_root_not_200_then_root_ok_succeeds(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                ("http", 200, _healthy_containers_json()),
                ("http", 200, _healthy_containers_json()),
            ],
            ready=[("http", 200, ""), ("http", 200, "")],
            root=[("http", 503, ""), ("http", 200, "")],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "deployment verified" in result.stdout
        assert len(_sleeps(sleep_log)) == 1
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# G. transport failures
# ---------------------------------------------------------------------------


class TestTransportFailures:
    def test_transport_failure_then_success(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                ("transport", 7),
                ("http", 200, _healthy_containers_json()),
            ],
            ready=[("http", 200, "")],
            root=[("http", 200, "")],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "deployment verified" in result.stdout
        assert "transport failure" in result.stdout
        assert len(_sleeps(sleep_log)) == 1
        _assert_no_leak(result, call_log, sleep_log)

    def test_transport_failures_until_timeout(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("transport", 7)] * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert "timed out after repeated Hostinger API 5xx responses" not in result.stdout
        containers_calls = len(_calls_to(call_log, "/containers"))
        assert f"transport failures: {containers_calls}" in result.stdout
        assert "transient 5xx responses: 0" in result.stdout
        assert "no scripted response left" not in result.stderr
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# 2xx body/shape and content edge cases
# ---------------------------------------------------------------------------


class TestTwoXxBodyEdgeCases:
    def test_invalid_json_body_fails_clearly_without_retry(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, "not-json-at-all{")],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "::error::" in combined
        assert "not valid JSON" in combined
        assert len(_calls_to(call_log, "/containers")) == 1
        assert _sleeps(sleep_log) == []
        _assert_no_leak(result, call_log, sleep_log)

    def test_unexpected_json_shape_fails_clearly_without_retry(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, '{"not":"an array"}')],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        combined = result.stdout + result.stderr
        assert "::error::" in combined
        assert "unexpected JSON shape" in combined
        assert len(_calls_to(call_log, "/containers")) == 1
        assert _sleeps(sleep_log) == []
        _assert_no_leak(result, call_log, sleep_log)

    def test_empty_array_keeps_polling_then_times_out(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, "[]")] * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deployment verified" not in result.stdout
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert "no scripted response left" not in result.stderr
        _assert_no_leak(result, call_log, sleep_log)

    def test_old_sha_keeps_polling_then_times_out(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, _healthy_containers_json(sha=_OLD_SHA))]
            * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deployment verified" not in result.stdout
        assert "::error::deployment verification timed out after 720s" in result.stdout
        _assert_no_leak(result, call_log, sleep_log)

    def test_unhealthy_container_keeps_polling_then_times_out_with_diagnostic(
        self, tmp_path
    ) -> None:
        unhealthy = (
            '[{"name":"adg-api","state":"running","health":"unhealthy",'
            f'"status":"Up (unhealthy)","image":"ghcr.io/sheliga/adg-api:{_TARGET_SHA}"}}]'
        )
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, unhealthy)] * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deployment verified" not in result.stdout
        assert "::error::deployment verification timed out after 720s" in result.stdout
        # Final diagnostic dump uses the last VALID 2xx JSON.
        assert "name=adg-api" in result.stdout
        assert "health=unhealthy" in result.stdout
        _assert_no_leak(result, call_log, sleep_log)


class TestFinalDiagnosticUsesLastValidJsonOnly:
    def test_diagnostic_after_5xx_reflects_last_valid_2xx_not_the_5xx_body(self, tmp_path) -> None:
        starting = (
            '[{"name":"adg-api","state":"starting","health":"starting",'
            f'"status":"Up (health: starting)","image":"ghcr.io/sheliga/adg-api:{_OLD_SHA}"}}]'
        )
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, starting)] + [("http", 500, _SENTINEL_5XX_BODY)] * 48,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert "timed out after repeated Hostinger API 5xx responses" in result.stdout
        assert "name=adg-api" in result.stdout
        assert "health=starting" in result.stdout
        # Exactly one of the queued containers calls was the valid 2xx; every
        # other call the budget allowed for was a 5xx.
        containers_calls = len(_calls_to(call_log, "/containers"))
        assert f"transient 5xx responses: {containers_calls - 1}" in result.stdout
        assert "no scripted response left" not in result.stderr
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# All correct -> success, no retries at all
# ---------------------------------------------------------------------------


class TestAllCorrectSucceedsWithoutAnyRetry:
    def test_single_pass_success(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, _healthy_containers_json())],
            ready=[("http", 200, "")],
            root=[("http", 200, "")],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            "deployment verified: containers healthy at "
            f"{_TARGET_SHA}, /disclosure-gateway/api/ready=200, /disclosure-gateway=200"
        ) in result.stdout
        assert len(_calls_to(call_log, "/containers")) == 1
        assert len(_calls_to(call_log, "/api/ready")) == 1
        assert _sleeps(sleep_log) == []
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# Budget hardening (Issue #99 follow-up round 2): the 720s deadline is a
# real, shared wall-clock bound over every curl and sleep in the loop, not
# just a condition re-checked at the top of each iteration. These tests use
# the fake curl's `elapsed` field to simulate slow requests eating into the
# budget, so a call landing near (or past) the deadline can be observed
# directly, without waiting out 720 real seconds.
# ---------------------------------------------------------------------------


def _root_calls(call_log: Path) -> list[str]:
    """Root ("/disclosure-gateway", no further path) calls only --
    distinguished from ready ("/disclosure-gateway/api/ready") by matching
    "disclosure-gateway" immediately followed by " auth=" (i.e. nothing else
    in the URL after it), which a ready call's URL never is."""
    return _calls_to(call_log, "disclosure-gateway auth=")


def _burn_event(target_remaining_after_sleep: int) -> tuple:
    """A single scripted containers transport-failure event whose elapsed
    time, once its own retry sleep (`min(15, remaining)`) also runs, leaves
    exactly `target_remaining_after_sleep` seconds of the 720s budget before
    the NEXT containers call -- so a later, interesting call can be placed
    at a precise point near the deadline without re-deriving this arithmetic
    at every call site. Only valid for a target that implies a >=15s sleep
    after the burn event (true for every value this module uses): remaining
    right after the burn call is `target + 15`, its own sleep is exactly
    15s (since `target + 15 >= 15`), landing at `target`.
    """
    remaining_before_sleep = target_remaining_after_sleep + 15
    assert remaining_before_sleep >= 15, "helper only supports the >=15s-sleep case"
    elapsed = 720 - remaining_before_sleep
    return ("transport", 6, elapsed)


class TestBudgetNearDeadlineForContainersCurl:
    def test_max_time_bounded_when_five_seconds_left(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                _burn_event(5),
                ("http", 401, '{"message":"unauthorized"}'),
            ],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        max_times = _max_times(call_log)
        assert len(max_times) == 2
        assert max_times[0] == 30, "the first call starts with the full budget"
        # Bounded with a tolerance band, not pinned to exactly 5: real
        # process-spawn overhead (mktemp/jq/cat per iteration) can eat a
        # couple of real seconds between the burn landing and this
        # assertion, especially on a slower machine -- the meaningful claim
        # is "nowhere near the old hardcoded 30", not "exactly 5".
        assert 1 <= max_times[1] <= 10, (
            f"second containers call's --max-time should be bounded to ~5s left, got {max_times[1]}"
        )
        _assert_no_leak(result, call_log, sleep_log)

    def test_containers_curl_consuming_the_rest_ends_with_no_sleep_no_further_call(
        self, tmp_path
    ) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                _burn_event(5),
                ("http", 500, _SENTINEL_5XX_BODY, 5),
            ],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert len(_calls_to(call_log, "/containers")) == 2, (
            "the deadline must stop the loop before a third containers call"
        )
        assert _sleeps(sleep_log) == ["15"], (
            "the exhausted 5xx must not be followed by another sleep"
        )
        assert "transient 5xx responses: 1" in result.stdout
        assert "transport failures: 1" in result.stdout
        _assert_no_leak(result, call_log, sleep_log)


class TestReadyAndRootShareTheDeadline:
    def test_root_max_time_bounded_after_ready_spends_most_of_it(self, tmp_path) -> None:
        # Wider margins than the "10s left, ready spends 8" the issue
        # describes: with only 2s nominally left for root, a couple of
        # seconds of real process-spawn overhead (this scenario has more
        # steps -- containers, ready, root -- than most other cases here)
        # was enough to occasionally wipe the window out entirely and skip
        # root altogether. 40s left / ready spends 30 keeps root's ~10s
        # comfortably positive under that same realistic overhead while
        # still proving it is nowhere near the old hardcoded 30.
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                _burn_event(40),
                ("http", 200, _healthy_containers_json()),
            ],
            ready=[("http", 200, "", 30)],
            root=[("http", 200, "")],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "deployment verified" in result.stdout
        max_times = _max_times(call_log)
        assert len(max_times) == 4, max_times
        _, containers2, ready_mt, root_mt = max_times
        assert containers2 <= 40
        assert ready_mt <= 40, f"ready should be bounded to ~40s left, got {ready_mt}"
        assert 1 <= root_mt <= 20, (
            f"root should be bounded to ~10s left after ready spent 30 of the 40, got {root_mt} "
            "(never the old hardcoded 30)"
        )
        _assert_no_leak(result, call_log, sleep_log)

    def test_root_not_called_when_ready_spends_the_whole_remaining_budget(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                _burn_event(10),
                ("http", 200, _healthy_containers_json()),
            ],
            ready=[("http", 200, "", 10)],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deployment verified" not in result.stdout
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert len(_calls_to(call_log, "/api/ready")) == 1
        assert _root_calls(call_log) == [], (
            "root must not be called once ready alone exhausted the remaining budget"
        )
        _assert_no_leak(result, call_log, sleep_log)


class TestSleepBoundedByRemainingBudget:
    def test_sleep_bounded_to_about_ten_seconds_left(self, tmp_path) -> None:
        not_yet_healthy = (
            '[{"name":"adg-api","state":"starting","health":"starting",'
            f'"status":"Up (health: starting)","image":"ghcr.io/sheliga/adg-api:{_OLD_SHA}"}}]'
        )
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                _burn_event(10),
                ("http", 200, not_yet_healthy),
            ],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        sleeps = _sleeps(sleep_log)
        assert sleeps[0] == "15", "the burn event's own retry sleep is unaffected"
        # Tolerance band rather than an exact "10": a couple of real seconds
        # of process-spawn overhead can land the final poll a bit under the
        # nominal target. What matters is that it is clearly NOT the old
        # hardcoded 15.
        assert len(sleeps) == 2
        final_sleep = int(sleeps[1])
        assert 1 <= final_sleep <= 13, (
            f"the final poll's sleep must be bounded to ~10s left, not 15 -- got {final_sleep}"
        )
        _assert_no_leak(result, call_log, sleep_log)


class TestNoNegativeRemainingIsEverLogged:
    def test_elapsed_time_past_the_deadline_never_logs_a_negative_remaining(self, tmp_path) -> None:
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("transport", 6, 750)],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert not re.search(r"~-\d+s left", result.stdout), (
            f"a negative remaining was logged: {result.stdout!r}"
        )
        assert "~0s left" in result.stdout
        assert _sleeps(sleep_log) == [], "nothing was left to sleep for"
        _assert_no_leak(result, call_log, sleep_log)


class TestTransportTimeoutConsumingTheBudgetStaysBounded:
    def test_large_transport_elapsed_reaches_timeout_without_exhausting_the_queue(
        self, tmp_path
    ) -> None:
        # Each attempt "takes" 100s before failing -- at ~115s/iteration
        # (100s elapsed + a 15s retry sleep) the 720s budget is exhausted
        # in well under the 10 scripted events, proving elapsed time alone
        # (not just the sleep interval) counts toward the shared deadline.
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[("transport", 6, 100)] * 10,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert "no scripted response left" not in result.stderr, (
            "the budget, not an exhausted test queue, must be what ends this run"
        )
        containers_calls = len(_calls_to(call_log, "/containers"))
        assert containers_calls < 10, (
            f"720s of budget at ~115s/iteration should need far fewer than 10 calls, "
            f"got {containers_calls}"
        )
        assert f"transport failures: {containers_calls}" in result.stdout
        _assert_no_leak(result, call_log, sleep_log)


class TestFiveXxNearDeadlineIsBounded:
    def test_5xx_with_little_budget_left_gets_a_bounded_timeout_and_sleep(self, tmp_path) -> None:
        # The issue describes "~719s already consumed" (~1s left); an exact
        # 1s target proved too fragile here -- any real process-spawn
        # overhead at all could exhaust it before the second containers
        # call even started, so nothing was left to assert on. 10s left
        # keeps enough headroom to reliably observe both the bounded
        # --max-time on the 5xx call itself and its bounded retry sleep,
        # while still being unambiguously far from the old hardcoded 30/15.
        result, call_log, sleep_log = _run_verify(
            tmp_path,
            containers=[
                _burn_event(10),
                ("http", 500, _SENTINEL_5XX_BODY),
            ],
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "::error::deployment verification timed out after 720s" in result.stdout
        max_times = _max_times(call_log)
        assert len(max_times) == 2
        assert 1 <= max_times[1] <= 13, (
            f"the 5xx call itself should get --max-time bounded to ~10s left, got {max_times[1]} "
            "(never the old hardcoded 30)"
        )
        sleeps = _sleeps(sleep_log)
        assert sleeps[0] == "15"
        assert len(sleeps) == 2
        final_sleep = int(sleeps[1])
        assert 1 <= final_sleep <= 13, (
            f"the retry sleep after this 5xx must be bounded to ~10s left, not 15 -- got {final_sleep}"
        )
        _assert_no_leak(result, call_log, sleep_log)


# ---------------------------------------------------------------------------
# Structural: budget/interval constants and rollback safety
# ---------------------------------------------------------------------------


class TestBudgetAndIntervalConstantsPreserved:
    def test_720s_budget_15s_interval_and_30s_curl_ceiling_still_pinned(self) -> None:
        # The literal `sleep 15` this test used to pin no longer appears --
        # sleep is now bounded by the shared remaining budget
        # (`sleep "$(bounded_sleep_seconds "$remaining")"`), not a bare
        # constant -- so this pins the actual mechanism instead: the
        # deadline, and each helper's ceiling.
        run = _verify_step()["run"]
        assert "SECONDS + 720" in run, "the ~12 minute verification budget must be preserved"
        assert "remaining_seconds" in run, (
            "the shared remaining-budget computation must be preserved"
        )
        assert "bounded_sleep_seconds" in run and re.search(r"-gt 15", run), (
            "the ~15s poll interval ceiling must be preserved"
        )
        assert "bounded_timeout" in run and re.search(r"-gt 30", run), (
            "the ~30s per-curl --max-time ceiling must be preserved"
        )


class TestNoVerboseCurlOrHeaderDump:
    def test_no_verbose_or_trace_flags(self) -> None:
        run = _verify_step()["run"]
        assert " -v " not in run and not run.startswith("-v ")
        assert "--trace" not in run
        assert "--include" not in run and " -i " not in run


class TestRollbackSafety:
    """Rollback re-runs this workflow via workflow_dispatch with an OLDER
    `sha`; the job checks out that older ref, but the workflow YAML itself
    still comes from the dispatch ref (current HEAD). A helper script file
    added to the repo now would therefore be missing from an old checkout,
    breaking rollback -- so the verification logic must stay inline."""

    def test_verify_step_has_no_dependency_on_repo_files(self) -> None:
        run = _verify_step()["run"]
        forbidden_substrings = ["./scripts", "bash scripts", "bash ./", "source scripts"]
        for token in forbidden_substrings:
            assert token not in run, (
                f"Verify deployment step must stay fully inline (found {token!r}) so "
                "rollback to an older commit -- which runs the CURRENT workflow YAML "
                "against an OLDER checkout -- doesn't reference a file that commit lacks"
            )
        for line in run.splitlines():
            stripped = line.strip()
            assert not re.match(r"^\.?\s*/?scripts/", stripped), (
                f"line sources/executes a repo script file, breaking rollback: {line!r}"
            )
