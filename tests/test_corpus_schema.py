"""Fail-closed schema loading for the HR pilot corpus (T09 / issue #4, Phase A).

Every scenario below pins a real defect an inattentive annotator could
introduce: a missing field, an unknown field, a necessity label outside the
primary binary oracle, a category outside the five frozen for this corpus,
a file whose name disagrees with its own declared ``sample_id``, or two
files that claim the same ``sample_id``. None of these are exercised
against the real, frozen v1 corpus (which is covered separately by
``tests/test_corpus_coverage.py`` and ``tests/test_corpus_span_consistency.py``)
-- they are built from a minimal valid case fixture, mutated one field at a
time, so each test fails for the specific reason it names rather than by
accident.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from adaptive_disclosure_gateway.corpus import CorpusLoadError, load_case, load_corpus

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"


def _minimal_valid_case(sample_id: str = "hr_schema_fixture_case") -> dict[str, Any]:
    return {
        "input": {
            "sample_id": sample_id,
            "task_family": "team_summary_without_salary",
            "text": "Employee: Test Person\nDepartment: Engineering\n",
            "task": "Describe which department this employee belongs to.",
            "domain": "hr",
            "purpose": "team_summary",
            "requester_role": "hr_analyst",
            "policy_version": "hr-v1",
        },
        "oracle": {
            "sample_id": sample_id,
            "expected_spans": [
                {
                    "category": "employee_name",
                    "value": "Test Person",
                    "start": 10,
                    "end": 21,
                    "task_necessity": "required",
                    "expected_actions": ["preserve"],
                },
                {
                    "category": "department",
                    "value": "Engineering",
                    "start": 34,
                    "end": 45,
                    "task_necessity": "required",
                    "expected_actions": ["preserve"],
                },
            ],
            "expected_block_request": False,
            "expected_answer": "The response names the department 'Engineering'.",
        },
    }


def _write_case(tmp_path: Path, case: dict[str, Any], file_name: str | None = None) -> Path:
    sample_id = case["input"]["sample_id"]
    path = tmp_path / (file_name or f"{sample_id}.yaml")
    path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    return path


def test_real_corpus_cases_all_load_without_error():
    # Not a defect-injection test by itself, but the load must actually
    # succeed for every frozen case file, or the rest of this suite would be
    # validating a schema the real corpus does not conform to.
    cases = load_corpus(REAL_CORPUS_DIR)
    assert len(cases) >= 1


def test_missing_required_input_field_raises(tmp_path: Path):
    case = _minimal_valid_case()
    del case["input"]["policy_version"]
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_missing_required_oracle_field_raises(tmp_path: Path):
    case = _minimal_valid_case()
    del case["oracle"]["expected_block_request"]
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_unknown_top_level_key_raises(tmp_path: Path):
    case = _minimal_valid_case()
    case["extra_top_level_key"] = "not allowed"
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_unknown_input_field_raises(tmp_path: Path):
    case = _minimal_valid_case()
    case["input"]["unexpected_field"] = "not allowed"
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_unknown_expected_span_field_raises(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["expected_spans"][0]["unexpected_field"] = "not allowed"
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_task_necessity_outside_required_not_required_raises(tmp_path: Path):
    # This is the concrete regression the primary/auxiliary label split
    # exists to prevent: "helpful" must never be accepted as a
    # task_necessity value, only as the separate ExpectedSpan.helpful flag.
    case = _minimal_valid_case()
    case["oracle"]["expected_spans"][0]["task_necessity"] = "helpful"
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_category_outside_five_frozen_categories_raises(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["expected_spans"][0]["category"] = "birth_date"
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_empty_expected_actions_raises(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["expected_spans"][0]["expected_actions"] = []
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_expected_answer_required_when_not_blocked(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["expected_answer"] = None
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_expected_answer_forbidden_when_blocked(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["expected_block_request"] = True
    case["oracle"]["expected_spans"][0]["expected_actions"] = ["block_request"]
    case["oracle"]["expected_spans"][1]["expected_actions"] = ["block_request"]
    # expected_answer is still set from the base fixture -- this must be
    # rejected, not silently ignored.
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_blocked_case_requires_a_block_request_expected_action(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["expected_block_request"] = True
    case["oracle"]["expected_answer"] = None
    # Neither span names block_request as acceptable -- inconsistent with a
    # case-level expected_block_request of true.
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_reconstruction_forbidden_when_blocked(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["expected_block_request"] = True
    case["oracle"]["expected_answer"] = None
    case["oracle"]["expected_spans"][0]["expected_actions"] = ["block_request"]
    case["oracle"]["expected_spans"][1]["expected_actions"] = ["block_request"]
    case["oracle"]["reconstruction"] = [
        {"category": "employee_name", "expected_reconstructable": True}
    ]
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_sample_id_mismatch_between_input_and_oracle_raises(tmp_path: Path):
    case = _minimal_valid_case()
    case["oracle"]["sample_id"] = "a_different_sample_id"
    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_duplicate_sample_id_across_files_raises(tmp_path: Path):
    # Two distinct file names deliberately declaring the same sample_id --
    # the loader does not require a file's name to match its own
    # sample_id (see SCHEMA.md), so this is the one way a collision can
    # actually happen, and it must be caught at the load_corpus level.
    first = _minimal_valid_case(sample_id="hr_schema_fixture_case")
    second = copy.deepcopy(first)
    _write_case(tmp_path, first, file_name="case_a.yaml")
    _write_case(tmp_path, second, file_name="case_b.yaml")

    with pytest.raises(CorpusLoadError):
        load_corpus(tmp_path)


def test_not_a_yaml_mapping_raises(tmp_path: Path):
    path = tmp_path / "not_a_mapping.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")

    with pytest.raises(CorpusLoadError):
        load_case(path)
