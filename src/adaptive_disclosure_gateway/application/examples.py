"""Prepared HR examples for the guided demo (T20 / issue #28, slice 1).

Sourced from the frozen HR pilot corpus's INPUT half only
(``corpus/hr/v1/cases/``, loaded via the existing ``corpus.loader.load_corpus``
-- reused verbatim here, not reimplemented, per this ticket's "no duplicated
logic" rule). These are synthetic, controlled HR cases built for T09's
corpus-based experiment (issue #4), not real personal data. Reusing them
here as prepared examples for a guided UI does NOT make this demo an
evaluation surface: the oracle half of every case this module loads
(``CaseOracle``, expected spans, expected answer, reconstruction
expectations) is discarded immediately and never named, stored, or returned
by anything in this module -- see
``tests/test_application_ground_truth_isolation.py``, which pins that by
AST inspection across the whole ``application`` package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import load_corpus


class ExampleNotFoundError(Exception):
    """Raised when ``load_example`` is asked for an ``example_id`` the
    directory has no case file for. Names the id only -- an identifier, not
    sensitive content, exactly like the corpus loader's own ``sample_id``
    usage in its own error messages.
    """


@dataclass(frozen=True)
class ExampleSummary:
    """Safe metadata for a guided-demo example picker -- never anything
    from the case's oracle half, only what ``CorpusCaseInput`` itself
    already exposes as non-sensitive identifying metadata.
    """

    example_id: str
    title: str
    domain: str
    purpose: str
    task: str
    character_count: int


def _to_summary(case_input: CorpusCaseInput) -> ExampleSummary:
    return ExampleSummary(
        example_id=case_input.sample_id,
        # No separate human-authored title exists in the corpus schema yet
        # -- sample_id doubles as the display title for this slice.
        title=case_input.sample_id,
        domain=case_input.domain,
        purpose=case_input.purpose,
        task=case_input.task,
        character_count=len(case_input.text),
    )


def list_examples(directory: str | Path) -> tuple[ExampleSummary, ...]:
    """List every prepared example under ``directory``, in the same
    deterministic (file-name-sorted) order ``load_corpus`` already produces.

    ``load_corpus`` loads both halves of each case file (input and oracle)
    -- reused as-is rather than duplicated -- but only ``case.input`` is
    ever read here; the oracle half of every loaded case is discarded
    immediately.
    """
    cases = load_corpus(directory)
    return tuple(_to_summary(case.input) for case in cases)


def load_example(directory: str | Path, example_id: str) -> CorpusCaseInput:
    """Load one example's input by id.

    Raises ``ExampleNotFoundError`` if no case file under ``directory`` has
    this ``sample_id``. Loads (and discards) the oracle half exactly like
    ``list_examples`` above -- only the matching case's ``input`` is ever
    returned.
    """
    cases = load_corpus(directory)
    for case in cases:
        if case.input.sample_id == example_id:
            return case.input
    raise ExampleNotFoundError(f"no example found with example_id={example_id!r}")
