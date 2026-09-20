"""Per-domain corpus schema validation (T24 / issue #37).

Before this ticket the corpus schema was HR-only: ``corpus/models.py``
hardcoded an ``HrCategory`` ``Literal`` and an HR-only ``TaskFamily``, so a
Contracts case could not be expressed at all (documented as the one expected,
non-semantic T24 change in ``docs/contracts-policy-matrix.md``'s "Known
limitations").

The extension is deliberately the smallest one that works: a per-domain
registry of frozen categories and task families, cross-checked against the
case's own ``input.domain`` at load time -- the loader is already where every
cross-half consistency rule lives (``sample_id`` agreement, file-name
agreement, duplicate detection). Nothing about ``corpus/hr/v1`` changes: its
case files stay byte-identical and every existing HR test stays green.

Each test below pins a real defect an annotator could introduce, not the
fixture apparatus: a Contracts case reaching for an HR category (or the
reverse), a task family borrowed from the wrong domain, a domain nobody
registered, and schema/registry drift between the two.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml

from adaptive_disclosure_gateway.corpus import CorpusLoadError, load_case, load_corpus
from adaptive_disclosure_gateway.corpus.models import (
    FROZEN_CATEGORIES_BY_DOMAIN,
    FROZEN_CONTRACTS_CATEGORIES,
    FROZEN_HR_CATEGORIES,
    TASK_FAMILIES_BY_DOMAIN,
    ContractsTaskFamily,
    CorpusCategory,
    TaskFamily,
)

REPO_ROOT = Path(__file__).parents[1]
HR_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"


def _minimal_contracts_case(sample_id: str = "contracts_schema_fixture_case") -> dict[str, Any]:
    """A minimal, valid Contracts case -- invented here for schema testing
    only, never corpus material (it lives under ``tests/``, like
    ``tests/contracts_fixture.py``, and carries no oracle anyone scores).
    """
    text = "Contracting party: Zenite Servicos Ltda\nDeadline: 2026-04-30\n"
    return {
        "input": {
            "sample_id": sample_id,
            "task_family": "deadline_tracking",
            "text": text,
            "task": "Report the contractual deadline for the delivery calendar.",
            "domain": "contracts",
            "purpose": "delivery_tracking",
            "policy_version": "contracts-v1",
        },
        "oracle": {
            "sample_id": sample_id,
            "expected_spans": [
                {
                    "category": "party_name",
                    "value": "Zenite Servicos Ltda",
                    "start": text.index("Zenite"),
                    "end": text.index("Zenite") + len("Zenite Servicos Ltda"),
                    "task_necessity": "not_required",
                    "expected_actions": ["remove", "pseudonymize"],
                },
                {
                    "category": "deadline",
                    "value": "2026-04-30",
                    "start": text.index("2026-04-30"),
                    "end": text.index("2026-04-30") + len("2026-04-30"),
                    "task_necessity": "required",
                    "expected_actions": ["preserve"],
                },
            ],
            "expected_block_request": False,
            "expected_answer": "The response reports the contractual deadline, 2026-04-30.",
            "answer_depends_on_categories": ["deadline"],
        },
    }


def _minimal_hr_case(sample_id: str = "hr_schema_fixture_case") -> dict[str, Any]:
    text = "Employee: Test Person\nDepartment: Engineering\n"
    return {
        "input": {
            "sample_id": sample_id,
            "task_family": "team_summary_without_salary",
            "text": text,
            "task": "Describe which department this employee belongs to.",
            "domain": "hr",
            "purpose": "team_summary",
            "policy_version": "hr-v1",
        },
        "oracle": {
            "sample_id": sample_id,
            "expected_spans": [
                {
                    "category": "department",
                    "value": "Engineering",
                    "start": text.index("Engineering"),
                    "end": text.index("Engineering") + len("Engineering"),
                    "task_necessity": "required",
                    "expected_actions": ["preserve"],
                }
            ],
            "expected_block_request": False,
            "expected_answer": "The response names the department 'Engineering'.",
            "answer_depends_on_categories": ["department"],
        },
    }


def _write_case(tmp_path: Path, case: dict[str, Any], file_name: str | None = None) -> Path:
    sample_id = case["input"]["sample_id"]
    path = tmp_path / (file_name or f"{sample_id}.yaml")
    path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    return path


def test_a_contracts_case_loads_with_contracts_categories_and_task_family(tmp_path):
    path = _write_case(tmp_path, _minimal_contracts_case())

    case = load_case(path)

    assert case.input.domain == "contracts"
    assert case.input.task_family is ContractsTaskFamily.DEADLINE_TRACKING
    assert {span.category for span in case.oracle.expected_spans} == {"party_name", "deadline"}


def test_a_contracts_case_declaring_an_hr_only_category_fails_to_load(tmp_path):
    case = _minimal_contracts_case()
    case["oracle"]["expected_spans"][0]["category"] = "salary"

    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError) as excinfo:
        load_case(path)
    assert "salary" in str(excinfo.value)
    assert "contracts" in str(excinfo.value)


def test_an_hr_case_declaring_a_contracts_only_category_fails_to_load(tmp_path):
    case = _minimal_hr_case()
    case["oracle"]["expected_spans"][0]["category"] = "penalty_amount"
    case["oracle"]["answer_depends_on_categories"] = ["penalty_amount"]

    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError) as excinfo:
        load_case(path)
    assert "penalty_amount" in str(excinfo.value)


def test_a_reconstruction_expectation_from_another_domain_fails_to_load(tmp_path):
    case = _minimal_contracts_case()
    case["oracle"]["reconstruction"] = [
        {"category": "employee_name", "expected_reconstructable": True}
    ]

    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError) as excinfo:
        load_case(path)
    assert "employee_name" in str(excinfo.value)


def test_an_answer_dependency_from_another_domain_fails_to_load(tmp_path):
    case = _minimal_contracts_case()
    case["oracle"]["answer_depends_on_categories"] = ["department"]

    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError) as excinfo:
        load_case(path)
    assert "department" in str(excinfo.value)


def test_a_case_declaring_a_task_family_from_another_domain_fails_to_load(tmp_path):
    case = _minimal_contracts_case()
    case["input"]["task_family"] = "authorized_salary_analysis"

    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError) as excinfo:
        load_case(path)
    assert "authorized_salary_analysis" in str(excinfo.value)


def test_an_unregistered_domain_fails_closed(tmp_path):
    case = _minimal_contracts_case()
    case["input"]["domain"] = "procurement"

    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError) as excinfo:
        load_case(path)
    assert "procurement" in str(excinfo.value)


def test_a_task_family_outside_every_registered_domain_fails_schema_validation(tmp_path):
    case = _minimal_contracts_case()
    case["input"]["task_family"] = "invented_family"

    path = _write_case(tmp_path, case)

    with pytest.raises(CorpusLoadError):
        load_case(path)


def test_corpus_category_literal_matches_the_per_domain_registries():
    """Drift guard: the schema-level ``Literal`` a case file is validated
    against must name exactly the categories the per-domain registries
    declare. Adding a domain category to a registry without widening the
    Literal would make every case using it fail schema validation for an
    unrelated-looking reason; widening the Literal without registering the
    category would let it through the schema and then past every domain
    check.
    """
    assert set(get_args(CorpusCategory)) == set(FROZEN_HR_CATEGORIES) | set(
        FROZEN_CONTRACTS_CATEGORIES
    )
    assert set(FROZEN_CATEGORIES_BY_DOMAIN) == {"hr", "contracts"}
    assert FROZEN_CATEGORIES_BY_DOMAIN["hr"] == FROZEN_HR_CATEGORIES
    assert FROZEN_CATEGORIES_BY_DOMAIN["contracts"] == FROZEN_CONTRACTS_CATEGORIES


def test_task_family_registry_matches_the_task_family_enums():
    assert set(TASK_FAMILIES_BY_DOMAIN) == set(FROZEN_CATEGORIES_BY_DOMAIN)
    assert TASK_FAMILIES_BY_DOMAIN["hr"] == tuple(family.value for family in TaskFamily)
    assert TASK_FAMILIES_BY_DOMAIN["contracts"] == tuple(
        family.value for family in ContractsTaskFamily
    )


def test_hr_and_contracts_task_family_values_never_collide():
    """The two enums are distinct types but their *values* share one schema
    field, so a value present in both would make the domain cross-check
    unable to tell which domain a case's family belongs to.
    """
    assert not set(TASK_FAMILIES_BY_DOMAIN["hr"]) & set(TASK_FAMILIES_BY_DOMAIN["contracts"])


def test_the_frozen_hr_corpus_still_loads_unchanged_under_the_extended_schema():
    """The extension is additive: every frozen HR v1 case must still load,
    with its HR task family and HR categories intact. A regression here
    means the per-domain schema broke the corpus it was required not to
    touch.
    """
    cases = load_corpus(HR_CORPUS_DIR)

    assert len(cases) == 13
    for case in cases:
        assert case.input.domain == "hr"
        assert isinstance(case.input.task_family, TaskFamily)
        for span in case.oracle.expected_spans:
            assert span.category in FROZEN_HR_CATEGORIES


def test_a_contracts_case_may_reuse_the_shared_cnpj_and_cpf_categories(tmp_path):
    """``cnpj``/``cpf`` are the two HR-era categories Issue #56 reused
    unchanged for Contracts rather than inventing a ``tax_id`` synonym. The
    per-domain check must not treat them as foreign to Contracts.
    """
    case = _minimal_contracts_case()
    text = (
        "Contracting party: Zenite Servicos Ltda\n"
        "CNPJ: 11.222.333/0001-44\n"
        "Representative: Vitoria Andrade Rocha\n"
        "CPF: 155.266.377-88\n"
        "Deadline: 2026-04-30\n"
    )
    case["input"]["text"] = text
    spans = copy.deepcopy(case["oracle"]["expected_spans"])
    for span in spans:
        span["start"] = text.index(span["value"])
        span["end"] = span["start"] + len(span["value"])
    for value, category in (("11.222.333/0001-44", "cnpj"), ("155.266.377-88", "cpf")):
        spans.append(
            {
                "category": category,
                "value": value,
                "start": text.index(value),
                "end": text.index(value) + len(value),
                "task_necessity": "not_required",
                "expected_actions": ["remove"],
            }
        )
    case["oracle"]["expected_spans"] = spans

    loaded = load_case(_write_case(tmp_path, case))

    assert {span.category for span in loaded.oracle.expected_spans} == {
        "party_name",
        "deadline",
        "cnpj",
        "cpf",
    }
