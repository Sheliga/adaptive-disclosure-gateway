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

# Labeled-line rules for the Contracts domain (Issue #56). Same deliberate
# limitation as the HR set above -- a fixed "Label: value" line format, one
# value per line, case-sensitive, no entity recognition and no coreference.
#
# The one Contracts-specific thing worth reading carefully is the role/value
# split. A contract's meaning is relational: "who owes what to whom" is only
# preserved if the ROLE survives while the IDENTITY is transformed. That
# falls out of ``group="value"`` for free, with no relation model, because
# the role word lives in the *label*:
#
#     Contracting party: Aurora Servicos Digitais Ltda
#     ^--- role, never inside the span   ^--- identity, the detected span
#
# so a pseudonymized payload still reads ``Contracting party:
# PSEUDO-party_name-...`` / ``Contracted party: PSEUDO-party_name-...``.
# Combined with the vault's per-value pseudonym stability (the same original
# always resolves to the same pseudonym within a scope), obligation
# assignment survives B2-B4 unchanged. Pinned by
# tests/test_contracts_domain.py's relation-preservation tests.
#
# Both party labels map to the SAME ``party_name`` category on purpose: the
# role is document structure, not a separate information type, and splitting
# it into two categories would have duplicated every policy/action-space
# entry to express something the label already carries.
#
# ``representative_name`` is separate from ``party_name`` because the two are
# different objects under Brazilian data-protection law: a contracting party
# is typically a legal entity (not a natural person, so not an LGPD data
# subject), while a signatory/legal representative is a natural person whose
# name is personal data. Keeping them apart lets a policy govern them
# independently without a schema change, and keeps the audit trail able to
# say which of the two was disclosed.
#
# What is deliberately NOT here: `obligation` and `confidential_clause`.
# Obligation text is the task-bearing content of a contract, not a sensitive
# information unit -- putting ordinary clause prose under disclosure control
# buys no safety and destroys the utility the task needs, and the relation it
# carries is already preserved by the role/value split above. A
# "confidential clause" label would not detect a clause at all; it would
# detect an author's *classification* of one, which is oracle information and
# must never reach the detector at runtime. See
# docs/contracts-policy-matrix.md.
_CONTRACTS_LABELS: tuple[tuple[str, str], ...] = (
    ("party_name", "Contracting party"),
    ("party_name", "Contracted party"),
    ("representative_name", "Representative"),
    ("bank_account", "Bank account"),
    ("contract_value", "Contract value"),
    ("penalty_amount", "Penalty"),
    ("deadline", "Deadline"),
)

LABELED_CONTRACTS_RULES: tuple[DetectionRule, ...] = tuple(
    DetectionRule(
        category,
        re.compile(rf"^{re.escape(label)}:[ \t]*(?P<value>.+?)[ \t]*$", re.MULTILINE),
        group="value",
    )
    for category, label in _CONTRACTS_LABELS
)

BUILT_IN_RULES: tuple[DetectionRule, ...] = (
    STRUCTURED_RULES + LABELED_HR_RULES + LABELED_CONTRACTS_RULES
)
