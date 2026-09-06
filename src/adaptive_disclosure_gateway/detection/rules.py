from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from adaptive_disclosure_gateway.domain import SensitiveSpan


@dataclass(frozen=True)
class DetectionRule:
    """A single deterministic regex-based detection rule.

    ``group`` selects which regex group becomes the SensitiveSpan value/offsets:
    ``0`` (the default) uses the whole match, a named or numbered group narrows
    the span to just that part of the match (used by the labeled-HR rules to
    exclude the "Label:" prefix from the detected value).
    """

    category: str
    pattern: re.Pattern[str]
    group: str | int = 0
    confidence: float = 1.0

    def find(self, text: str) -> Iterator[SensitiveSpan]:
        for match in self.pattern.finditer(text):
            start, end = match.span(self.group)
            if start == -1:
                continue
            yield SensitiveSpan(
                category=self.category,
                value=match.group(self.group),
                start=start,
                end=end,
                confidence=self.confidence,
            )


# Structured Brazilian identifiers, matched by canonical punctuated format
# only. This is a deliberate scope limit: it avoids inventing heuristics for
# unformatted digit runs (which would collide with phone numbers or other
# numeric identifiers) and does not validate CPF/CNPJ check digits.
CPF_PATTERN = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")
CNPJ_PATTERN = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"\(?\d{2}\)?[\s.-]?\d{4,5}-\d{4}")

STRUCTURED_RULES: tuple[DetectionRule, ...] = (
    DetectionRule("cnpj", CNPJ_PATTERN),
    DetectionRule("cpf", CPF_PATTERN),
    DetectionRule("email", EMAIL_PATTERN),
    DetectionRule("phone", PHONE_PATTERN),
)

# Deliberately simple labeled-line detector for the controlled HR fixture.
# This is NOT a named-entity recognizer: it only recognizes a fixed,
# case-sensitive "Label: value" line format, one value per line. It exists to
# validate the disclosure pipeline against a controlled first vertical slice,
# not to claim general free-text extraction capability.
_LABELS: tuple[tuple[str, str], ...] = (
    ("employee_name", "Employee"),
    ("salary", "Salary"),
    ("department", "Department"),
    ("medical_data", "Medical notes"),
)

LABELED_HR_RULES: tuple[DetectionRule, ...] = tuple(
    DetectionRule(
        category,
        re.compile(rf"^{re.escape(label)}:[ \t]*(?P<value>.+?)[ \t]*$", re.MULTILINE),
        group="value",
    )
    for category, label in _LABELS
)

BUILT_IN_RULES: tuple[DetectionRule, ...] = STRUCTURED_RULES + LABELED_HR_RULES
