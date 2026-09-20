"""The Contracts oracle's relation half: "who owes what to whom" (T24 /
issue #37).

``CaseOracle.obligation_relations`` is the only genuinely new oracle field
this ticket adds, and it is the one most likely to be misused, in two
opposite directions:

1. **As a runtime input.** A relation annotation is ground truth. If it ever
   reached the detector, the task analyzer, a treatment, policy or the
   provider, the experiment would be measuring a pipeline that was told the
   answer. The isolation tests below extend
   ``tests/test_corpus_oracle_isolation.py``'s AST approach to this field
   specifically, and add a behavioral proof: a marker planted in a relation
   must not surface anywhere in a full runner execution's serialized output.

2. **As a place to write an identity.** The relation is recorded in ROLE
   terms because that is the only form that survives the disclosure boundary
   (``docs/contracts-policy-matrix.md``, "Relation semantics": the role lives
   in the detector's label, the identity lives in the detected value). A
   party's actual name written into ``obligor_role``/``obligee_role``/
   ``obligation`` would put a raw sensitive value into the oracle and make a
   payload-level relation check look for a string that must never be there.
   ``test_no_obligation_relation_field_contains_a_sensitive_span_value``
   fails the build if that ever happens.
"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from adaptive_disclosure_gateway.corpus import CorpusLoadError, load_case, load_corpus
from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.models import ObligationRelation
from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.experiments.case_result import to_safe_dict
from adaptive_disclosure_gateway.experiments.runner import run_case_for_treatment
from adaptive_disclosure_gateway.policies import PolicyRepository

REPO_ROOT = Path(__file__).parents[1]
CORPUS_DIR = REPO_ROOT / "corpus" / "contracts" / "v1" / "cases"
POLICY_DIR = REPO_ROOT / "configs" / "policies"
SRC_ROOT = REPO_ROOT / "src" / "adaptive_disclosure_gateway"

PRODUCTION_DIRS = (
    SRC_ROOT / "transformations",
    SRC_ROOT / "detection",
    SRC_ROOT / "task_analysis",
    SRC_ROOT / "application",
)
PRODUCTION_FILES = (SRC_ROOT / "policies.py", SRC_ROOT / "pipeline.py")

# The experiments modules that sit on the "everything a treatment may see"
# side of the execution boundary (experiments/execution.py's own docstring).
EXECUTION_BOUNDARY_FILES = (
    SRC_ROOT / "experiments" / "execution.py",
    SRC_ROOT / "experiments" / "treatments.py",
    SRC_ROOT / "experiments" / "provider_instrumentation.py",
    SRC_ROOT / "experiments" / "corpus_source.py",
)

_RELATION_IDENTIFIERS = {"ObligationRelation", "obligation_relations"}


def _cases():
    cases = load_corpus(CORPUS_DIR)
    assert cases, "expected at least one Contracts corpus case"
    return cases


def _cases_with_relations():
    cases = [case for case in _cases() if case.oracle.obligation_relations]
    assert cases, "expected at least one Contracts case to state an obligation relation"
    return cases


# --- the relation is grounded in its own case's document ---------------------


def test_every_obligation_relation_role_is_a_labeled_line_in_its_own_case_text():
    """A role is only preserved because it is a detector *label*. A relation
    naming a role the document never uses as a label is not preserved by
    anything -- it is an assertion about a document that does not exist.
    """
    failures = []
    for case in _cases_with_relations():
        for relation in case.oracle.obligation_relations:
            for role in (relation.obligor_role, relation.obligee_role):
                if f"{role}:" not in case.input.text:
                    failures.append(f"{case.input.sample_id}: {role!r}")

    assert not failures, (
        "obligation relation names a role that is not a labeled line in the "
        f"case's own input.text: {failures}"
    )


def test_every_obligation_relation_states_its_obligation_by_role_in_the_document():
    """The obligation sentence itself must be present in the document, phrased
    by role -- the only shape ``docs/contracts-policy-matrix.md`` proves
    relation preservation for. Both roles must appear inside the document's
    own ``Obligation:`` line.
    """
    failures = []
    for case in _cases_with_relations():
        obligation_lines = [
            line for line in case.input.text.split("\n") if line.startswith("Obligation:")
        ]
        if not obligation_lines:
            failures.append(f"{case.input.sample_id}: no Obligation: line")
            continue
        joined = "\n".join(obligation_lines)
        for relation in case.oracle.obligation_relations:
            if relation.obligor_role not in joined or relation.obligee_role not in joined:
                failures.append(f"{case.input.sample_id}: roles absent from the Obligation: line")

    assert not failures, (
        "an obligation relation is not stated by role in its own document -- "
        "relation preservation is proven only for the role-referenced shape: "
        f"{failures}"
    )


def test_no_obligation_relation_field_contains_a_sensitive_span_value():
    """The adversarial half: if an annotator writes a party's real name into
    the relation, the relation stops being checkable against a transformed
    payload (the name is exactly what every treatment above B0 removes or
    pseudonymizes) and the oracle starts carrying a raw sensitive value.
    """
    failures = []
    for case in _cases_with_relations():
        sensitive_values = {span.value for span in case.oracle.expected_spans}
        for relation in case.oracle.obligation_relations:
            fields = (relation.obligor_role, relation.obligee_role, relation.obligation)
            for value in sensitive_values:
                if any(value in field for field in fields):
                    failures.append(f"{case.input.sample_id}: a span value appears in a relation")

    assert not failures, (
        "an obligation relation field contains a sensitive span value -- the "
        f"relation must be recorded in role terms only: {failures}"
    )


def test_no_obligation_relation_restates_a_literal_amount_or_date():
    """The obligation content refers to the amount and the deadline by name
    ("the contract value", "the deadline"), never by figure. A literal figure
    there would be an oracle-side copy of a value the payload is supposed to
    have transformed.
    """
    literal = re.compile(r"R\$\s?\d|\d{4}-\d{2}-\d{2}")
    failures = [
        f"{case.input.sample_id}: {relation.obligation!r}"
        for case in _cases_with_relations()
        for relation in case.oracle.obligation_relations
        if literal.search(relation.obligation)
    ]

    assert not failures, f"obligation content restates a literal amount or date: {failures}"


def test_every_obligation_relation_dependency_is_annotated_in_its_own_case():
    failures = []
    for case in _cases_with_relations():
        annotated = {span.category for span in case.oracle.expected_spans}
        for relation in case.oracle.obligation_relations:
            missing = set(relation.depends_on_categories) - annotated
            if missing:
                failures.append(f"{case.input.sample_id}: {sorted(missing)}")

    assert not failures, (
        "an obligation relation depends on a category the case never annotates, "
        f"so nothing measures whether that dependency survived: {failures}"
    )


def test_the_corpus_states_obligations_in_both_directions():
    """A treatment that always bound the first-named party to the obligor role
    would satisfy a corpus whose obligations all run the same way. At least
    one case must run each direction.
    """
    directions = {
        (relation.obligor_role, relation.obligee_role)
        for case in _cases_with_relations()
        for relation in case.oracle.obligation_relations
    }

    assert ("Contracting party", "Contracted party") in directions
    assert ("Contracted party", "Contracting party") in directions


# --- schema-level fail-closed behavior ---------------------------------------


def _relation_case(sample_id: str = "contracts_relation_fixture_case") -> dict[str, Any]:
    text = (
        "Contracting party: Zenite Servicos Ltda\n"
        "Contracted party: Boreal Sistemas SA\n"
        "Obligation: Contracting party must pay Contracted party the contract value "
        "by the deadline\n"
        "Contract value: R$ 300000.00\n"
        "Deadline: 2026-04-30\n"
    )

    def span(category, value, necessity, actions):
        start = text.index(value)
        return {
            "category": category,
            "value": value,
            "start": start,
            "end": start + len(value),
            "task_necessity": necessity,
            "expected_actions": actions,
        }

    return {
        "input": {
            "sample_id": sample_id,
            "task_family": "obligation_relation_preservation",
            "text": text,
            "task": "State which contracting party owes payment to which contracted party.",
            "domain": "contracts",
            "purpose": "contract_summary",
            "policy_version": "contracts-v1",
        },
        "oracle": {
            "sample_id": sample_id,
            "expected_spans": [
                span("party_name", "Zenite Servicos Ltda", "required", ["pseudonymize"]),
                span("party_name", "Boreal Sistemas SA", "required", ["pseudonymize"]),
                span("contract_value", "R$ 300000.00", "not_required", ["remove", "generalize"]),
                span("deadline", "2026-04-30", "not_required", ["remove", "generalize"]),
            ],
            "expected_block_request": False,
            "expected_answer": "The response states which role owes payment to which other role.",
            "answer_depends_on_categories": ["party_name"],
            "obligation_relations": [
                {
                    "obligor_role": "Contracting party",
                    "obligee_role": "Contracted party",
                    "obligation": "must pay the contract value by the deadline",
                    "depends_on_categories": ["contract_value", "deadline"],
                }
            ],
        },
    }


def _write_case(tmp_path: Path, case: dict[str, Any]) -> Path:
    path = tmp_path / f"{case['input']['sample_id']}.yaml"
    path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    return path


def test_the_relation_fixture_itself_loads(tmp_path):
    loaded = load_case(_write_case(tmp_path, _relation_case()))

    assert len(loaded.oracle.obligation_relations) == 1
    assert loaded.oracle.obligation_relations[0].obligor_role == "Contracting party"


def test_a_relation_owed_by_a_role_to_itself_fails_schema_validation(tmp_path):
    case = _relation_case()
    case["oracle"]["obligation_relations"][0]["obligee_role"] = "Contracting party"

    with pytest.raises(CorpusLoadError):
        load_case(_write_case(tmp_path, case))


def test_a_relation_with_no_dependency_categories_fails_schema_validation(tmp_path):
    case = _relation_case()
    case["oracle"]["obligation_relations"][0]["depends_on_categories"] = []

    with pytest.raises(CorpusLoadError):
        load_case(_write_case(tmp_path, case))


def test_a_blocked_case_may_not_declare_an_obligation_relation(tmp_path):
    case = copy.deepcopy(_relation_case())
    case["oracle"]["expected_block_request"] = True
    del case["oracle"]["expected_answer"]
    del case["oracle"]["answer_depends_on_categories"]
    case["oracle"]["expected_spans"][0]["expected_actions"] = ["block_request"]

    with pytest.raises(CorpusLoadError):
        load_case(_write_case(tmp_path, case))


def test_an_unknown_field_on_a_relation_fails_schema_validation(tmp_path):
    case = _relation_case()
    case["oracle"]["obligation_relations"][0]["obligor_company"] = "Zenite Servicos Ltda"

    with pytest.raises(CorpusLoadError):
        load_case(_write_case(tmp_path, case))


# --- isolation: the relation is oracle-only ----------------------------------


def test_corpus_case_input_declares_no_relation_field():
    """Structural, not documentary: ``CorpusCaseInput`` is the entire set of
    fields a treatment may see. A relation field appearing here is the only
    way the relation could ever reach ``to_disclosure_request()``.
    """
    for field_name in CorpusCaseInput.model_fields:
        assert "obligation" not in field_name.lower()
        assert "relation" not in field_name.lower()


def test_a_disclosure_request_built_from_a_contracts_case_carries_no_relation():
    case = _cases_with_relations()[0]

    request = case.input.to_disclosure_request()

    assert set(type(request).model_fields) == {"text", "task", "context"}
    for relation in case.oracle.obligation_relations:
        assert relation.obligation not in request.task
        assert relation.obligation not in request.text


def _identifiers(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_no_production_or_execution_boundary_module_references_the_relation():
    files: list[Path] = []
    for directory in PRODUCTION_DIRS:
        files.extend(sorted(directory.glob("*.py")))
    files.extend(PRODUCTION_FILES)
    files.extend(EXECUTION_BOUNDARY_FILES)
    assert files, "expected source files to check"
    for path in EXECUTION_BOUNDARY_FILES:
        assert path in files and path.exists(), f"{path} must exist to be checked"

    violations = [
        f"{path.name} references {name!r}"
        for path in files
        for name in _identifiers(path) & _RELATION_IDENTIFIERS
    ]

    assert not violations, "\n".join(violations)


def test_a_marker_planted_in_an_obligation_relation_never_reaches_a_runner_result():
    """Behavioral proof, not just structural: run a real Contracts case
    through the real runner with a distinctive marker planted in its oracle's
    relation, and assert the marker appears nowhere in the serialized result
    -- which covers the payload, the audit record, telemetry-derived metadata
    and every identity/score field the runner persists.
    """
    case = _cases_with_relations()[0]
    marker = "ZzRelationMarkerNeverInInputZz"
    assert marker not in case.input.text
    assert marker not in case.input.task

    poisoned_relation = ObligationRelation(
        obligor_role=marker,
        obligee_role=f"{marker}-obligee",
        obligation=f"{marker} must pay {marker}-obligee",
        depends_on_categories=["contract_value"],
    )
    poisoned_case = case._replace(
        oracle=case.oracle.model_copy(update={"obligation_relations": [poisoned_relation]})
    )
    assert poisoned_case.oracle.obligation_relations[0].obligor_role == marker

    policy_repository = PolicyRepository.from_directory(POLICY_DIR)
    for treatment in Treatment:
        result = run_case_for_treatment(
            poisoned_case,
            treatment,
            corpus_version="contracts/v1",
            run_classification="pilot_development",
            policy_repository=policy_repository,
            experiment_run_id="relation-isolation-probe",
        )

        serialized = repr(to_safe_dict(result))
        assert marker not in serialized, (
            f"{treatment.value}: an oracle relation marker reached the runner's serialized result"
        )
        assert marker not in result.case_execution.execution.disclosure_result.external_payload
        assert marker not in repr(result.case_execution.execution.audit)
