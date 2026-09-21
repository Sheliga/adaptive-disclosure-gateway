"""Run-identity model for T10's experiment runner (issue #8).

Separates two kinds of metadata every run result needs, per
docs/experimental-design.md's "Output requirements" and the issue's
identity requirements:

- ``RunIdentity`` -- deterministic content. Two runs of the same case
  through the same treatment/policy/provider configuration produce an
  *equal* ``RunIdentity`` (as a value, field by field), so golden/regression
  comparisons can diff on this half alone.
- ``RunMetadata`` -- volatile per-execution metadata (a shared experiment
  run id, a per-execution id, a wall-clock timestamp). Never compared for
  equality across runs; recorded purely for provenance.

Never carries a raw sensitive value, a pseudonym, ``requester_id``, or raw
task text -- every field here is an identifier, version string, category
name or classification label (CLAUDE.md's no-leak invariant).

PR #35 review, blocker 1 (B4 versioned with the wrong commit): B3 and B4 are
two distinct frozen implementations, not one. ``treatment_version`` names
the commit that froze the implementation actually producing *this* result
(B3's own commit for a B3 result, B4's own -- different -- commit for a B4
result); ``task_aware_baseline_version`` separately names the B3 baseline a
result's task-analysis/action-space machinery depends on (identical to
``treatment_version`` for a B3 result, since B3 depends on itself; B3's own
commit for a B4 result, since B4 retains B3's analyzer/action-space
machinery on top of its own policy layer). No B4 result may ever report B3's
commit as its own ``treatment_version`` -- see
``tests/test_experiments_core.py::test_b4_treatment_version_is_never_b3s_baseline_commit``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

# Schema version for the runner's machine-readable output. Bump this any
# time a field is added/removed/renamed on any of the dataclasses this
# package serializes -- consumers (later statistical analysis, a UI) key
# compatibility off this string, not off guessing from field presence.
# Bumped to v2 for PR #35 review: RunIdentity's treatment_baseline field was
# split into treatment_version/task_aware_baseline_version (blocker 1),
# RunMetadata gained experiment_run_id/case_execution_id in place of a bare
# run_id (blocker 5), and CaseExecution/CaseScore gained detector and
# resource_metrics fields (blockers 2, 3).
# Bumped to v3 for T22 / issue #30: ProviderCallMetrics gained the four
# provider-reported token-usage fields (input_tokens, output_tokens,
# cache_creation_input_tokens, cache_read_input_tokens), which are part of
# every serialized CaseResult. They are None under FakeProvider -- the shape
# changed, so the version changes; the M2/HR and Contracts v1 artifacts
# already on disk stay correctly labeled v2 and are not rewritten.
# Bumped to v4 for M3 Gate 6 / issue #38: RunIdentity gained protocol_id
# (docs/research/post-pilot-protocol-v2.md's provenance/version-boundary
# section) -- every result row now names the post-pilot protocol version
# that scored it, never left implicit or only present at the manifest
# level. Every artifact already on disk (schema v2/v3) stays exactly as
# written and is not rewritten.
SCHEMA_VERSION = "t10-experiment-runner-v4"

# T07/B3's frozen baseline commit (docs/experimental-design.md, issue #8):
# every B3 -- and, since B4 retains B3's analyzer/action-space machinery,
# every B4 -- result must name this explicitly rather than leaving the
# baseline implicit in the bare treatment code "b3"/"b4".
B3_TASK_AWARE_BASELINE_COMMIT = "31bce08b7ea6a5c905f7a20bbb4bb99a05682bab"

# T08/B4's own frozen implementation commit -- distinct from B3's baseline
# above (PR #35 review, blocker 1). Every B4 result's own treatment_version
# must be this commit, never B3's.
B4_POLICY_GOVERNED_COMMIT = "5abea8514fa10ac64b9bc3714bbfd3f18682f713"

RunClassification = Literal["pilot_development", "held_out_confirmatory"]

# The only run classification this ticket's pilot is permitted to produce
# (docs/experimental-design.md's development/evaluation separation
# requirement): corpus/hr/v1 was used during B3/B4 development, so any
# result against it is pilot/development evidence, never confirmatory.
PILOT_DEVELOPMENT: RunClassification = "pilot_development"
HELD_OUT_CONFIRMATORY: RunClassification = "held_out_confirmatory"


@dataclass(frozen=True)
class RunIdentity:
    """Deterministic identity of one case run through one treatment.

    ``matrix_cell`` is ``None`` for every treatment except B4 -- Policy
    Governed, where it is populated (never invented) from the exact
    identifier ``transformations/policy_governed.py`` already emits as an
    OTel span attribute for that case (see ``experiments/execution.py``'s
    span extraction) -- this module never recomputes or reformats it.

    ``treatment_version`` and ``task_aware_baseline_version`` are populated
    only for B3/B4 (frozen commits above); both ``None`` for B0-B2, which
    have no comparable "baseline version" concept beyond the frozen code
    itself. For a B3 result the two fields are equal (B3 depends on its own
    baseline); for a B4 result they differ (B4's own, later commit vs. the
    B3 baseline its analyzer/action-space machinery still depends on) -- see
    the module docstring for why conflating them was PR #35 review's
    blocker 1.

    ``protocol_id`` (M3 Gate 6 / issue #38) is the post-pilot protocol
    version (``post_pilot_protocol.CURRENT_PROTOCOL_ID``) that scored this
    result -- validated against ``FROZEN_PROTOCOL_IDS`` at construction time
    (``execution.py``), never a free string a caller could misspell. It is
    always populated (never ``None``): every result produced by this
    codebase is scored under exactly one, known protocol version.
    """

    schema_version: str
    run_classification: RunClassification
    corpus_version: str
    case_id: str
    treatment_code: str
    treatment_name: str
    treatment_version: str | None
    task_aware_baseline_version: str | None
    policy_version: str | None
    matrix_cell: str | None
    provider_name: str
    provider_model_id: str
    provider_model_snapshot: str
    protocol_id: str


@dataclass(frozen=True)
class RunMetadata:
    """Volatile, per-execution-only metadata. Never part of a golden/regression
    comparison -- see ``experiments/case_result.py``'s ``deterministic_key``.

    PR #35 review, blocker 5 (ambiguous run identity): ``experiment_run_id``
    is shared by every case execution, summary and contextual comparison
    produced by one pilot invocation -- callers pass the *same* value into
    every ``new_run_metadata`` call for that pilot run (see
    ``runner.run_pilot``). ``case_execution_id`` is the per-execution
    identifier the old, ambiguously-named ``run_id`` field actually was --
    unique per case x treatment x contextual configuration, never shared
    across executions. Never call either field ``run_id`` again: that name
    is exactly what let a manifest's run id and 65 unrelated per-case ids
    both plausibly claim to be "the" run id with no way to tell which was
    meant.
    """

    experiment_run_id: str
    case_execution_id: str
    generated_at: str


def new_experiment_run_id() -> str:
    """A fresh id identifying one whole pilot invocation -- generate this
    exactly once per pilot run and thread it into every
    ``new_run_metadata`` call and artifact for that run (never regenerate
    it per case or per treatment).
    """
    return uuid.uuid4().hex


def new_run_metadata(experiment_run_id: str) -> RunMetadata:
    """A fresh ``RunMetadata`` for one case execution: the caller-supplied,
    shared ``experiment_run_id`` for the whole pilot run, a fresh
    non-reproducible ``case_execution_id`` for this one execution, and the
    current UTC timestamp in ISO-8601 form.
    """
    return RunMetadata(
        experiment_run_id=experiment_run_id,
        case_execution_id=uuid.uuid4().hex,
        generated_at=datetime.now(UTC).isoformat(),
    )
