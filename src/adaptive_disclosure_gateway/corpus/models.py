"""Shared enums and per-span oracle models for the versioned evaluation
corpora (T09 / issue #4, Phase A; extended per-domain by T24 / issue #37).

These are pure data models with no dependency on ``transformations``,
``detection``, ``policies`` or ``pipeline`` -- see
``tests/test_corpus_oracle_isolation.py`` for the architectural test that
pins the other half of the isolation invariant (no production module may
import anything from this package).

Per-domain registries (T24 / issue #37)
---------------------------------------

Until T24 this module was HR-only: one ``HrCategory`` ``Literal`` and one
``TaskFamily`` enum, which is why a Contracts corpus could not be expressed
at all (``docs/contracts-policy-matrix.md``'s "Known limitations", item 4,
which flags this as the one expected, *non-semantic* T24 change).

The extension is the smallest one Contracts actually forces: the frozen
category tuple and the task-family enum become per-domain registries
(``FROZEN_CATEGORIES_BY_DOMAIN`` / ``TASK_FAMILIES_BY_DOMAIN``), and a case's
categories/task family are checked against its own ``input.domain`` in
``loader.py`` -- which is already where every cross-half consistency rule
lives. No generic multi-domain abstraction is introduced: adding a third
domain means adding two registry entries and one enum, nothing more.

``HrCategory`` and ``FROZEN_HR_CATEGORIES`` are kept exactly as they were
(``tests/test_corpus_coverage.py`` and the frozen ``corpus/hr/v1`` files
depend on them), and every ``corpus/hr/v1`` case file stays byte-identical.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_disclosure_gateway.domain import DisclosureAction

# The five HR categories frozen in the detector today (CLAUDE.md: "Somente
# as cinco categorias RH ja congeladas no detector"). A corpus case's
# expected spans/reconstruction expectations may only reference these --
# adding a sixth category is explicitly out of scope for T09 Phase A.
FROZEN_HR_CATEGORIES = (
    "employee_name",
    "cpf",
    "salary",
    "department",
    "medical_data",
)

HrCategory = Literal[
    "employee_name",
    "cpf",
    "salary",
    "department",
    "medical_data",
]

# The eight Contracts categories frozen by Issue #56 / PR #59
# (docs/contracts-policy-matrix.md). `cnpj` and `cpf` are the two HR-era
# categories reused unchanged rather than duplicated under a `tax_id`
# synonym; `obligation` and `confidential_clause` are deliberately NOT
# sensitive categories. This tuple is a corpus-schema mirror of that freeze,
# not a second source of truth for it -- `tests/test_contracts_domain.py`
# remains the executable half of the freeze itself, and
# `tests/test_corpus_contracts_coverage.py` pins that this tuple never drifts
# from the live detector/policy registries.
FROZEN_CONTRACTS_CATEGORIES = (
    "party_name",
    "representative_name",
    "cnpj",
    "cpf",
    "bank_account",
    "contract_value",
    "penalty_amount",
    "deadline",
)

# The schema-level category vocabulary: the union of every registered
# domain's frozen categories, stated once so a case file is validated
# against a closed set before the per-domain check in `loader.py` narrows it
# to the case's own domain. Both steps are needed: this Literal rejects an
# invented category outright, the loader rejects a real category borrowed
# from the wrong domain. `tests/test_corpus_contracts_schema.py` pins that
# this Literal never drifts from `FROZEN_CATEGORIES_BY_DOMAIN`.
CorpusCategory = Literal[
    "employee_name",
    "cpf",
    "salary",
    "department",
    "medical_data",
    "party_name",
    "representative_name",
    "cnpj",
    "bank_account",
    "contract_value",
    "penalty_amount",
    "deadline",
]

# Version of the case-file schema itself, distinct from any one corpus's own
# version directory (`hr/v1`, `contracts/v1`). v1 was the implicit, HR-only
# shape T09 froze; v2 is this module's per-domain registries plus the
# oracle's `obligation_relations` field (T24 / issue #37). The change is
# purely additive -- no v1 field changed meaning, no `corpus/hr/v1` file was
# edited, and every one of them still loads -- which is exactly why the
# frozen HR corpus keeps its own `hr/v1` version string unchanged.
CORPUS_SCHEMA_VERSION = "corpus-case-schema-v2"


class TaskNecessity(StrEnum):
    """The primary, binary task-necessity oracle (docs/experimental-design.md).

    Deliberately only two members: a case file that spells out anything
    else (e.g. a literal ``"helpful"`` value) fails schema validation instead
    of silently being accepted. ``HELPFUL`` is not a member here on purpose
    -- it may only exist as the separate, auxiliary ``ExpectedSpan.helpful``
    flag below, never mixed into this primary label.
    """

    REQUIRED = "required"
    NOT_REQUIRED = "not_required"


class TaskFamily(StrEnum):
    """The four HR task families T09/Issue #4 requires the pilot corpus to
    cover. Recorded as an explicit, validated field (rather than inferred
    from ``sample_id`` naming) so corpus-coverage checks are a real schema
    invariant, not a string-matching convention.
    """

    AUTHORIZED_SALARY_ANALYSIS = "authorized_salary_analysis"
    TEAM_SUMMARY_WITHOUT_SALARY = "team_summary_without_salary"
    DEPARTMENT_AGGREGATION_WITHOUT_IDENTITY = "department_aggregation_without_identity"
    MEDICAL_OR_PROHIBITED_BLOCK = "medical_or_prohibited_block"


class ContractsTaskFamily(StrEnum):
    """The six Contracts task families ``corpus/contracts/v1`` covers (T24 /
    issue #37), recorded as an explicit validated field for exactly the same
    reason ``TaskFamily`` is: corpus-coverage checks must be a schema
    invariant rather than a ``sample_id`` naming convention.

    Each family exists to make a specific treatment or governance difference
    observable, not merely to label a topic -- see
    ``corpus/contracts/v1/SCHEMA.md``'s "Task families" section:

    - ``contract_summary_without_identity`` -- party identity is not needed;
    - ``contract_value_audit`` -- the contract value figure is needed, under
      a ``purpose`` that may or may not authorize disclosing it exactly
      (the one governance dimension ``contracts-v1`` actually reads);
    - ``penalty_compliance_review`` -- the penalty regime is needed while
      the contract value is not, which is what the two separate monetary
      categories exist to make possible;
    - ``deadline_tracking`` -- an enforceable deadline is needed to the day;
    - ``payment_details_block`` -- a ``Bank account:`` line is present, so
      the request must block;
    - ``obligation_relation_preservation`` -- a role-referenced obligation
      whose "who owes what to whom" must survive the disclosure boundary.
    """

    CONTRACT_SUMMARY_WITHOUT_IDENTITY = "contract_summary_without_identity"
    CONTRACT_VALUE_AUDIT = "contract_value_audit"
    PENALTY_COMPLIANCE_REVIEW = "penalty_compliance_review"
    DEADLINE_TRACKING = "deadline_tracking"
    PAYMENT_DETAILS_BLOCK = "payment_details_block"
    OBLIGATION_RELATION_PRESERVATION = "obligation_relation_preservation"


# The schema-level task-family type: a case file's value must belong to one
# of the registered domains' enums. Which domain's enum is then checked
# against `input.domain` by `loader.py`; the two enums' values never overlap
# (pinned by tests/test_corpus_contracts_schema.py), so this union is
# unambiguous.
CorpusTaskFamily = TaskFamily | ContractsTaskFamily

# --- Per-domain registries (T24 / issue #37) --------------------------------
#
# The single place that says which categories and task families belong to
# which corpus domain. `loader.py` is the only consumer: it rejects a case
# whose annotations reach into another domain's vocabulary, and rejects an
# unregistered domain outright rather than silently accepting any category.
FROZEN_CATEGORIES_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "hr": FROZEN_HR_CATEGORIES,
    "contracts": FROZEN_CONTRACTS_CATEGORIES,
}

TASK_FAMILIES_BY_DOMAIN: dict[str, tuple[str, ...]] = {
    "hr": tuple(family.value for family in TaskFamily),
    "contracts": tuple(family.value for family in ContractsTaskFamily),
}

#: Every corpus domain the schema knows about. A case declaring anything
#: else fails closed at load time -- never "unknown domain, accept whatever
#: categories it names".
REGISTERED_CORPUS_DOMAINS: tuple[str, ...] = tuple(sorted(FROZEN_CATEGORIES_BY_DOMAIN))


class ExpectedSpan(BaseModel):
    """One annotated sensitive information unit inside ``input.text``.

    ``expected_actions`` is the acceptable action set for this unit (a
    single-element list when only one action is acceptable) -- never a bare
    default, so a case cannot silently omit the annotation. ``helpful`` is
    the auxiliary annotation channel: it must never be read as if it were
    part of ``task_necessity``, which stays strictly binary.
    """

    model_config = ConfigDict(extra="forbid")

    category: CorpusCategory
    value: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int
    task_necessity: TaskNecessity
    expected_actions: list[DisclosureAction] = Field(min_length=1)
    helpful: bool = False

    @model_validator(mode="after")
    def _check_offsets(self) -> ExpectedSpan:
        # Mirrors adaptive_disclosure_gateway.domain.SensitiveSpan's own
        # structural check. Text-relative validation (offsets in-bounds
        # against input.text, slice == value) is deliberately not done here
        # -- this model has no access to the case's text -- and instead
        # lives in tests/test_corpus_span_consistency.py, which reuses
        # transformations/span_validation.py rather than reimplementing it.
        if self.end <= self.start:
            raise ValueError(
                "ExpectedSpan.end must be greater than ExpectedSpan.start "
                f"(category={self.category!r})"
            )
        return self


class ReconstructionExpectation(BaseModel):
    """Whether a pseudonymized information unit of ``category`` is expected
    to be reconstructable back to its original value under the case's
    governance context.
    """

    model_config = ConfigDict(extra="forbid")

    category: CorpusCategory
    expected_reconstructable: bool


class ObligationRelation(BaseModel):
    """One "who owes what to whom" relation a Contracts case's document
    states, recorded in **role terms only** (T24 / issue #37).

    This is the relation half of the Contracts oracle, and it is
    ORACLE-ONLY: like every other field on ``CaseOracle``, it is never
    reachable from ``CorpusCaseInput``, never part of
    ``to_disclosure_request()``'s output, and never seen by the detector,
    the task analyzer, a treatment, policy or the provider -- pinned
    structurally and behaviorally by
    ``tests/test_corpus_obligation_relation.py``.

    **Why roles, not identities.** Issue #56 froze the relation semantics
    this field records against: the detector captures only its ``value``
    group, so the ROLE lives in the label (``Contracting party:``) and never
    inside a detected span, while the IDENTITY lives in the value and is
    pseudonymized. An obligation phrased by role therefore survives the
    disclosure boundary with its assignment intact and needs no relation
    model at runtime (``docs/contracts-policy-matrix.md``, "Relation
    semantics"). Recording the relation by role is what makes it checkable
    against a *transformed* payload at all -- an identity-phrased relation
    would only ever be checkable against B0's untransformed output.

    Writing a party's actual name into any field here would put a raw
    sensitive value in the oracle's relation annotation, where a
    payload-level relation check would then look for it; that is an
    annotation defect, and
    ``tests/test_corpus_obligation_relation.py::test_no_obligation_relation_field_contains_a_sensitive_span_value``
    fails the build if it ever happens.

    ``depends_on_categories`` names the categories the obligation's content
    depends on (the amount it is owed in, the deadline it falls due on), so
    a scorer or reviewer can tell which transformed values the relation's
    *content* -- as opposed to its assignment -- rests on.
    """

    model_config = ConfigDict(extra="forbid")

    #: The role that owes the obligation, exactly as it appears as a
    #: detector label in the case's ``input.text`` (e.g. ``Contracting party``).
    obligor_role: str = Field(min_length=1)
    #: The role the obligation is owed to (e.g. ``Contracted party``).
    obligee_role: str = Field(min_length=1)
    #: What is owed, in role/reference terms and never restating a literal
    #: amount or date (e.g. ``must pay the contract value by the deadline``).
    obligation: str = Field(min_length=1)
    #: Every category the obligation's content depends on.
    depends_on_categories: list[CorpusCategory] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_roles_are_distinct(self) -> ObligationRelation:
        if self.obligor_role == self.obligee_role:
            raise ValueError(
                "ObligationRelation.obligor_role and obligee_role must name two "
                "different roles -- an obligation owed by a role to itself "
                "carries no assignment for a treatment to preserve or lose"
            )
        return self
