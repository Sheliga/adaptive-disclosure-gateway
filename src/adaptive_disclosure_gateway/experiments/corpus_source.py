"""Corpus loading and request construction for T10's experiment runner.

This is the *only* place in ``experiments`` that touches
``adaptive_disclosure_gateway.corpus`` for both halves of a case
(``CorpusCase.input`` and ``.oracle``) side by side -- callers further down
the runner (``execution.py``, ``treatments.py``, ``provider_instrumentation.py``)
receive only ``CorpusCaseInput``, never ``CaseOracle`` (see
``tests/test_experiments_ground_truth_isolation.py``). ``build_request``
below is the single function that turns a ``CorpusCaseInput`` into the
``DisclosureRequest`` a treatment actually runs -- it reads only fields
``CorpusCaseInput`` itself declares, mirroring
``CorpusCaseInput.to_disclosure_request()`` plus the harness defaulting
``scripts/report_b3_corpus_divergence.py`` already established for a
session-scope identifier a case omits.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.corpus.loader import CorpusCase, load_corpus
from adaptive_disclosure_gateway.domain import DisclosureRequest

# A fixed harness session id, filled in only for a case that omits one in its
# own YAML -- exactly what a real caller supplying the SESSION-scope
# lifecycle identifier would do (see pipeline.py's "identifier contract"
# docstring and scripts/report_b3_corpus_divergence.py's own precedent).
# Never overrides a case that already supplies its own.
DEFAULT_HARNESS_SESSION_ID = "t10-experiment-runner-session"


def load_hr_v1_cases(directory: str | Path) -> list[CorpusCase]:
    """Load every case in the frozen HR v1 corpus, sorted by file name."""
    return load_corpus(directory)


def build_request(
    case_input: CorpusCaseInput,
    *,
    default_session_id: str = DEFAULT_HARNESS_SESSION_ID,
    context_overrides: Mapping[str, Any] | None = None,
) -> DisclosureRequest:
    """Build the ``DisclosureRequest`` a treatment actually runs against.

    Reads only ``case_input`` -- never a ``CaseOracle`` -- exactly like
    ``CorpusCaseInput.to_disclosure_request()`` itself.

    ``context_overrides`` lets the B3->B4 contextual-matrix comparisons
    (``experiments/contextual_matrix.py``) vary a single ``GovernanceContext``
    dimension (``purpose``/``requester_role``/``provider_class``/
    ``policy_version``) while holding ``text``/``task`` and every other
    context field byte-for-byte identical -- the same
    ``GovernanceContext.model_copy(update=...)`` technique
    ``tests/test_hr_policy_matrix.py`` and
    ``scripts/report_b3_corpus_divergence.py`` already use, applied here
    only at the request-construction boundary, never by editing the frozen
    corpus or policy documents themselves.
    """
    request = case_input.to_disclosure_request()
    context = request.context
    if context.session_id is None:
        context = context.model_copy(update={"session_id": default_session_id})
    if context_overrides:
        context = context.model_copy(update=dict(context_overrides))
    if context is request.context:
        return request
    return DisclosureRequest(text=request.text, task=request.task, context=context)
