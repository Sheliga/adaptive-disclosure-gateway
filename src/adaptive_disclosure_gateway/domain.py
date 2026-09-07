from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DisclosureAction(StrEnum):
    PRESERVE = "preserve"
    PSEUDONYMIZE = "pseudonymize"
    GENERALIZE = "generalize"
    REMOVE = "remove"
    BLOCK_REQUEST = "block_request"
    TASK_DEPENDENT = "task_dependent"


class PseudonymScope(StrEnum):
    REQUEST = "request"
    DOCUMENT = "document"
    SESSION = "session"
    ORGANIZATION = "organization"


class Treatment(StrEnum):
    """The five experimental disclosure-control treatments, B0-B4.

    Member names carry the intent (what the treatment does); member values
    carry experimental traceability (the frozen B0-B4 identifiers used
    throughout the research design, docs and telemetry). The values must
    never change -- see docs/experimental-design.md for the canonical
    sequence Direct -> Static Sanitization -> Reversible Pseudonymization ->
    Task-aware -> Policy-governed and what each comparison isolates.
    """

    DIRECT = "b0"
    STATIC_SANITIZATION = "b1"
    REVERSIBLE_PSEUDONYMIZATION = "b2"
    TASK_AWARE = "b3"
    POLICY_GOVERNED = "b4"


class GovernanceContext(BaseModel):
    domain: str
    purpose: str
    requester_role: str | None = None
    requester_id: str | None = None
    provider_class: str = "external_llm"
    policy_version: str
    requested_pseudonym_scope: PseudonymScope = PseudonymScope.SESSION


class SensitiveSpan(BaseModel):
    # ``start``/``end`` are required: a span that does not know where it sits
    # in the source text must not be constructible at all, rather than being
    # silently coerced to offset 0 downstream (see issue #17). ``confidence``
    # stays optional -- it is legitimately unknown for some detection rules.
    category: str
    value: str
    start: int
    end: int
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _check_offsets(self) -> "SensitiveSpan":
        # Only checks that do not require the source text: in-bounds,
        # non-inverted, non-zero-length. Text-relative checks (end within the
        # source text, the slice matching ``value``) live at the
        # transformation boundary, which is the only place that has the text.
        if self.start < 0:
            raise ValueError("SensitiveSpan.start must be >= 0")
        if self.end <= self.start:
            raise ValueError("SensitiveSpan.end must be greater than start")
        return self


def span_offsets_are_structurally_valid(span: SensitiveSpan) -> bool:
    """True if ``span.start``/``span.end`` are structurally valid without
    reference to any source text: both are ``int`` instances, ``start >= 0``,
    and ``end > start``.

    This is the text-independent half of offset validation -- it cannot check
    whether ``end`` falls within a particular text or whether the slice it
    names matches ``span.value``, because it has no text to check against.
    ``SensitiveSpan``'s own validator already enforces this for normal
    construction, but ``SensitiveSpan.model_construct`` bypasses Pydantic
    validation entirely, so a span reaching here may still have missing or
    invalid offsets (e.g. ``start=None, end=None``).

    Both ``transformations/span_validation.py`` (which adds the text-relative
    checks) and ``detection/overlap.py`` (which must fail closed before
    sorting spans by offset) need exactly this check. It lives here, on
    ``domain``, rather than in either package, so that ``detection`` does not
    have to import from ``transformations`` to reuse it.
    """
    start, end = span.start, span.end
    if not isinstance(start, int) or not isinstance(end, int):
        return False
    if start < 0:
        return False
    return end > start


class PolicyDecision(BaseModel):
    category: str
    action: DisclosureAction
    reason: str
    task_required: bool | None = None
    allowed_actions: list[DisclosureAction] = Field(default_factory=list)
    policy_version: str | None = None


class Transformation(BaseModel):
    category: str
    original: str
    transformed: str | None
    action: DisclosureAction


class DisclosureRequest(BaseModel):
    text: str
    task: str
    context: GovernanceContext


class DisclosureResult(BaseModel):
    external_payload: str
    decisions: list[PolicyDecision]
    transformations: list[Transformation]
    reconstruction_required: bool = False
    status: Literal["allowed", "blocked"] = "allowed"
