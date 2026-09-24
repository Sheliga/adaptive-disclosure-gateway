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
from the fake. Two independent measures now stand between "the fake curl
mechanism regressed" and "a test silently talks to the real internet":
  1. every extracted script run here is prefixed with a guard (see
     `_GUARD_PRELUDE`) that compares `command -v curl` against the fake
     curl's own canonical path and `exit 97`s before doing anything else if
     they don't match; `_run_verify` asserts the result is never 97, with
     the full stderr in the failure message.
  2. `_run_verify` also asserts the fake curl's own call log is non-empty
     after every run -- a second, independent signal that execution really
     did reach the fake.
  3. `ADG_VPS_HOSTNAME` is overridden to `adg-verify-test.invalid` (an
     RFC 2606 reserved, permanently non-resolving name) instead of the real
     production hostname the workflow YAML carries, so even a total
     mechanism failure that slipped past both guards above could not reach
     production's public URLs -- only fail on DNS.
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

# Fail-closed guard, run before a single line of the extracted script: if
# `curl` does not resolve to exactly the fake curl this run installed, abort
# immediately (exit 97) rather than let the extracted script silently talk
# to the real internet with the real ADG_VPS_HOSTNAME/HOSTINGER_API_TOKEN.
# The expected path (FAKE_CURL_EXPECTED_PATH) is computed once per run via
# `cd + pwd` -- NOT via `command -v`, and NOT hardcoded from the Python-side
# path string -- because bash/MSYS can normalize a Windows path differently
# than a naive backslash-to-slash rewrite would predict (e.g. a path under
# the Windows TEMP directory is reported as /tmp/..., not /c/Users/.../Temp/
# ...). Computing "what bash would call this path" via `command -v curl`
# itself would be circular: if the fake curl's chmod silently failed (the
# exact regression this guard exists to catch), that same resolution would
# already be pointing at the real system curl, and the guard would then be
# comparing the real curl's path to itself -- always "matching", and never
# tripping. `cd`/`pwd` reads bash's filesystem-mount view of a directory
# that is known to exist, entirely independent of whether anything inside
# it is executable or even present, so it stays a trustworthy oracle even
# when the fake curl installation is broken.
_GUARD_PRELUDE = textwrap.dedent(
    """\
    if [ "$(command -v curl)" != "$FAKE_CURL_EXPECTED_PATH" ]; then
      echo "HARNESS: curl did not resolve to the fake curl -- resolved to $(command -v curl 2>&1 || echo '<not found>'), expected $FAKE_CURL_EXPECTED_PATH" >&2
      exit 97
    fi
    """
)


def _bash_canonical_dir(bash: str, dir_posix: str) -> str:
    """Bash's own canonical path for `dir_posix`, via `cd` + `pwd` -- see
    _GUARD_PRELUDE's comment for why this, and not `command -v`, is the
    right oracle for the guard's expected value."""
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
# header's value) to FAKE_CURL_LOG. A "transport" entry exits non-zero with
# no usable HTTP status (curl's own behavior for DNS/refused/TLS/timeout),
# an "http" entry writes the scripted body to the `-o` file (if any) and the
# scripted status via the `-w` format, exactly like real curl without
# `--fail`, matching the real curl invocations in deploy.yml.
_FAKE_CURL_SCRIPT = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    set -euo pipefail

    url=""
    out_file=""
    want_write=0
    has_auth=0

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
          ;;
        http*://*)
          url="$a"
          ;;
      esac
      i=$((i + 1))
    done

    printf 'url=%s auth=%s\\n' "$url" "$has_auth" >> "$FAKE_CURL_LOG"

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
      exit 97
    fi

    echo $((idx + 1)) > "$idx_file"

    kind=$(cat "$resp_dir/kind")
    code=$(cat "$resp_dir/code")

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
    ep_dir = state_dir / endpoint
    ep_dir.mkdir(parents=True, exist_ok=True)
    for index, event in enumerate(events):
        resp_dir = ep_dir / str(index)
        resp_dir.mkdir()
        kind = event[0]
        if kind == "http":
            _, code, body = event
            (resp_dir / "kind").write_text("http", encoding="utf-8")
            (resp_dir / "code").write_text(str(code), encoding="utf-8")
            (resp_dir / "body").write_text(body, encoding="utf-8")
        elif kind == "transport":
            _, exit_code = event
            (resp_dir / "kind").write_text("transport", encoding="utf-8")
            (resp_dir / "code").write_text(str(exit_code), encoding="utf-8")
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
    call_log.write_text("", encoding="utf-8")
    sleep_log.write_text("", encoding="utf-8")

    # ADG_DOCKER_PROJECT is workflow-level env, not job-level -- merge both
    # so a future move between the two doesn't silently break this harness.
    job_env = dict(_workflow().get("env") or {})
    job_env.update(_deploy_job().get("env") or {})
    script = _GUARD_PRELUDE + _SLEEP_PRELUDE + _extracted_script()

    env = os.environ.copy()
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
    env["FAKE_CURL_EXPECTED_PATH"] = _bash_canonical_dir(_BASH, bin_dir.as_posix()) + "/curl"

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
            "HARNESS FAILURE: the fake-curl guard tripped -- curl did not resolve to the "
            f"fake executable. stdout={result.stdout!r} stderr={result.stderr!r}"
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


def _assert_no_leak(result: subprocess.CompletedProcess, call_log: Path) -> None:
    combined = result.stdout + result.stderr
    assert _SENTINEL_TOKEN not in combined, f"token leaked into output: {combined!r}"
    assert _SENTINEL_5XX_BODY not in combined, f"5xx body leaked into output: {combined!r}"
    call_text = call_log.read_text(encoding="utf-8")
    assert _SENTINEL_TOKEN not in call_text, "token leaked into the fake curl call log"


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
        _assert_no_leak(result, call_log)


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
        _assert_no_leak(result, call_log)


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
        _assert_no_leak(result, call_log)


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
        _assert_no_leak(result, call_log)


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
        _assert_no_leak(result, call_log)

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
        _assert_no_leak(result, call_log)


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
        _assert_no_leak(result, call_log)

    def test_transport_failures_until_timeout(self, tmp_path) -> None:
        result, call_log, _sleep_log = _run_verify(
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
        _assert_no_leak(result, call_log)


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
        _assert_no_leak(result, call_log)

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
        _assert_no_leak(result, call_log)

    def test_empty_array_keeps_polling_then_times_out(self, tmp_path) -> None:
        result, call_log, _sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, "[]")] * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deployment verified" not in result.stdout
        assert "::error::deployment verification timed out after 720s" in result.stdout
        assert "no scripted response left" not in result.stderr
        _assert_no_leak(result, call_log)

    def test_old_sha_keeps_polling_then_times_out(self, tmp_path) -> None:
        result, call_log, _sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, _healthy_containers_json(sha=_OLD_SHA))]
            * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deployment verified" not in result.stdout
        assert "::error::deployment verification timed out after 720s" in result.stdout
        _assert_no_leak(result, call_log)

    def test_unhealthy_container_keeps_polling_then_times_out_with_diagnostic(
        self, tmp_path
    ) -> None:
        unhealthy = (
            '[{"name":"adg-api","state":"running","health":"unhealthy",'
            f'"status":"Up (unhealthy)","image":"ghcr.io/sheliga/adg-api:{_TARGET_SHA}"}}]'
        )
        result, call_log, _sleep_log = _run_verify(
            tmp_path,
            containers=[("http", 200, unhealthy)] * _TIMEOUT_EVENT_COUNT,
        )
        assert result.returncode == 1, result.stdout + result.stderr
        assert "deployment verified" not in result.stdout
        assert "::error::deployment verification timed out after 720s" in result.stdout
        # Final diagnostic dump uses the last VALID 2xx JSON.
        assert "name=adg-api" in result.stdout
        assert "health=unhealthy" in result.stdout
        _assert_no_leak(result, call_log)


class TestFinalDiagnosticUsesLastValidJsonOnly:
    def test_diagnostic_after_5xx_reflects_last_valid_2xx_not_the_5xx_body(self, tmp_path) -> None:
        starting = (
            '[{"name":"adg-api","state":"starting","health":"starting",'
            f'"status":"Up (health: starting)","image":"ghcr.io/sheliga/adg-api:{_OLD_SHA}"}}]'
        )
        result, call_log, _sleep_log = _run_verify(
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
        _assert_no_leak(result, call_log)


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
        _assert_no_leak(result, call_log)


# ---------------------------------------------------------------------------
# Structural: budget/interval constants and rollback safety
# ---------------------------------------------------------------------------


class TestBudgetAndIntervalConstantsPreserved:
    def test_720s_budget_and_15s_interval_still_pinned(self) -> None:
        run = _verify_step()["run"]
        assert "SECONDS + 720" in run, "the ~12 minute verification budget must be preserved"
        assert re.search(r"\bsleep 15\b", run), "the ~15s poll interval must be preserved"


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
