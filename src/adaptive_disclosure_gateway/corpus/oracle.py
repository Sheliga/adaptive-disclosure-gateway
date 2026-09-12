"""The scoring-only half of a corpus case (T09 / issue #4, Phase A).

``CaseOracle`` never has a method that builds a ``DisclosureRequest``, never
imports anything from ``transformations``, ``detection``, ``policies`` or
``pipeline``, and no production module may import this module or
``CaseOracle`` -- see ``tests/test_corpus_oracle_isolation.py``, which pins
all of that by AST inspection. Ground truth is an evaluation oracle only
(CLAUDE.md's no-leak invariant and docs/experimental-design.md): a
treatment must never receive it as privileged input.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaptive_disclosure_gateway.corpus.models import (
    CorpusCategory,
    ExpectedSpan,
    ObligationRelation,
    ReconstructionExpectation,
)
from adaptive_disclosure_gateway.domain import DisclosureAction


class CaseOracle(BaseModel):
    """Ground truth used for scoring one corpus case.

    ``expected_block_request`` and ``expected_answer``/``reconstruction``/
    ``answer_depends_on_categories`` are mutually constrained (see
    ``_check_block_consistency``): a case that must ``BLOCK_REQUEST`` never
    executes far enough to have an expected answer, a reconstruction
    expectation, or an answer dependency list, and every blocked case must
    name at least one span whose acceptable action set is exactly
    ``BLOCK_REQUEST`` -- otherwise the annotation is internally inconsistent
    about *why* the case blocks.

    ``answer_depends_on_categories`` names every category ``expected_answer``
    actually depends on. It exists so a span can never be annotated
    ``task_necessity: required`` without the case's own answer oracle
    depending on it -- see ``tests/test_corpus_task_necessity_coherence.py``,
    which pins that the set of categories with at least one `required` span
    equals this field exactly, for every non-blocked case. This is the
    structural check that would have caught PR #31 review round 2's
    `hr_team_summary_001/002/003` defect (`employee_name` marked `required`
    even though those cases' `expected_answer` only ever names the
    department).
    """

    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    expected_spans: list[ExpectedSpan] = Field(min_length=1)
    expected_block_request: bool
    expected_answer: str | None = None
    reconstruction: list[ReconstructionExpectation] = Field(default_factory=list)
    answer_depends_on_categories: list[CorpusCategory] | None = None
    # T24 / issue #37: the relation half of the oracle -- "who owes what to
    # whom", in role terms only (see ObligationRelation's own docstring).
    # Defaults to empty, so every frozen corpus/hr/v1 case file stays valid
    # byte-for-byte without stating it. Must be empty for a blocked case: a
    # blocked request discloses nothing at all, so no relation could have
    # survived or been lost through a payload that was never produced.
    obligation_relations: list[ObligationRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_block_consistency(self) -> CaseOracle:
        if self.expected_block_request:
            if self.expected_answer is not None:
                raise ValueError(
                    "oracle.expected_answer must be absent when "
                    "oracle.expected_block_request is true -- a blocked "
                    "request never produces an answer to score"
                )
            if self.reconstruction:
                raise ValueError(
                    "oracle.reconstruction must be empty when "
                    "oracle.expected_block_request is true -- a blocked "
                    "request never reaches reconstruction"
                )
            if self.answer_depends_on_categories is not None:
                raise ValueError(
                    "oracle.answer_depends_on_categories must be absent when "
                    "oracle.expected_block_request is true -- a blocked "
                    "request never produces an answer for anything to "
                    "depend on"
                )
            if self.obligation_relations:
                raise ValueError(
                    "oracle.obligation_relations must be empty when "
                    "oracle.expected_block_request is true -- a blocked "
                    "request produces no payload for a relation to survive "
                    "in or be lost from"
                )
            if not any(
                DisclosureAction.BLOCK_REQUEST in span.expected_actions
                for span in self.expected_spans
            ):
                raise ValueError(
                    "oracle.expected_block_request is true but no "
                    "expected_spans entry names BLOCK_REQUEST as an "
                    "acceptable action -- annotate which category forces "
                    "the block"
                )
        else:
            if self.expected_answer is None:
                raise ValueError(
                    "oracle.expected_answer is required when oracle.expected_block_request is false"
                )
            if self.answer_depends_on_categories is None:
                raise ValueError(
                    "oracle.answer_depends_on_categories is required when "
                    "oracle.expected_block_request is false -- name every "
                    "category the expected_answer actually depends on"
                )
        return self
