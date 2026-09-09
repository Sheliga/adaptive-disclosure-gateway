"""T20 / issue #28, slice 1: ``application/examples.py`` -- prepared HR
examples for the guided demo, sourced from the frozen corpus INPUT half
only. These tests use the real ``corpus/hr/v1/cases`` fixture directory
(the same one T09/T10 already load), so a real regression in the
input-only projection can actually fail them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_disclosure_gateway.application.examples import (
    ExampleNotFoundError,
    ExampleSummary,
    list_examples,
    load_example,
)
from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput

CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"


def test_list_examples_returns_summaries_for_every_case_file():
    examples = list_examples(CORPUS_DIR)

    assert len(examples) == 13
    assert all(isinstance(example, ExampleSummary) for example in examples)
    example_ids = {example.example_id for example in examples}
    assert "hr_team_summary_001" in example_ids


def test_list_examples_summary_carries_safe_metadata_only():
    examples = list_examples(CORPUS_DIR)
    team_summary = next(e for e in examples if e.example_id == "hr_team_summary_001")

    assert team_summary.domain == "hr"
    assert team_summary.purpose == "team_summary"
    assert "department" in team_summary.task.lower()
    assert team_summary.character_count > 0


def test_load_example_returns_a_corpus_case_input():
    case_input = load_example(CORPUS_DIR, "hr_team_summary_001")

    assert isinstance(case_input, CorpusCaseInput)
    assert case_input.sample_id == "hr_team_summary_001"
    assert "Renata Farias" in case_input.text


def test_load_example_raises_for_an_unknown_id():
    with pytest.raises(ExampleNotFoundError):
        load_example(CORPUS_DIR, "does_not_exist")
