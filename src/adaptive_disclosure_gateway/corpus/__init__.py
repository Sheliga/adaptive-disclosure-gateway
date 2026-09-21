"""Versioned evaluation-corpus schema and loader (T09 / issue #4, Phase A;
extended per-domain for Contracts by T24 / issue #37).

Public surface:

- ``CorpusCaseInput`` -- everything a treatment may legitimately see.
- ``CaseOracle`` -- ground truth used for scoring only, never privileged
  treatment input.
- ``ExpectedSpan`` / ``ReconstructionExpectation`` / ``TaskNecessity`` /
  ``TaskFamily`` / ``ContractsTaskFamily`` / ``ObligationRelation`` /
  ``NumericUtilityReference`` / ``ReferenceOperator`` -- the oracle's
  building blocks.
- ``CorpusCase`` / ``load_case`` / ``load_corpus`` / ``CorpusLoadError`` --
  loading one or all versioned case files from a corpus directory
  (``corpus/hr/v1/cases/``, ``corpus/contracts/v1/cases/``).

See ``corpus/hr/v1/SCHEMA.md`` and ``corpus/contracts/v1/SCHEMA.md``
(repository root) for each corpus's frozen case-file schema in prose, and
the matching ``README.md`` for what each corpus covers and its
freeze/versioning rule.
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
    CORPUS_SCHEMA_VERSION,
    FROZEN_CATEGORIES_BY_DOMAIN,
    FROZEN_CONTRACTS_CATEGORIES,
    FROZEN_HR_CATEGORIES,
    NUMERIC_REFERENCE_CATEGORIES,
    REGISTERED_CORPUS_DOMAINS,
    TASK_FAMILIES_BY_DOMAIN,
    ContractsTaskFamily,
    ExpectedSpan,
    NumericUtilityReference,
    ObligationRelation,
    ReconstructionExpectation,
    ReferenceOperator,
    TaskFamily,
    TaskNecessity,
)
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle

__all__ = [
    "CORPUS_SCHEMA_VERSION",
    "FROZEN_CATEGORIES_BY_DOMAIN",
    "FROZEN_CONTRACTS_CATEGORIES",
    "FROZEN_HR_CATEGORIES",
    "NUMERIC_REFERENCE_CATEGORIES",
    "REGISTERED_CORPUS_DOMAINS",
    "TASK_FAMILIES_BY_DOMAIN",
    "CaseOracle",
    "ContractsTaskFamily",
    "CorpusCase",
    "CorpusCaseInput",
    "CorpusLoadError",
    "ExpectedSpan",
    "NumericUtilityReference",
    "ObligationRelation",
    "ReconstructionExpectation",
    "ReferenceOperator",
    "TaskFamily",
    "TaskNecessity",
    "load_case",
    "load_corpus",
]
