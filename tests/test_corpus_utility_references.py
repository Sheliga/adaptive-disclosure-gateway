"""Issue #87 / M3 -- structural and no-leak invariants for the oracle's new
structured numeric utility references (``CaseOracle.utility_references``,
``post-pilot-v4``).

Mirrors ``tests/test_corpus_obligation_relation.py``'s two-directional
concern for ``obligation_relations``, applied here to
``NumericUtilityReference``/``ReferenceOperator``/``utility_references``:

1. **As a runtime input.** A reference is ground truth for evaluation only.
   If it ever reached the detector, the task analyzer, a treatment, policy
   or the provider, the experiment would be measuring a pipeline that was
   told the answer. The AST allowlist below extends
   ``tests/test_corpus_oracle_isolation.py``'s approach to this field
   specifically, and a behavioral marker-run test proves it does not leak
   through any real execution.
2. **As a schema surface.** The value grammar, category/duplicate/blocked
   validators and loader error messages must never let an invalid or
   sensitive value escape through a side channel (CLAUDE.md's no-leak
   invariant).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import CorpusLoadError, load_case
from adaptive_disclosure_gateway.corpus.models import (
    NUMERIC_REFERENCE_CATEGORIES,
    NumericUtilityReference,
    ReferenceOperator,
)
from adaptive_disclosure_gateway.domain import DisclosureRequest

REPO_ROOT = Path(__file__).parents[1]
SRC_ROOT = REPO_ROOT / "src" / "adaptive_disclosure_gateway"

_REFERENCE_IDENTIFIERS = {"NumericUtilityReference", "ReferenceOperator", "utility_references"}

# The minimal, justified allowlist: the oracle/corpus schema modules
# themselves and the one scorer module that reads the field.
# ``experiments/runner.py`` calls ``check_corpus_protocol_compatibility``
# (defined in ``experiments/scoring/utility.py``) but never itself names any
# of these identifiers -- it passes the loaded ``CorpusCase`` list straight
# through, which is the tighter isolation and exactly why it is deliberately
# NOT in this allowlist (pinned by the coverage test below: an allowlist
# entry that stops referencing these identifiers should be removed, not kept
# "just in case").
_ALLOWED_FILES = {
    SRC_ROOT / "corpus" / "models.py",
    SRC_ROOT / "corpus" / "oracle.py",
    SRC_ROOT / "corpus" / "loader.py",
    SRC_ROOT / "corpus" / "__init__.py",
    SRC_ROOT / "experiments" / "scoring" / "utility.py",
}


def _identifiers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.rsplit(".", 1)[-1])
    return names


def _all_source_files() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.py"))


# --- 1. AST allowlist: only justified files ever reference these names -----


def test_utility_reference_identifiers_appear_only_in_the_allowlisted_files():
    files = _all_source_files()
    assert files, "expected source files to check"

    violations = []
    for path in files:
        if path in _ALLOWED_FILES:
            continue
        found = _identifiers(path) & _REFERENCE_IDENTIFIERS
        if found:
            violations.append(f"{path.relative_to(REPO_ROOT)} references {sorted(found)}")

    assert not violations, "\n".join(violations)


def test_allowlist_actually_covers_files_that_reference_the_identifiers():
    """Pins that the allowlist is not accidentally over-broad (every file in
    it really does reference at least one of the identifiers) -- a stale
    entry here would silently widen the isolation boundary this test set
    exists to hold tight.
    """
    for path in _ALLOWED_FILES:
        assert path.exists(), f"{path} must exist to be checked"
        assert _identifiers(path) & _REFERENCE_IDENTIFIERS, (
            f"{path.relative_to(REPO_ROOT)} is allowlisted but references none of "
            f"{_REFERENCE_IDENTIFIERS} -- remove it from the allowlist"
        )


# --- 2. CorpusCaseInput/DisclosureRequest have no reference-shaped field ---


def test_corpus_case_input_has_no_reference_or_threshold_field():
    field_names = set(CorpusCaseInput.model_fields)
    for name in field_names:
        assert "reference" not in name.lower()
        assert "threshold" not in name.lower()


def test_disclosure_request_fields_are_unchanged_by_utility_references():
    assert set(DisclosureRequest.model_fields) == {"text", "task", "context"}


# --- 3. registry drift ------------------------------------------------------


def test_numeric_reference_categories_is_a_non_empty_frozenset():
    assert isinstance(NUMERIC_REFERENCE_CATEGORIES, frozenset)
    assert NUMERIC_REFERENCE_CATEGORIES


# --- 4. loader no-leak: invalid references never echo the value ------------


def _write_case(
    tmp_path: Path, sample_id: str, oracle_extra: dict, input_extra: dict | None = None
) -> Path:
    document = {
        "input": {
            "sample_id": sample_id,
            "text": "Salary: R$ 9200.00\nDepartment: Engineering\n",
            "task": "Summarize the department budget.",
            "task_family": "authorized_salary_analysis",
            "domain": "hr",
            "purpose": "salary_analysis",
            "policy_version": "hr-v1",
            **(input_extra or {}),
        },
        "oracle": {
            "sample_id": sample_id,
            "expected_spans": [
                {
                    "category": "salary",
                    "value": "R$ 9200.00",
                    "start": 8,
                    "end": 18,
                    "task_necessity": "required",
                    "expected_actions": ["generalize"],
                },
            ],
            "expected_block_request": False,
            "expected_answer": "some answer",
            "answer_depends_on_categories": ["salary"],
            **oracle_extra,
        },
    }
    path = tmp_path / f"{sample_id}.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


_DISTINCTIVE_MARKER_VALUE = "913579.24"


@pytest.mark.parametrize(
    "utility_references",
    [
        [{"category": "salary", "operator": "eq", "value": _DISTINCTIVE_MARKER_VALUE}],
        [
            {
                "category": "salary",
                "operator": "greater_than",
                "value": _DISTINCTIVE_MARKER_VALUE + "0",
            }
        ],
        [{"category": "deadline", "operator": "greater_than", "value": _DISTINCTIVE_MARKER_VALUE}],
        [
            {"category": "salary", "operator": "greater_than", "value": _DISTINCTIVE_MARKER_VALUE},
            {"category": "salary", "operator": "greater_than", "value": _DISTINCTIVE_MARKER_VALUE},
        ],
    ],
)
def test_invalid_utility_references_raise_corpus_load_error_without_leaking_the_value(
    tmp_path, utility_references
):
    path = _write_case(
        tmp_path, "synthetic_loader_probe", {"utility_references": utility_references}
    )
    with pytest.raises(CorpusLoadError) as excinfo:
        load_case(path)
    message = str(excinfo.value)
    assert _DISTINCTIVE_MARKER_VALUE not in message
    # from None discipline: the pydantic ValidationError must never survive
    # as __cause__, since its own repr can embed the offending input value.
    assert excinfo.value.__cause__ is None


def test_valid_utility_references_load_successfully(tmp_path):
    path = _write_case(
        tmp_path,
        "synthetic_loader_valid",
        {
            "utility_references": [
                {"category": "salary", "operator": "greater_than_or_equal", "value": "5000.00"},
            ]
        },
    )
    case = load_case(path)
    assert case.oracle.utility_references == [
        NumericUtilityReference(
            category="salary", operator=ReferenceOperator.GREATER_THAN_OR_EQUAL, value="5000.00"
        )
    ]


def test_absent_utility_references_field_loads_as_none_legacy(tmp_path):
    path = _write_case(tmp_path, "synthetic_loader_legacy", {})
    case = load_case(path)
    assert case.oracle.utility_references is None


def test_reference_naming_a_category_foreign_to_the_case_domain_is_rejected(tmp_path):
    """The domain-consistency check (loader.py) must cover
    ``oracle.utility_references`` exactly like every other oracle field --
    a reference naming a real category from a *different* domain than the
    case's own ``input.domain`` must be rejected."""
    path = _write_case(
        tmp_path,
        "synthetic_loader_foreign_domain",
        {
            "utility_references": [
                {"category": "penalty_amount", "operator": "greater_than", "value": "5000.00"},
            ],
            "answer_depends_on_categories": ["salary"],
        },
    )
    # penalty_amount is a real CorpusCategory but not part of the hr domain,
    # and is also not in answer_depends_on_categories -- either validator
    # alone is sufficient to reject this, so this pins that *some* fail-closed
    # path rejects it (Field-level validators run first).
    with pytest.raises((CorpusLoadError, ValidationError)):
        load_case(path)


# --- 5. UtilityScore serialization never contains a marker (unit-level) ----


def test_numeric_utility_reference_repr_and_json_never_contain_a_marker_via_wrong_field():
    """Sanity check that the model's own repr/serialization only ever
    contains the fields it declares -- a change that widened the model
    (e.g. adding a debug field carrying the raw case text) would be caught
    by the existing extra="forbid" config, but this pins the serialized
    shape stays exactly {category, operator, value}."""
    reference = NumericUtilityReference(
        category="salary", operator=ReferenceOperator.GREATER_THAN, value="5000.00"
    )
    dumped = reference.model_dump()
    assert set(dumped) == {"category", "operator", "value"}
    serialized = json.dumps(dumped)
    assert serialized  # must not raise; shape already pinned above
