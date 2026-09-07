"""HR pilot corpus schema and loader (T09 / issue #4, Phase A).

Public surface:

- ``CorpusCaseInput`` -- everything a treatment may legitimately see.
- ``CaseOracle`` -- ground truth used for scoring only, never privileged
  treatment input.
- ``ExpectedSpan`` / ``ReconstructionExpectation`` / ``TaskNecessity`` /
  ``TaskFamily`` -- the oracle's building blocks.
- ``CorpusCase`` / ``load_case`` / ``load_corpus`` / ``CorpusLoadError`` --
  loading one or all versioned case files from ``corpus/hr/v1/cases/``.

See ``corpus/hr/v1/SCHEMA.md`` (repository root) for the frozen case-file
schema in prose, and ``corpus/hr/v1/README.md`` for what the corpus covers
and its freeze/versioning rule.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import (
    CorpusCase,
    CorpusLoadError,
    load_case,
    load_corpus,
)
from adaptive_disclosure_gateway.corpus.models import (
    FROZEN_HR_CATEGORIES,
    ExpectedSpan,
    ReconstructionExpectation,
    TaskFamily,
    TaskNecessity,
)
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle

__all__ = [
    "FROZEN_HR_CATEGORIES",
    "CaseOracle",
    "CorpusCase",
    "CorpusCaseInput",
    "CorpusLoadError",
    "ExpectedSpan",
    "ReconstructionExpectation",
    "TaskFamily",
    "TaskNecessity",
    "load_case",
    "load_corpus",
]
