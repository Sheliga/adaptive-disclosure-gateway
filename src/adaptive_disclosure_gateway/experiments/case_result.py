"""One case's complete, serializable experiment result (T10 / issue #8).

Combines a ``CaseExecution`` (real treatment run, ground-truth-free), a
``CaseScore`` (post-hoc scoring against the oracle) and run
identity/metadata into one structure, plus the safe/serializable dict form
every artifact this ticket writes is built from.

No-leak guarantee: ``to_safe_dict`` never includes a raw sensitive value, a
pseudonym/original mapping, ``requester_id``, or raw task/response text --
only identifiers, enum values, counts, rates, booleans and byte lengths.
The underlying ``AuditRecord`` is already safe by construction
(``audit.py``'s own no-leak invariant) except for its optional ``raw``
field, which this module drops unconditionally regardless of whether the
caller happened to populate it -- defense in depth, not just trusting that
no caller ever passes ``capture_raw_values_for_controlled_experiment=True``
into a pilot run.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any

from .execution import CaseExecution
from .run_identity import RunIdentity, RunMetadata
from .scoring import CaseScore

# Fields of RunMetadata considered volatile for golden/regression comparison
# purposes -- see docs/experimental-design.md's "Separate deterministic
# content from volatile metadata" requirement, implemented here as "strip
# these before comparing/golden-testing a serialized result".
VOLATILE_METADATA_FIELDS = ("run_id", "generated_at")

# Measurement fields that are also excluded from a *golden* (byte-for-byte
# regression) comparison: real wall-clock timing is never reproducible
# between runs even when every deterministic input is identical. These stay
# in the safe dict itself (they are real, useful, non-sensitive metrics) --
# only ``deterministic_key`` below strips them, for callers that want to
# diff two runs' *decisions* while ignoring how long each took.
_MEASUREMENT_KEYS = ("stage_timings", "provider_metrics")


def _to_plain(value: Any) -> Any:
    """Recursively convert a value tree (pydantic ``BaseModel``s, plain
    dataclasses, enums, mappings, sequences) into plain JSON-safe Python
    values, without ever using ``dataclasses.asdict`` -- which does not know
    how to descend into a pydantic model field.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "model_dump"):  # pydantic BaseModel
        return _to_plain(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain(item) for item in value]
    return value


def _dataclass_safe_dict(obj: Any) -> Any:
    if obj is None:
        return None
    return _to_plain(obj)


@dataclass(frozen=True)
class CaseResult:
    identity: RunIdentity
    metadata: RunMetadata
    score: CaseScore
    case_execution: CaseExecution


def to_safe_dict(case_result: CaseResult) -> dict[str, Any]:
    """The complete, safe-to-persist/log/serve representation of one case
    result. Never includes raw values, the audit's optional ``raw`` capture,
    a pseudonym/original mapping, or ``requester_id``.
    """
    execution = case_result.case_execution
    audit_dict = _dataclass_safe_dict(execution.execution.audit)
    audit_dict.pop("raw", None)  # defense in depth -- see module docstring

    return {
        "identity": _dataclass_safe_dict(case_result.identity),
        "metadata": _dataclass_safe_dict(case_result.metadata),
        "stage_timings": _dataclass_safe_dict(execution.stage_timings),
        "provider_metrics": _dataclass_safe_dict(execution.provider_metrics),
        "b4_metadata": _dataclass_safe_dict(execution.b4_metadata),
        "status": execution.execution.disclosure_result.status,
        "score": {
            "conformance": _dataclass_safe_dict(case_result.score.conformance),
            "exposure": _dataclass_safe_dict(case_result.score.exposure),
            "unnecessary_disclosure": _dataclass_safe_dict(
                case_result.score.unnecessary_disclosure
            ),
            "utility": _dataclass_safe_dict(case_result.score.utility),
            "reconstruction": _dataclass_safe_dict(case_result.score.reconstruction),
            "outcomes": _dataclass_safe_dict(case_result.score.outcomes),
            "ordinary_utility_failure": case_result.score.ordinary_utility_failure,
        },
        "audit": audit_dict,
    }


def deterministic_key(case_result: CaseResult) -> dict[str, Any]:
    """The subset of ``to_safe_dict`` that is byte-for-byte reproducible
    across independent runs of the same case/treatment/config: excludes
    ``metadata`` (run id, timestamp) and every wall-clock measurement
    (``stage_timings``, ``provider_metrics.latency_ms``). Two calls to
    ``execute_case``/``score_case`` for the same inputs must always produce
    an *equal* ``deterministic_key`` even though their full
    ``to_safe_dict`` differs in ``metadata`` and timing.
    """
    full = to_safe_dict(case_result)
    stripped = dict(full)
    for key in _MEASUREMENT_KEYS:
        stripped.pop(key, None)
    stripped.pop("metadata", None)
    provider_metrics = full.get("provider_metrics")
    if provider_metrics is not None:
        stripped["provider_metrics_deterministic"] = {
            key: value for key, value in provider_metrics.items() if key != "latency_ms"
        }
    return stripped
