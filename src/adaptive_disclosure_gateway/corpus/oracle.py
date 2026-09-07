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

from adaptive_disclosure_gateway.corpus.models import ExpectedSpan, ReconstructionExpectation
from adaptive_disclosure_gateway.domain import DisclosureAction


class CaseOracle(BaseModel):
    """Ground truth used for scoring one corpus case.

    ``expected_block_request`` and ``expected_answer``/``reconstruction``
    are mutually constrained (see ``_check_block_consistency``): a case
    that must ``BLOCK_REQUEST`` never executes far enough to have an
    expected answer or a reconstruction expectation, and every blocked
    case must name at least one span whose acceptable action set is
    exactly ``BLOCK_REQUEST`` -- otherwise the annotation is internally
    inconsistent about *why* the case blocks.
    """

    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    expected_spans: list[ExpectedSpan] = Field(min_length=1)
    expected_block_request: bool
    expected_answer: str | None = None
    reconstruction: list[ReconstructionExpectation] = Field(default_factory=list)

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
        elif self.expected_answer is None:
            raise ValueError(
                "oracle.expected_answer is required when oracle.expected_block_request is false"
            )
        return self
