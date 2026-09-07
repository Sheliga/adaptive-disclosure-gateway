"""Shared enums and per-span oracle models for the HR pilot corpus (T09 /
issue #4, Phase A).

These are pure data models with no dependency on ``transformations``,
``detection``, ``policies`` or ``pipeline`` -- see
``tests/test_corpus_oracle_isolation.py`` for the architectural test that
pins the other half of the isolation invariant (no production module may
import anything from this package).
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


class ExpectedSpan(BaseModel):
    """One annotated sensitive information unit inside ``input.text``.

    ``expected_actions`` is the acceptable action set for this unit (a
    single-element list when only one action is acceptable) -- never a bare
    default, so a case cannot silently omit the annotation. ``helpful`` is
    the auxiliary annotation channel: it must never be read as if it were
    part of ``task_necessity``, which stays strictly binary.
    """

    model_config = ConfigDict(extra="forbid")

    category: HrCategory
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

    category: HrCategory
    expected_reconstructable: bool
