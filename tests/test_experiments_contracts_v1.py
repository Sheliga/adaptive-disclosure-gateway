"""The Contracts v1 corpus actually executes B0-B4, and the scientific
invariants hold on a second domain (T24 / issue #37).

The Contracts counterpart of ``tests/test_experiments_core.py``'s runner
invariants. Its purpose is to prove that a second-domain corpus runs through
the *unmodified* pipeline -- no treatment, policy, detector or metric change
was needed to execute it -- and that the disclosure-surface invariants
CLAUDE.md states hold for Contracts data, not only for HR data.

Everything here runs against ``FakeProvider``. Per T22 / Issue #30, which is
open and parallel, nothing in this file supports any claim about real LLM
utility, real token counts, real cost or real provider behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_disclosure_gateway.corpus import load_corpus
from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.experiments.case_result import to_safe_dict
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.run_identity import PILOT_DEVELOPMENT
from adaptive_disclosure_gateway.experiments.runner import ALL_TREATMENTS, run_pilot
from adaptive_disclosure_gateway.policies import PolicyRepository

REPO_ROOT = Path(__file__).parents[1]
CORPUS_DIR = REPO_ROOT / "corpus" / "contracts" / "v1" / "cases"
POLICY_DIR = REPO_ROOT / "configs" / "policies"
CORPUS_VERSION = "contracts/v1"

# Treatments that apply disclosure control at all. B0 -- Direct transmits the
# document unchanged by definition, so it is excluded from every
# "no raw value in the payload" assertion below -- that difference is the
# B0->B1 comparison the experiment exists to measure, not a defect.
CONTROLLED_TREATMENTS = tuple(t for t in ALL_TREATMENTS if t is not Treatment.DIRECT)


def _policy_repo() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def _cases():
    cases = load_corpus(CORPUS_DIR)
    assert cases, "expected Contracts corpus cases"
    return cases


def _case(sample_id: str):
    return {case.input.sample_id: case for case in _cases()}[sample_id]


def _execute(case_input, treatment):
    return execute_case(
        case_input=case_input,
        treatment=treatment,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
        policy_repository=_policy_repo(),
    )


# --- the corpus executes end to end -----------------------------------------


def test_every_contracts_case_runs_through_every_treatment_and_produces_a_result():
    cases = _cases()
    assert len(cases) == 12

    for treatment in Treatment:
        for case in cases:
            execution = _execute(case.input, treatment)
            assert execution.identity.case_id == case.input.sample_id
            assert execution.identity.treatment_code == treatment.value
            assert execution.execution.disclosure_result.status in ("allowed", "blocked")


def test_every_contracts_result_is_classified_pilot_development():
    """The run classification was fixed in advance, before this branch existed
    and before any B0-B4 Contracts result was produced or inspected (see
    ``corpus/contracts/v1/README.md``). ``pilot_development`` means this
    corpus is NOT confirmatory evidence. Because its results have since been
    inspected, this corpus is permanently ineligible for
    ``held_out_confirmatory`` (post-pilot-v1 Section 1): a future confirmatory
    Contracts round requires a newly authored, independently frozen corpus.
    """
    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
        experiment_run_id="contracts-classification-probe",
        # Issue #87 / M3: corpus/contracts/v1 is a frozen, legacy corpus
        # with no opted-in CaseOracle.utility_references -- must be scored
        # under the historical post-pilot-v3 protocol explicitly.
        protocol_id="post-pilot-v3",
    )

    assert results
    for treatment_results in results.values():
        assert treatment_results
        for result in treatment_results:
            assert result.identity.run_classification == "pilot_development"
            assert result.identity.corpus_version == CORPUS_VERSION


def test_every_treatment_receives_the_same_detected_input_for_the_same_case():
    """B0-B4 must differ only in what they *do* with a case, never in what
    they are given. The detector runs before any treatment, on the same
    ``request.text``, so the spans it produces must be byte-identical across
    treatments -- a difference here would mean the input itself varied and
    every adjacent comparison would be confounded.
    """
    for case in _cases():
        per_treatment = {
            treatment: tuple(
                (span.category, span.start, span.end)
                for span in _execute(case.input, treatment).detected_text_spans
            )
            for treatment in Treatment
        }
        distinct = set(per_treatment.values())
        assert len(distinct) == 1, (
            f"{case.input.sample_id}: treatments saw different detected input: {per_treatment}"
        )


def test_every_case_annotating_a_bank_account_blocks_under_every_controlled_treatment():
    for case in _cases():
        if not any(span.category == "bank_account" for span in case.oracle.expected_spans):
            continue
        for treatment in CONTROLLED_TREATMENTS:
            execution = _execute(case.input, treatment)
            assert execution.execution.disclosure_result.status == "blocked", (
                f"{case.input.sample_id}/{treatment.value} did not block on a bank account"
            )
            assert execution.execution.disclosure_result.external_payload == ""


# --- disclosure-surface invariants on a second domain ------------------------


@pytest.mark.parametrize("treatment", CONTROLLED_TREATMENTS, ids=lambda t: t.value)
def test_no_raw_contracts_value_reaches_the_payload_task_audit_or_serialized_result(treatment):
    """The no-leak invariant checked over the whole disclosure surface, not
    just the payload: the external payload, the task text actually sent, the
    audit record and the runner's complete serialized result.

    The one deliberate exception is a PRESERVE-d value: ``contracts-v1``
    preserves ``deadline`` outright and preserves ``contract_value`` /
    ``penalty_amount`` under their authorized purposes, so those originals are
    *supposed* to appear. The check below therefore asserts on the categories
    that must never appear in raw form under any Contracts policy -- party and
    representative names, CNPJ, CPF and bank account -- which is the set whose
    disclosure would be a real defect rather than a governed decision.
    """
    never_raw = {"party_name", "representative_name", "cnpj", "cpf", "bank_account"}

    for case in _cases():
        values = [span.value for span in case.oracle.expected_spans if span.category in never_raw]
        if not values:
            continue
        execution = _execute(case.input, treatment)
        result = execution.execution.disclosure_result
        surfaces = {
            "external_payload": result.external_payload,
            "audit": repr(execution.execution.audit),
        }
        if execution.provider_metrics is not None:
            surfaces["provider_metrics"] = repr(execution.provider_metrics)

        for name, surface in surfaces.items():
            for value in values:
                assert value not in surface, (
                    f"{case.input.sample_id}/{treatment.value}: a raw value of a "
                    f"never-raw category reached {name}"
                )


def test_the_full_serialized_runner_result_carries_no_never_raw_contracts_value():
    """The same invariant one level further out: whatever a later analysis,
    UI or artifact file consumes is ``to_safe_dict``'s output, so that is the
    surface an adversarial check must actually scan.
    """
    never_raw = {"party_name", "representative_name", "cnpj", "cpf", "bank_account"}
    results = run_pilot(
        corpus_dir=CORPUS_DIR,
        policy_dir=POLICY_DIR,
        corpus_version=CORPUS_VERSION,
        run_classification=PILOT_DEVELOPMENT,
        treatments=CONTROLLED_TREATMENTS,
        experiment_run_id="contracts-no-leak-probe",
        protocol_id="post-pilot-v3",
    )
    cases_by_id = {case.input.sample_id: case for case in _cases()}

    for treatment_results in results.values():
        for result in treatment_results:
            case = cases_by_id[result.identity.case_id]
            serialized = repr(to_safe_dict(result))
            for span in case.oracle.expected_spans:
                if span.category in never_raw:
                    assert span.value not in serialized, (
                        f"{result.identity.case_id}/{result.identity.treatment_code}: "
                        f"a raw {span.category} value reached the serialized result"
                    )


# --- relation preservation ---------------------------------------------------

RELATION_CASE = "contracts_obligation_relation_001"
REVERSED_RELATION_CASE = "contracts_obligation_relation_002"


def _role_values(payload: str, role: str) -> list[str]:
    return [
        line[len(role) + 1 :].strip() for line in payload.split("\n") if line.startswith(f"{role}:")
    ]


@pytest.mark.parametrize("sample_id", [RELATION_CASE, REVERSED_RELATION_CASE])
@pytest.mark.parametrize(
    "treatment",
    [Treatment.REVERSIBLE_PSEUDONYMIZATION, Treatment.TASK_AWARE, Treatment.POLICY_GOVERNED],
    ids=lambda t: t.value,
)
def test_who_owes_what_to_whom_survives_pseudonymizing_treatments(sample_id, treatment):
    """Corpus/oracle validation, deliberately NOT a new comparison metric:
    ``post-pilot-v1`` freezes the metric set, and a relation check belongs to
    validating that this corpus measures what it claims to, not to the
    protocol's metrics.

    What is asserted, per ``docs/contracts-policy-matrix.md``'s relation
    semantics: the obligation sentence reaches the payload untransformed (it
    carries no detected span), both roles still appear as labels, and the two
    roles carry *distinct, non-empty* references -- so the payload alone still
    says which role owes the other, with neither identity disclosed.
    """
    case = _case(sample_id)
    relation = case.oracle.obligation_relations[0]
    execution = _execute(case.input, treatment)
    payload = execution.execution.disclosure_result.external_payload

    assert execution.execution.disclosure_result.status == "allowed"
    source_lines = [line for line in case.input.text.split("\n") if line.startswith("Obligation:")]
    obligation_lines = [line for line in payload.split("\n") if line.startswith("Obligation:")]
    assert obligation_lines == source_lines, (
        "the obligation sentence must reach the payload untransformed -- it carries "
        "no detected span of its own, so any difference means something transformed it"
    )
    assert relation.obligor_role in obligation_lines[0]
    assert relation.obligee_role in obligation_lines[0]

    obligor_values = _role_values(payload, relation.obligor_role)
    obligee_values = _role_values(payload, relation.obligee_role)
    assert obligor_values and obligee_values, "a role label vanished from the payload"
    assert all(value for value in obligor_values + obligee_values), (
        "a role survived with an empty reference -- the relation no longer says who"
    )
    assert set(obligor_values).isdisjoint(obligee_values), (
        "the two roles resolved to the same reference, so the parties collapsed into one"
    )

    for span in case.oracle.expected_spans:
        if span.category == "party_name":
            assert span.value not in payload


@pytest.mark.parametrize("sample_id", [RELATION_CASE, REVERSED_RELATION_CASE])
def test_static_sanitization_keeps_the_roles_but_loses_which_company_is_which(sample_id):
    """The B1->B2 gap this domain makes unusually visible, pinned as a
    measured property rather than left as prose: B1 -- Static Sanitization has
    no vault, so both party names are REMOVE-d. The ROLE relation still reads
    intact -- that is the role-in-label split doing its work -- but the two
    parties become indistinguishable from each other, so cross-document
    identity is gone.
    """
    case = _case(sample_id)
    relation = case.oracle.obligation_relations[0]
    execution = _execute(case.input, Treatment.STATIC_SANITIZATION)
    payload = execution.execution.disclosure_result.external_payload

    source_lines = [line for line in case.input.text.split("\n") if line.startswith("Obligation:")]
    obligation_lines = [line for line in payload.split("\n") if line.startswith("Obligation:")]
    assert obligation_lines == source_lines
    assert relation.obligor_role in obligation_lines[0]
    assert relation.obligee_role in obligation_lines[0]

    obligor_values = _role_values(payload, relation.obligor_role)
    obligee_values = _role_values(payload, relation.obligee_role)
    assert obligor_values and obligee_values
    assert set(obligor_values) == {""}, (
        "B1 removes a party name outright, leaving its role label with no "
        f"reference at all -- got {obligor_values}"
    )
    assert set(obligor_values) == set(obligee_values), (
        "B1 is expected to leave both parties with the same, identity-free "
        "placeholder -- if that changed, this documented B1->B2 gap changed with it"
    )


@pytest.mark.parametrize("sample_id", [RELATION_CASE, REVERSED_RELATION_CASE])
def test_authorized_reconstruction_restores_both_parties_for_the_relation_cases(sample_id):
    """The other half of the B1->B2 delta: the pseudonymized payload is
    reversible for an authorized requester, so utility is reached by
    pseudonymize + reconstruction rather than by disclosure.
    """
    case = _case(sample_id)
    execution = _execute(case.input, Treatment.REVERSIBLE_PSEUDONYMIZATION)
    reconstructed = execution.payload_echo_reconstructed_text

    assert reconstructed is not None, "expected the payload-echo reconstruction round trip"
    for span in case.oracle.expected_spans:
        if span.category == "party_name":
            assert span.value in reconstructed, (
                f"{span.category} did not reconstruct back to its original value"
            )


def test_the_same_company_would_receive_the_same_reference_within_one_case():
    """Pseudonym stability is what carries "the same company owes this
    obligation" across a document. The corpus's own cases each name a party
    once, so this asserts the underlying property directly on a document that
    repeats a party -- built here, not added to the frozen corpus, because a
    duplicated-party case would add no oracle the corpus does not already
    have.
    """
    case = _case(RELATION_CASE)
    repeated_text = case.input.text + case.input.text
    repeated_input = case.input.model_copy(update={"text": repeated_text})

    execution = _execute(repeated_input, Treatment.REVERSIBLE_PSEUDONYMIZATION)
    payload = execution.execution.disclosure_result.external_payload

    obligor_values = _role_values(payload, "Contracting party")
    assert len(obligor_values) == 2, "expected the repeated party block to reach the payload"
    assert obligor_values[0] == obligor_values[1], (
        "the same original party resolved to two different pseudonyms within one scope"
    )
