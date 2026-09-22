"""Fail-closed YAML loading for the HR pilot corpus (T09 / issue #4, Phase A).

Every failure mode here -- unreadable file, invalid YAML, an unknown or
missing field, a mismatched ``sample_id``, a file name that disagrees with
its own ``input.sample_id`` -- raises ``CorpusLoadError``
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
from adaptive_disclosure_gateway.corpus.models import (
    FROZEN_CATEGORIES_BY_DOMAIN,
    REGISTERED_CORPUS_DOMAINS,
    TASK_FAMILIES_BY_DOMAIN,
)
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


def _check_domain_consistency(path: Path, case_input: CorpusCaseInput, oracle: CaseOracle) -> None:
    """Reject a case whose annotations reach into another domain's frozen
    vocabulary (T24 / issue #37).

    The schema-level ``CorpusCategory``/``CorpusTaskFamily`` types already
    reject an invented category or family. They cannot reject a *real* one
    borrowed from the wrong domain -- an HR case annotating ``penalty_amount``
    or a Contracts case annotating ``salary`` -- because both live in the
    same union. That check needs the case's own ``input.domain``, which is
    why it lives here, alongside every other cross-half consistency rule
    (``sample_id`` agreement, file-name agreement, duplicate detection).

    Fails closed on an unregistered domain rather than accepting whatever
    vocabulary the case happens to name.

    No-leak: names only the file, the domain, a category name and a task
    family -- all schema vocabulary, never a span ``value`` or case text.
    """
    domain = case_input.domain
    allowed_categories = FROZEN_CATEGORIES_BY_DOMAIN.get(domain)
    allowed_families = TASK_FAMILIES_BY_DOMAIN.get(domain)
    if allowed_categories is None or allowed_families is None:
        raise CorpusLoadError(
            f"corpus case file {path.name} declares input.domain {domain!r}, which is "
            f"not a registered corpus domain: {list(REGISTERED_CORPUS_DOMAINS)}"
        )

    # Bound to a local named for what it is -- a task-family *name* -- rather
    # than interpolating `case_input.task_family.value` into the message:
    # tests/test_no_sensitive_value_in_raises.py rejects a `.value` attribute
    # access inside a raise, and that rule is right to be blunt rather than
    # case-by-case. The family name is schema vocabulary, never case content.
    family_name = str(case_input.task_family)
    if family_name not in allowed_families:
        raise CorpusLoadError(
            f"corpus case file {path.name}: task_family {family_name!r} "
            f"does not belong to domain {domain!r}"
        )

    annotated: list[tuple[str, str]] = [
        ("oracle.expected_spans", span.category) for span in oracle.expected_spans
    ]
    annotated.extend(
        ("oracle.reconstruction", expectation.category) for expectation in oracle.reconstruction
    )
    annotated.extend(
        ("oracle.answer_depends_on_categories", category)
        for category in (oracle.answer_depends_on_categories or [])
    )
    annotated.extend(
        ("oracle.obligation_relations", category)
        for relation in oracle.obligation_relations
        for category in relation.depends_on_categories
    )
    annotated.extend(
        ("oracle.utility_references", reference.category)
        for reference in (oracle.utility_references or [])
    )

    foreign = sorted(
        {
            f"{field}:{category}"
            for field, category in annotated
            if category not in allowed_categories
        }
    )
    if foreign:
        raise CorpusLoadError(
            f"corpus case file {path.name}: category/categories not frozen for domain "
            f"{domain!r}: {foreign}"
        )


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

    _check_domain_consistency(path, case_input, oracle)

    if path.stem != case_input.sample_id:
        raise CorpusLoadError(
            f"corpus case file {path.name} does not match its own input.sample_id "
            f"{case_input.sample_id!r} -- the file's base name and sample_id must be identical"
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
