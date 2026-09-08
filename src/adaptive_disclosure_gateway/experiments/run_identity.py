"""Run-identity model for T10's experiment runner (issue #8).

Separates two kinds of metadata every run result needs, per
docs/experimental-design.md's "Output requirements" and the issue's
identity requirements:

- ``RunIdentity`` -- deterministic content. Two runs of the same case
  through the same treatment/policy/provider configuration produce an
  *equal* ``RunIdentity`` (as a value, field by field), so golden/regression
  comparisons can diff on this half alone.
- ``RunMetadata`` -- volatile per-execution metadata (a random run id, a
  wall-clock timestamp). Never compared for equality across runs; recorded
  purely for provenance.

Never carries a raw sensitive value, a pseudonym, ``requester_id``, or raw
task text -- every field here is an identifier, version string, category
name or classification label (CLAUDE.md's no-leak invariant).
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
SCHEMA_VERSION = "t10-experiment-runner-v1"

# T07/B3's frozen baseline commit (docs/experimental-design.md, issue #8):
# every B3 -- and, since B4 retains B3's analyzer/action-space machinery,
# every B4 -- result must name this explicitly rather than leaving the
# baseline implicit in the bare treatment code "b3"/"b4".
B3_TASK_AWARE_BASELINE_COMMIT = "31bce08b7ea6a5c905f7a20bbb4bb99a05682bab"

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
    ``treatment_baseline`` is populated only for B3/B4 (the frozen commit
    above); ``None`` for B0-B2, which have no comparable "baseline version"
    concept beyond the frozen code itself.
    """

    schema_version: str
    run_classification: RunClassification
    corpus_version: str
    case_id: str
    treatment_code: str
    treatment_name: str
    treatment_baseline: str | None
    policy_version: str | None
    matrix_cell: str | None
    provider_name: str
    provider_model_id: str
    provider_model_snapshot: str


@dataclass(frozen=True)
class RunMetadata:
    """Volatile, per-execution-only metadata. Never part of a golden/regression
    comparison -- see ``experiments/serialization.py``.
    """

    run_id: str
    generated_at: str


def new_run_metadata() -> RunMetadata:
    """A fresh, non-reproducible ``RunMetadata`` for one execution: a random
    run id and the current UTC timestamp in ISO-8601 form.
    """
    return RunMetadata(run_id=uuid.uuid4().hex, generated_at=datetime.now(UTC).isoformat())
