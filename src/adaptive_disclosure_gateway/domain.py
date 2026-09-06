from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DisclosureAction(StrEnum):
    PRESERVE = "preserve"
    PSEUDONYMIZE = "pseudonymize"
    GENERALIZE = "generalize"
    REMOVE = "remove"
    BLOCK_REQUEST = "block_request"
    TASK_DEPENDENT = "task_dependent"


class GovernanceContext(BaseModel):
    domain: str
    purpose: str
    requester_role: str | None = None
    provider_class: str = "external_llm"
    policy_version: str


class SensitiveSpan(BaseModel):
    category: str
    value: str
    start: int | None = None
    end: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class PolicyDecision(BaseModel):
    category: str
    action: DisclosureAction
    reason: str
    task_required: bool | None = None


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
