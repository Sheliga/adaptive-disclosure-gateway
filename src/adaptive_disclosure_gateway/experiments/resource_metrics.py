"""Process CPU-time and peak-memory measurement for T10's pilot (PR #35
review, blocker 3).

Deliberately simple, stdlib-only measurement -- never a sophisticated
profiler:

- ``cpu_time_ms`` is a delta of ``time.process_time()``, which reports the
  whole process's accumulated system+user CPU time. ``run_pilot`` executes
  case executions serially, one at a time, on the main thread, so in
  practice this delta reflects only the measured call -- but the primitive
  itself is process-wide, not call-scoped, so a caller running concurrent
  work during the measured window would see that work's CPU time folded in
  too. Documented here rather than hidden.
- ``peak_memory_bytes`` is ``tracemalloc``'s peak *traced* allocation size:
  memory allocated through Python's own allocator during the measured
  window. This is not resident set size (RSS) and does not capture
  allocations made by C extensions outside Python's allocator -- a
  deliberately simple, portable proxy (identical on every platform this
  runs on), not a full memory profile.

``measurement_scope`` is a required, free-text field naming exactly what
code ran inside the measured window (e.g. ``"detection+treatment+provider"``
for the whole ``run_disclosure_case`` call) -- callers must never claim a
scope narrower than what was actually measured (e.g. presenting a
whole-pipeline measurement as if it covered only a treatment's own
``sanitize()``).
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceMetrics:
    cpu_time_ms: float
    peak_memory_bytes: int
    measurement_scope: str


def measure_resources[T](scope: str, fn: Callable[[], T]) -> tuple[T, ResourceMetrics]:
    """Run ``fn`` once, measuring process CPU time and peak Python-level
    memory allocation across the call.

    ``scope`` must describe, in plain text, exactly what ``fn`` does (e.g.
    ``"detection+treatment+provider"``) -- see the module docstring.

    ``tracemalloc`` is started only if it was not already running -- a
    nested call (never expected in this runner) would otherwise reset an
    outer measurement's baseline instead of composing with it. Whichever
    call started it also stops it, so a caller never leaves it running
    process-wide by accident; a call that finds tracing already active
    resets the peak counter instead, so its own measurement window still
    starts from zero.
    """
    already_tracing = tracemalloc.is_tracing()
    if already_tracing:
        tracemalloc.reset_peak()
    else:
        tracemalloc.start()

    cpu_started = time.process_time()
    result = fn()
    cpu_time_ms = (time.process_time() - cpu_started) * 1000

    _current, peak = tracemalloc.get_traced_memory()
    if not already_tracing:
        tracemalloc.stop()

    return result, ResourceMetrics(
        cpu_time_ms=cpu_time_ms, peak_memory_bytes=peak, measurement_scope=scope
    )
