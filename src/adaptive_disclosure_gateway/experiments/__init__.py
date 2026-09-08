"""T10 -- the experiment runner, evaluation metrics and B0-B4 pilot
(GitHub issue #8).

Responsibilities are split by module, per the T10 brief:

- ``corpus_source`` -- corpus loading and ground-truth-free request
  construction;
- ``run_identity`` -- deterministic run identity vs. volatile run metadata;
- ``treatments`` -- treatment construction;
- ``provider_instrumentation`` -- provider-call timing/volume capture;
- ``span_capture`` / ``stage_timing`` / ``b4_span_metadata`` -- real OTel
  span capture and stage-aware timing/metadata extraction;
- ``execution`` -- the ground-truth-isolated case-execution boundary;
- ``scoring`` (subpackage) -- conformance, exposure, unnecessary
  disclosure, utility, reconstruction and outcome classification;
- ``case_result`` -- combined, safe/serializable per-case result;
- ``aggregation`` -- descriptive per-treatment and pairwise summaries;
- ``contextual_matrix`` -- the B3->B4 contextual policy comparisons;
- ``runner`` / ``artifacts`` -- orchestration and disk serialization.

This package is experimental/evaluation code, not production disclosure
control: no module under ``transformations/``, ``detection/``,
``task_analysis/``, ``policies.py`` or ``pipeline.py`` may import anything
from here, and this package's own execution boundary never receives a
``CaseOracle`` -- see ``tests/test_experiments_ground_truth_isolation.py``.
"""

from __future__ import annotations
