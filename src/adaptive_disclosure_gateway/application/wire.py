"""The application layer's own safe wire projection -- the explicit,
allowlisted serialization of ``application/contracts.py``'s response
contracts to a JSON-serializable shape (T20 / issue #28, slice 3: the CLI
adapter).

Every response model below used to live in ``api/schemas.py`` -- but a
serialization shape is not an HTTP concern, it is an application-layer
concern, exactly the same reasoning ``experiments/case_result.py``'s
``to_safe_dict`` already establishes for T10's runner: the layer that owns a
result also owns its one safe, allowlisted projection of that result, rather
than leaving every adapter to invent its own. Moving these models here means
the CLI adapter (``cli.py``) and the HTTP adapter (``api/app.py`` via
``api/schemas.py``) share exactly one allowlist -- a field added later to an
internal contract (``application/contracts.py``, ``audit.py``) cannot leak
through *either* adapter just by being new, because neither adapter defines
its own copy of this mapping to forget updating.

CLAUDE.md's "explicit response schemas -- never blanket serialization" rule
still applies here verbatim: every model below declares its field set
explicitly and is populated field-by-field in its own ``from_domain``
classmethod -- never ``model_validate(dataclasses.asdict(...))`` or any
other blanket/reflective conversion.

``CONTRACT_VERSION`` is a plain string constant, not derived from the
package version -- it identifies this application-response contract shape
specifically (both adapters serve it verbatim) so a client can assert
compatibility, and only needs to change when a response shape actually
changes incompatibly. Its value, ``"t20-application-api-v1"``, is a
published contract identifier and must not be renamed or bumped as part of
this move.

Every enum-valued field below is serialized as its frozen string value
(``Treatment``/``DisclosureStrategy``/``PseudonymScope`` are all
``StrEnum``), never the Python enum repr, so the wire format is plain JSON
strings.

``api/schemas.py`` re-exports every name below verbatim so ``api/app.py``
and the existing HTTP API tests keep working unchanged -- the same
re-export pattern ``experiments/treatments.py`` already uses for
``treatment_factory.build_treatment``. This module itself imports nothing
from ``api/`` or ``fastapi``/``starlette`` (pinned by
``tests/test_api_architecture.py`` and the CLI's own architectural test),
so the CLI can depend on it without pulling FastAPI in at all.

Request-specific schemas (``GovernanceOverridesBody``, ``DisclosureRequestBody``,
``ValidationErrorItem``, ``ValidationErrorResponse``) are deliberately NOT
here: they describe an HTTP request body / FastAPI's own validation-failure
shape, which the CLI does not have -- argparse validates CLI input its own
way.

``StrategyComparisonEntryModel``/``CompareResponse`` (T20 / issue #28's
"Compare strategies" slice) are the wire projection of
``application.contracts.StrategyComparisonEntry``/``StrategyComparison`` --
see that module's docstring for the full design. They reuse
``DisclosureSummaryModel``/``SafeGovernanceViewModel``/``ProviderModeModel``
verbatim rather than redefining an equivalent shape, exactly like
``PreviewResponse`` already does. Adding these does not change
``CONTRACT_VERSION``: it identifies existing response shapes, none of which
changed -- a new response model is an addition, not an incompatible change
to any shape a client already depends on.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from adaptive_disclosure_gateway.application.contracts import (
    CategoryDisclosureSummary,
    DisclosureExecution,
    DisclosureExport,
    DisclosurePreview,
    DisclosureRestore,
    DisclosureSummary,
    DocumentDisclosurePreview,
    SafeGovernanceView,
    StrategyComparison,
    StrategyComparisonEntry,
    StrategyOption,
)
from adaptive_disclosure_gateway.application.examples import ExampleSummary
from adaptive_disclosure_gateway.application.service import ServiceHealth, ServiceReadiness
from adaptive_disclosure_gateway.audit import ProviderStage, ReconstructionStage

CONTRACT_VERSION = "t20-application-api-v1"


# --- GET /health ---------------------------------------------------------------


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


# --- GET /ready (T25 review finding 2) ------------------------------------------


class ReadinessReason(StrEnum):
    """The closed vocabulary ``GET /ready``'s optional ``reason`` field is
    restricted to (``extra="forbid"`` on ``ReadyResponse`` below rejects
    anything else). Every member names a *category* of unreadiness only --
    never a credential, an environment variable's value, a config value or
    any exception text (CLAUDE.md's no-leak invariant). The string values
    are produced independently by ``providers.readiness`` and
    ``application.preview_confirmation`` (which cannot import this module
    without a cycle); this enum is the one place their shared vocabulary is
    pinned as a closed set for the wire contract.
    """

    PROVIDER_CREDENTIAL_MISSING = "provider_credential_missing"
    PROVIDER_SDK_UNAVAILABLE = "provider_sdk_unavailable"
    CONFIRMATION_SECRET_NOT_DURABLE = "confirmation_secret_not_durable"
    PROVIDER_UNRECOGNIZED = "provider_unrecognized"


class ReadyResponse(BaseModel):
    """``GET /ready``'s response -- a purely local readiness probe meant for
    a container healthcheck/orchestrator, not a versioned data contract a
    client parses: unlike every other response model here, it carries no
    ``contract_version``.

    ``reason`` is present only when ``status`` is ``"not_ready"`` and is
    always one of ``ReadinessReason``'s fixed values -- ``extra="forbid"``
    plus the closed enum together mean a caller can never observe anything
    beyond this fixed vocabulary through this endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    status: str
    reason: ReadinessReason | None = None

    @classmethod
    def from_domain(cls, readiness: ServiceReadiness) -> ReadyResponse:
        return cls(
            status="ready" if readiness.ready else "not_ready",
            reason=ReadinessReason(readiness.reason) if readiness.reason is not None else None,
        )


# --- GET /examples ---------------------------------------------------------------


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


# --- GET /strategies ---------------------------------------------------------------


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


# --- POST /documents/preview -----------------------------------------------------


class DocumentPreviewResponse(PreviewResponse):
    """``PreviewResponse`` plus the confirmation the structured-document
    flow requires back on execute.

    A subclass rather than a new field on ``PreviewResponse`` so the
    historical ``/disclosure/preview`` contract is untouched: that surface
    has no confirmation step, and giving every one of its callers a
    permanently-null ``confirmation_token`` would describe a mechanism that
    does not apply to them.

    ``confirmation_token`` is opaque to the client. It is not a session, not
    an identifier of anything stored server-side, and carries no
    representation of the document, the task or the payload -- see
    ``application/preview_confirmation.py``. A client's only correct use of
    it is to send it back unchanged, alongside the identical upload.
    """

    confirmation_token: str

    @classmethod
    def from_document_preview(
        cls, document_preview: DocumentDisclosurePreview
    ) -> DocumentPreviewResponse:
        base = PreviewResponse.from_domain(document_preview.preview)
        return cls(**base.model_dump(), confirmation_token=document_preview.confirmation_token)


# --- POST /disclosure/execute ---------------------------------------------------
#
# ProviderStageModel/ReconstructionStageModel moved here alongside
# ExecuteResponse (which embeds both) even though the ticket's explicit move
# list did not name them individually -- ExecuteResponse.from_domain cannot
# be defined without them, and leaving them behind in api/schemas.py would
# split one response model's shape across two modules.


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


# --- POST /disclosure/compare ---------------------------------------------------


class StrategyComparisonEntryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: str
    treatment: str
    recommended: bool
    unsafe_control_baseline: bool
    summary: DisclosureSummaryModel
    external_payload: str
    payload_byte_count: int

    @classmethod
    def from_domain(cls, entry: StrategyComparisonEntry) -> StrategyComparisonEntryModel:
        return cls(
            strategy=entry.strategy.value,
            treatment=entry.treatment.value,
            recommended=entry.recommended,
            unsafe_control_baseline=entry.unsafe_control_baseline,
            summary=DisclosureSummaryModel.from_domain(entry.summary),
            external_payload=entry.external_payload,
            payload_byte_count=entry.payload_byte_count,
        )


class CompareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    entries: list[StrategyComparisonEntryModel]
    governance: SafeGovernanceViewModel
    provider_mode: ProviderModeModel

    @classmethod
    def from_domain(cls, comparison: StrategyComparison) -> CompareResponse:
        return cls(
            contract_version=CONTRACT_VERSION,
            entries=[
                StrategyComparisonEntryModel.from_domain(entry) for entry in comparison.entries
            ],
            governance=SafeGovernanceViewModel.from_domain(comparison.governance),
            provider_mode=ProviderModeModel(provider_class=comparison.provider_mode.provider_class),
        )


# --- POST /documents/export / POST /documents/restore ---------------------------
#
# T26 / issue #67. Two new, additive response shapes -- neither replaces nor
# widens an existing one, so CONTRACT_VERSION is not bumped (see this
# module's own docstring on why adding a response model is not an
# incompatible change to any shape a client already depends on).
#
# Deliberately excludes anything that would let the mapping travel wholesale:
# ``ExportResponse`` never carries the (pseudonym -> original) entries, only
# ``restore_handle`` (opaque) and ``restorable_count``; ``RestoreResponse``
# never carries the mapping either, only the restored text and two counts.


class ExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    external_payload: str
    restore_handle: str
    expires_at: int
    restorable_count: int
    treatment: str
    strategy: str
    governance: SafeGovernanceViewModel

    @classmethod
    def from_domain(cls, export: DisclosureExport) -> ExportResponse:
        return cls(
            contract_version=CONTRACT_VERSION,
            external_payload=export.external_payload,
            restore_handle=export.restore_handle,
            expires_at=export.expires_at,
            restorable_count=export.restorable_count,
            treatment=export.treatment.value,
            strategy=export.strategy.value,
            governance=SafeGovernanceViewModel.from_domain(export.governance),
        )


class RestoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    restored_text: str
    restored_count: int
    unresolved_count: int

    @classmethod
    def from_domain(cls, restore: DisclosureRestore) -> RestoreResponse:
        return cls(
            contract_version=CONTRACT_VERSION,
            restored_text=restore.restored_text,
            restored_count=restore.restored_count,
            unresolved_count=restore.unresolved_count,
        )


# --- error bodies ------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """The safe body for every non-validation error response (400/404/500).
    ``detail`` is a static, no-leak message (never interpolated content);
    ``kind`` is the raised exception's class name, for client-side branching
    without parsing prose.
    """

    model_config = ConfigDict(extra="forbid")

    detail: str
    kind: str
