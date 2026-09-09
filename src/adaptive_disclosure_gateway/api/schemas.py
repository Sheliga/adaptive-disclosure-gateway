"""Explicit pydantic request/response schemas for the HTTP adapter (T20 /
issue #28, slice 2).

CLAUDE.md's "explicit response schemas -- never blanket serialization" rule
(absolute rule 4): every response model below declares its field set
explicitly and is populated field-by-field in its own ``from_domain``
classmethod -- never ``model_validate(dataclasses.asdict(...))`` or any
other blanket/reflective conversion. This means a field added later to an
internal application contract (``application/contracts.py``,
``audit.py``) never silently reaches the public HTTP surface just because
the internal shape grew; extending the HTTP contract is always a deliberate
edit to a model *and* its ``from_domain`` here.

``CONTRACT_VERSION`` is a plain string constant, not derived from the
package version -- it identifies this HTTP contract shape specifically so a
Next.js client can assert compatibility, and only needs to change when a
response shape actually changes incompatibly.

Every enum-valued field below is serialized as its frozen string value
(``Treatment``/``DisclosureStrategy``/``PseudonymScope`` are all
``StrEnum``), never the Python enum repr, so the wire format is plain JSON
strings.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from adaptive_disclosure_gateway.application.contracts import (
    CategoryDisclosureSummary,
    DisclosureExecution,
    DisclosurePreview,
    DisclosureStrategy,
    DisclosureSummary,
    GovernanceOverrides,
    SafeGovernanceView,
    StrategyOption,
)
from adaptive_disclosure_gateway.application.examples import ExampleSummary
from adaptive_disclosure_gateway.application.service import ServiceHealth
from adaptive_disclosure_gateway.audit import ProviderStage, ReconstructionStage
from adaptive_disclosure_gateway.domain import PseudonymScope

CONTRACT_VERSION = "t20-application-api-v1"


# --- request schemas ---------------------------------------------------------


class GovernanceOverridesBody(BaseModel):
    """Mirrors ``application.contracts.GovernanceOverrides`` field for
    field. Every field optional -- a caller supplying none of these gets the
    server's configured defaults untouched (see ``service.py``'s
    ``_merge_overrides``).
    """

    model_config = ConfigDict(extra="forbid")

    purpose: str | None = None
    requester_role: str | None = None
    requester_id: str | None = None
    provider_class: str | None = None
    policy_version: str | None = None
    requested_pseudonym_scope: PseudonymScope | None = None
    session_id: str | None = None
    document_id: str | None = None
    request_id: str | None = None
    domain: str | None = None

    def to_domain(self) -> GovernanceOverrides:
        return GovernanceOverrides(**self.model_dump())


class DisclosureRequestBody(BaseModel):
    """The one shared request body for ``POST /disclosure/preview`` and
    ``POST /disclosure/execute``.

    ``file_content`` is the file's text content, already decoded by the
    caller (the guided UI reads the file client-side) -- NOT a multipart
    upload. See ``api/app.py``'s module docstring for why multipart/binary
    upload is deliberately out of scope for this slice.
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    filename: str | None = None
    file_content: str | None = None
    example_id: str | None = None
    task: str | None = None
    strategy: DisclosureStrategy | None = None
    governance: GovernanceOverridesBody | None = None


# --- GET /health --------------------------------------------------------------


class ProviderHealthModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_class: str
    model_id: str | None
    model_snapshot: str | None
    deterministic_demo_mode: bool

    @classmethod
    def from_domain(cls, health: ServiceHealth) -> ProviderHealthModel:
        return cls(
            provider_class=health.provider_class,
            model_id=health.model_id,
            model_snapshot=health.model_snapshot,
            deterministic_demo_mode=health.deterministic_demo_mode,
        )


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    contract_version: str
    provider: ProviderHealthModel
    treatments_available: list[str]

    @classmethod
    def from_domain(cls, health: ServiceHealth) -> HealthResponse:
        return cls(
            status="ok",
            contract_version=CONTRACT_VERSION,
            provider=ProviderHealthModel.from_domain(health),
            treatments_available=[treatment.value for treatment in health.treatments_available],
        )


# --- GET /examples -------------------------------------------------------------


class ExampleSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: str
    title: str
    domain: str
    purpose: str
    task: str
    character_count: int

    @classmethod
    def from_domain(cls, example: ExampleSummary) -> ExampleSummaryModel:
        return cls(
            example_id=example.example_id,
            title=example.title,
            domain=example.domain,
            purpose=example.purpose,
            task=example.task,
            character_count=example.character_count,
        )


class ExamplesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    examples: list[ExampleSummaryModel]

    @classmethod
    def from_domain(cls, examples: tuple[ExampleSummary, ...]) -> ExamplesResponse:
        return cls(
            contract_version=CONTRACT_VERSION,
            examples=[ExampleSummaryModel.from_domain(example) for example in examples],
        )


# --- GET /strategies -----------------------------------------------------------


class StrategyInfoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: str
    treatment_code: str
    recommended: bool

    @classmethod
    def from_domain(cls, option: StrategyOption) -> StrategyInfoModel:
        return cls(
            strategy=option.strategy.value,
            treatment_code=option.treatment.value,
            recommended=option.recommended,
        )


class StrategiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    strategies: list[StrategyInfoModel]

    @classmethod
    def from_domain(cls, options: tuple[StrategyOption, ...]) -> StrategiesResponse:
        return cls(
            contract_version=CONTRACT_VERSION,
            strategies=[StrategyInfoModel.from_domain(option) for option in options],
        )


# --- shared preview/execute pieces ---------------------------------------------


class CategoryDisclosureSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    outcome: str
    action: str
    crosses_trust_boundary: bool
    occurrence_count: int
    required_for_task: bool | None
    technical_reason: str
    policy_version: str | None
    policy_restricted: bool | None
    impossible_under_policy: bool | None

    @classmethod
    def from_domain(cls, category: CategoryDisclosureSummary) -> CategoryDisclosureSummaryModel:
        return cls(
            category=category.category,
            outcome=category.outcome.value,
            action=category.action.value,
            crosses_trust_boundary=category.crosses_trust_boundary,
            occurrence_count=category.occurrence_count,
            required_for_task=category.required_for_task,
            technical_reason=category.technical_reason,
            policy_version=category.policy_version,
            policy_restricted=category.policy_restricted,
            impossible_under_policy=category.impossible_under_policy,
        )


class DisclosureSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    categories: list[CategoryDisclosureSummaryModel]
    detected_span_count: int
    detected_categories: list[str]

    @classmethod
    def from_domain(cls, summary: DisclosureSummary) -> DisclosureSummaryModel:
        return cls(
            status=summary.status,
            categories=[
                CategoryDisclosureSummaryModel.from_domain(category)
                for category in summary.categories
            ],
            detected_span_count=summary.detected_span_count,
            detected_categories=list(summary.detected_categories),
        )


class SafeGovernanceViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    purpose: str
    policy_version: str
    provider_class: str
    requester_role: str | None
    requested_pseudonym_scope: str

    @classmethod
    def from_domain(cls, governance: SafeGovernanceView) -> SafeGovernanceViewModel:
        return cls(
            domain=governance.domain,
            purpose=governance.purpose,
            policy_version=governance.policy_version,
            provider_class=governance.provider_class,
            requester_role=governance.requester_role,
            requested_pseudonym_scope=governance.requested_pseudonym_scope.value,
        )


# --- POST /disclosure/preview ---------------------------------------------------


class ProviderModeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_class: str


class PreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    summary: DisclosureSummaryModel
    external_payload: str
    payload_byte_count: int
    treatment: str
    strategy: str
    governance: SafeGovernanceViewModel
    provider_mode: ProviderModeModel

    @classmethod
    def from_domain(cls, preview: DisclosurePreview) -> PreviewResponse:
        return cls(
            contract_version=CONTRACT_VERSION,
            summary=DisclosureSummaryModel.from_domain(preview.summary),
            external_payload=preview.external_payload,
            payload_byte_count=preview.payload_byte_count,
            treatment=preview.treatment.value,
            strategy=preview.strategy.value,
            governance=SafeGovernanceViewModel.from_domain(preview.governance),
            provider_mode=ProviderModeModel(provider_class=preview.provider_mode.provider_class),
        )


# --- POST /disclosure/execute ---------------------------------------------------


class ProviderStageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    called: bool
    provider_class: str | None
    model_id: str | None
    model_snapshot: str | None
    decoding_config: dict[str, Any] | None
    transmitted_bytes: int | None
    response_hash: str | None
    failed: bool
    failure_kind: str | None

    @classmethod
    def from_domain(cls, provider: ProviderStage) -> ProviderStageModel:
        return cls(
            called=provider.called,
            provider_class=provider.provider_class,
            model_id=provider.model_id,
            model_snapshot=provider.model_snapshot,
            decoding_config=dict(provider.decoding_config)
            if provider.decoding_config is not None
            else None,
            transmitted_bytes=provider.transmitted_bytes,
            response_hash=provider.response_hash,
            failed=provider.failed,
            failure_kind=provider.failure_kind,
        )


class ReconstructionStageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted: bool
    reconstructed_hash: str | None
    changed_from_provider_response: bool | None

    @classmethod
    def from_domain(cls, reconstruction: ReconstructionStage) -> ReconstructionStageModel:
        return cls(
            attempted=reconstruction.attempted,
            reconstructed_hash=reconstruction.reconstructed_hash,
            changed_from_provider_response=reconstruction.changed_from_provider_response,
        )


class ExecuteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    status: str
    summary: DisclosureSummaryModel
    final_answer: str | None
    provider: ProviderStageModel
    reconstruction: ReconstructionStageModel
    treatment: str
    strategy: str
    governance: SafeGovernanceViewModel
    total_ms: float

    @classmethod
    def from_domain(cls, execution: DisclosureExecution) -> ExecuteResponse:
        return cls(
            contract_version=CONTRACT_VERSION,
            status=execution.summary.status,
            summary=DisclosureSummaryModel.from_domain(execution.summary),
            final_answer=execution.final_answer,
            provider=ProviderStageModel.from_domain(execution.provider),
            reconstruction=ReconstructionStageModel.from_domain(execution.reconstruction),
            treatment=execution.treatment.value,
            strategy=execution.strategy.value,
            governance=SafeGovernanceViewModel.from_domain(execution.governance),
            total_ms=execution.total_ms,
        )


# --- error bodies ----------------------------------------------------------------


class ErrorResponse(BaseModel):
    """The safe body for every non-validation error response (400/404/500).
    ``detail`` is a static, no-leak message (never interpolated content);
    ``kind`` is the raised exception's class name, for client-side branching
    without parsing prose.
    """

    model_config = ConfigDict(extra="forbid")

    detail: str
    kind: str


class ValidationErrorItem(BaseModel):
    """One pydantic validation error, stripped of FastAPI's default
    ``input`` echo -- see ``api/app.py``'s ``RequestValidationError``
    handler for why.
    """

    model_config = ConfigDict(extra="forbid")

    loc: list[str]
    type: str
    msg: str


class ValidationErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: list[ValidationErrorItem]
