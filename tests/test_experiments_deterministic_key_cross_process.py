"""PR #35 review, blocker 4: ``deterministic_key`` must be identical across
*independent processes*, not just across two calls within the same one.

Confirmed root cause: ``audit.py`` generates ``_DEFAULT_AUDIT_HASH_KEY =
secrets.token_bytes(32)`` once per process, at import time. Every audit
content hash (``transformation.payload_hash``, ``provider.response_hash``,
``reconstruction.reconstructed_hash``) is HMAC-SHA256 keyed by that value.
``deterministic_key`` strips ``metadata`` and every wall-clock measurement,
but previously retained the *entire* ``audit`` block, hashes included -- so
two independent processes scoring the identical case/treatment/config
produced *different* HMACs and therefore different "deterministic" keys.
The existing regression test (``test_experiments_serialization_and_aggregation.py``'s
``test_deterministic_key_is_identical_across_two_independent_runs_of_the_same_case``)
only ever called ``run_pilot`` twice *within one process*, so it could not
catch this -- ``_DEFAULT_AUDIT_HASH_KEY`` is stable within a single process
by construction.

This file spawns two genuinely separate Python processes (``subprocess``,
not an in-process fixture) running the identical case/treatment/config, and
asserts:

1. before the fix: this test is expected to FAIL (see the review's own
   before-fix capture in the PR description) because the two processes'
   ``deterministic_key`` JSON dumps differ;
2. after the fix: the two ``deterministic_key`` JSON dumps are byte-for-byte
   equal, while the two processes' *raw* audit hashes (``payload_hash``) are
   allowed -- and, separately, pinned -- to differ, proving the HMAC key
   itself was never fixed/weakened to make this pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
SRC_DIR = REPO_ROOT / "src"

_WORKER_SCRIPT = textwrap.dedent(
    """
    import json
    from pathlib import Path

    from adaptive_disclosure_gateway.domain import Treatment
    from adaptive_disclosure_gateway.experiments.case_result import (
        deterministic_key,
        to_safe_dict,
    )
    from adaptive_disclosure_gateway.experiments.corpus_source import load_hr_v1_cases
    from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
    from adaptive_disclosure_gateway.experiments.runner import run_case_for_treatment
    from adaptive_disclosure_gateway.policies import PolicyRepository

    REPO_ROOT = Path(%(repo_root)r)
    CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"
    POLICY_DIR = REPO_ROOT / "configs" / "policies"

    cases = {c.input.sample_id: c for c in load_hr_v1_cases(CORPUS_DIR)}
    case = cases["hr_team_summary_001"]
    policy_repo = PolicyRepository.from_directory(POLICY_DIR)

    result = run_case_for_treatment(
        case,
        Treatment.REVERSIBLE_PSEUDONYMIZATION,
        corpus_version="hr/v1",
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=policy_repo,
        experiment_run_id="cross-process-test-run",
    )

    full = to_safe_dict(result)
    output = {
        "deterministic_key": deterministic_key(result),
        "payload_hash": full["audit"]["transformation"]["payload_hash"],
    }
    print(json.dumps(output, sort_keys=True))
    """
)


def _run_worker() -> dict:
    script = _WORKER_SCRIPT % {"repo_root": str(REPO_ROOT)}
    # Copy the parent environment (not replace it) -- on Windows, dropping
    # SYSTEMROOT/other OS-managed variables entirely breaks DLL loading for
    # unrelated dependencies (e.g. grpc/asyncio) before this script's own
    # imports even run. Only PYTHONPATH is added/overridden.
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, (
        f"worker process failed:\nstdout={completed.stdout}\nstderr={completed.stderr}"
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_deterministic_key_is_identical_across_two_independent_processes():
    """The core regression pin for blocker 4. Before the fix, this fails
    because the two processes' HMAC-keyed audit hashes differ and were part
    of the deterministic key; after the fix, they are stripped and the keys
    match exactly.
    """
    output_a = _run_worker()
    output_b = _run_worker()

    key_a = json.dumps(output_a["deterministic_key"], sort_keys=True)
    key_b = json.dumps(output_b["deterministic_key"], sort_keys=True)

    assert key_a == key_b, (
        "deterministic_key differed across two independent processes for the "
        "identical case/treatment/config -- see audit.py's per-process HMAC "
        "key and case_result.py's deterministic_key stripping"
    )


def test_the_audit_hmac_key_remains_genuinely_random_per_process_not_fixed():
    """The fix must never pin/derive a fixed HMAC key to make the above test
    pass -- audit.py's own security posture (a fresh, non-reproducible key
    per process) must be completely unchanged. Proven here by the two
    processes' *raw* payload_hash values differing for identical content.
    """
    output_a = _run_worker()
    output_b = _run_worker()

    assert output_a["payload_hash"] != output_b["payload_hash"], (
        "the two processes produced the same raw audit content hash for "
        "identical payload content -- this would mean the per-process HMAC "
        "key was fixed/derived instead of remaining genuinely random, which "
        "must never happen"
    )
