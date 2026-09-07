from __future__ import annotations

import time

from adaptive_disclosure_gateway.domain import SensitiveSpan
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer

from .overlap import resolve_overlaps
from .rules import BUILT_IN_RULES, DetectionRule


class Detector:
    """Deterministic, rule-based sensitive-data detector.

    Combines regex rules for structured Brazilian identifiers (CPF, CNPJ,
    e-mail, phone) with a deliberately simple labeled-line detector for the
    controlled HR fixture (employee_name, salary, department, medical_data).

    This is explicitly NOT a general named-entity recognizer and depends on
    no NER library or model: a category with no rule registered here is
    simply never detected, by design.
    """

    def __init__(self, rules: tuple[DetectionRule, ...] | None = None) -> None:
        self._rules = BUILT_IN_RULES if rules is None else tuple(rules)

    def detect(self, text: str) -> list[SensitiveSpan]:
        tracer = get_tracer()
        with tracer.start_as_current_span("detection.detect") as span:
            started = time.perf_counter()
            raw_spans: list[SensitiveSpan] = []
            for rule in self._rules:
                raw_spans.extend(rule.find(text))
            resolved = resolve_overlaps(raw_spans)
            elapsed_ms = elapsed_ms_since(started)

            # Metadata only: categories, counts and timing -- never the
            # detected value, the raw text, or the payload.
            span.set_attribute("detection.rule_count", len(self._rules))
            span.set_attribute("detection.raw_span_count", len(raw_spans))
            span.set_attribute("detection.span_count", len(resolved))
            span.set_attribute("detection.categories", sorted({s.category for s in resolved}))
            span.set_attribute("detection.duration_ms", elapsed_ms)

            return resolved
