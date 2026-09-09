"""The application/use-case boundary (T20 / issue #28, slice 1).

Sits between a future adapter (HTTP/CLI/MCP -- not part of this slice, which
adds no HTTP code at all) and the existing disclosure-control core:

    adapter (future HTTP/CLI/MCP)
      -> application service (this package)
        -> existing core (pipeline / treatments / policies / vault /
           providers / audit)

No module in this package reimplements detection, treatment decisions,
policy resolution, task analysis, pseudonymization, generalization,
reconstruction or the fail-closed task check -- it only calls the existing
core through ``pipeline.decide_disclosure``/``pipeline.run_disclosure_case``.

Ground-truth isolation: this package never imports or references
``CaseOracle``, the bare identifier ``oracle``, ``CorpusCase`` (the bundled
input+oracle type), or anything from ``experiments.scoring`` -- pinned by
``tests/test_application_ground_truth_isolation.py``. Prepared demo examples
(``examples.py``) expose ``CorpusCaseInput`` only.
"""

from __future__ import annotations
