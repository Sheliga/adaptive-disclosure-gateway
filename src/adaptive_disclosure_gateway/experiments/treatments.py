"""Re-exports the treatment factory for T10's experiment runner.

T20 / issue #28, slice 1 moved the actual ``build_treatment`` implementation
to ``adaptive_disclosure_gateway.treatment_factory`` -- a neutral module
neither this runner package nor the new ``application`` package owns -- so
that the advisor-demo application service can build treatments the same way
this runner always has, without importing runner code (and without a second,
duplicated factory). See ``treatment_factory.py``'s module docstring for the
full rationale.

This module keeps re-exporting ``build_treatment`` under its original name
and location so every existing runner call site
(``experiments/execution.py``'s ``from .treatments import build_treatment``)
and every test importing ``adaptive_disclosure_gateway.experiments.treatments``
keeps working unchanged.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.treatment_factory import build_treatment

__all__ = ["build_treatment"]
