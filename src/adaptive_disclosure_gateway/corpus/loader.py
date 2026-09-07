"""Fail-closed YAML loading for the HR pilot corpus (T09 / issue #4, Phase A).

Every failure mode here -- unreadable file, invalid YAML, an unknown or
missing field, a mismatched ``sample_id`` -- raises ``CorpusLoadError``
rather than falling back to a default or skipping the offending case. Per
CLAUDE.md's no-leak invariant, ``CorpusLoadError`` messages never embed the
case's text, a span's value, or any other oracle/input content -- only the
file name, ``sample_id`` (an identifier, not sensitive content), a field
path and a pydantic error *type* code. In particular this module never lets
a lower-level exception's own message (a ``yaml.YAMLError``'s parse-context
snippet, a ``pydantic.ValidationError``'s ``input_value`` echo) reach a
raised message: every ``raise ... from None`` below is deliberate, and
``_describe_validation_errors`` reads only ``loc``/``type`` from each
pydantic error, never ``msg`` or ``input``.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import yaml
from pydantic import ValidationError

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle

_TOP_LEVEL_KEYS = {"input", "oracle"}


class CorpusLoadError(Exception):
    """Raised when a corpus case file fails to load or validate. See the
    module docstring for the no-leak contract this message type must honor.
    """


class CorpusCase(NamedTuple):
    """One corpus case's input and oracle, loaded side by side for whoever
    performs scoring. Nothing about this pairing gives the oracle a path
    into the pipeline -- only ``CorpusCaseInput.to_disclosure_request()``
    builds a ``DisclosureRequest``, and it never reads ``oracle``.
    """

    input: CorpusCaseInput
    oracle: CaseOracle


def _describe_validation_errors(exc: ValidationError) -> str:
    """A no-leak summary of a pydantic ``ValidationError``: field path and
    error *type* code only. Deliberately never reads ``error["msg"]`` or
    ``error["input"]`` -- pydantic embeds the offending input value in both,
    which for a corpus case could be case text or a span value.
    """
    parts = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"])
        parts.append(f"{loc} ({error['type']})")
    return "; ".join(parts)


def load_case(path: Path) -> CorpusCase:
    """Load and validate one case file. Raises ``CorpusLoadError`` for any
    structural, schema or cross-field problem -- never returns a partially
    valid case.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CorpusLoadError(
            f"could not read corpus case file {path.name}: {type(exc).__name__}"
        ) from None

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        # `from None`: yaml.YAMLError's own message frequently echoes a
        # snippet of the offending document content.
        raise CorpusLoadError(
            f"corpus case file {path.name} is not valid YAML: {type(exc).__name__}"
        ) from None

    if not isinstance(raw, dict):
        raise CorpusLoadError(f"corpus case file {path.name} must contain a YAML mapping")

    unknown_keys = sorted(set(raw) - _TOP_LEVEL_KEYS)
    if unknown_keys:
        raise CorpusLoadError(
            f"corpus case file {path.name} has unknown top-level key(s): {unknown_keys}"
        )
    missing_keys = sorted(_TOP_LEVEL_KEYS - set(raw))
    if missing_keys:
        raise CorpusLoadError(
            f"corpus case file {path.name} is missing required top-level key(s): {missing_keys}"
        )

    try:
        case_input = CorpusCaseInput.model_validate(raw["input"])
    except ValidationError as exc:
        raise CorpusLoadError(
            f"corpus case file {path.name}: input schema validation failed: "
            f"{_describe_validation_errors(exc)}"
        ) from None

    try:
        oracle = CaseOracle.model_validate(raw["oracle"])
    except ValidationError as exc:
        raise CorpusLoadError(
            f"corpus case file {path.name}: oracle schema validation failed: "
            f"{_describe_validation_errors(exc)}"
        ) from None

    if case_input.sample_id != oracle.sample_id:
        raise CorpusLoadError(
            f"corpus case file {path.name}: input.sample_id and oracle.sample_id do not match"
        )

    return CorpusCase(input=case_input, oracle=oracle)


def load_corpus(directory: str | Path) -> list[CorpusCase]:
    """Load every ``*.yaml`` case file directly under ``directory``, sorted
    by file name for a deterministic order. Raises ``CorpusLoadError`` --
    and loads nothing -- the moment any single case fails, and again if two
    files claim the same ``sample_id``.
    """
    cases: list[CorpusCase] = []
    seen_sample_ids: set[str] = set()
    for path in sorted(Path(directory).glob("*.yaml")):
        case = load_case(path)
        if case.input.sample_id in seen_sample_ids:
            raise CorpusLoadError(
                f"duplicate sample_id across corpus case files: {case.input.sample_id!r}"
            )
        seen_sample_ids.add(case.input.sample_id)
        cases.append(case)
    return cases
