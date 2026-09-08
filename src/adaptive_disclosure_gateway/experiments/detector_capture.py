"""Recording-detector wrapper for T10's detector-scoring layer (PR #35
review, blocker 2).

The issue #8 acceptance criteria require precision/recall/F1 for the
detector against the corpus's frozen ``expected_spans``, but scoring must
never run a *second*, independently-invoked ``Detector`` pass after the
fact -- that would score a detector call the treatment never actually saw,
and could silently drift from what really happened during execution (a
different rule set, a different text encoding, ...). Instead, this module
wraps the real ``Detector`` object ``execution.execute_case`` already
constructs and hands to ``pipeline.run_disclosure_case`` (via
``span_capture.run_case_with_span_capture``), and records the *actual*
spans it returned, in call order.

``pipeline.run_disclosure_case`` calls ``detector.detect(...)`` up to twice
per case: once over ``request.text`` (always -- what every treatment's own
``sanitize()`` actually decided against), and, for every treatment except
B0 -- Direct, a second time over ``request.task`` (the fail-closed
sensitive-task check -- see ``pipeline.py``'s module docstring).
``text_spans`` is always the *first* recorded call, mirroring
``stage_timing.py``'s identical assumption about call/span ordering, so
detector scoring is unambiguous even for treatments that trigger the second
call.

Never records ``SensitiveSpan.value`` -- only ``category``/``start``/``end``
(CLAUDE.md's no-leak invariant): a detected span's own text is exactly the
sensitive value disclosure control exists to protect, and detector scoring
only ever needs to know *where* and *what category* a span landed, never
what it said.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import SensitiveSpan


@dataclass(frozen=True)
class DetectedSpanRef:
    """A category/offset-only reference to one span the detector actually
    returned. Deliberately has no ``value``/``confidence`` field -- see the
    module docstring.
    """

    category: str
    start: int
    end: int


def _to_refs(spans: Sequence[SensitiveSpan]) -> tuple[DetectedSpanRef, ...]:
    return tuple(DetectedSpanRef(category=s.category, start=s.start, end=s.end) for s in spans)


@dataclass
class RecordingDetector:
    """Wraps a real ``Detector`` and records the (category, start, end)-only
    shape of every span it returns, in call order.

    Satisfies the same duck-typed ``detect(text) -> list[SensitiveSpan]``
    contract ``pipeline.run_disclosure_case`` already calls against a plain
    ``Detector`` -- a drop-in replacement from its point of view, exactly
    like ``provider_instrumentation.TimingProviderDelegate`` is for
    ``Provider``. A fresh instance should be constructed per case execution
    so ``text_spans`` unambiguously reflects that one case's first
    detection call.
    """

    wrapped: Detector
    calls: list[tuple[DetectedSpanRef, ...]] = field(default_factory=list)

    def detect(self, text: str) -> list[SensitiveSpan]:
        spans = self.wrapped.detect(text)
        self.calls.append(_to_refs(spans))
        return spans

    @property
    def text_spans(self) -> tuple[DetectedSpanRef, ...]:
        """The first recorded ``detect()`` call's spans -- always the call
        over ``request.text`` (see the module docstring). Empty if
        ``detect`` was never called at all.
        """
        return self.calls[0] if self.calls else ()
