"""Explicit pydantic request schemas for the HTTP adapter (T20 / issue #28,
slice 2), plus a re-export of the shared application-layer response models.

CLAUDE.md's "explicit response schemas -- never blanket serialization" rule
(absolute rule 4) still governs every response model used here -- it is just
that, as of T20 / issue #28 slice 3 (the CLI adapter), those response models
live in ``adaptive_disclosure_gateway.application.wire`` instead of here: a
serialization shape is an application-layer concern, not an HTTP one, and
the CLI adapter needs the exact same one so its ``--json`` output is
byte-identical to this API's. See ``application/wire.py``'s own module
docstring for the full rationale.

Every name below that used to be defined in this module is re-exported
verbatim from ``application.wire`` so ``api/app.py`` and the existing HTTP
API tests keep importing them from here unchanged -- the same re-export
pattern ``experiments/treatments.py`` already uses for
``treatment_factory.build_treatment``.

What actually stays defined in this module is HTTP-request-specific and has
no CLI equivalent: ``GovernanceOverridesBody``/``DisclosureRequestBody``
(the HTTP request body shape) and ``ValidationErrorItem``/
``ValidationErrorResponse`` (FastAPI/pydantic's own validation-failure
shape specifically -- the CLI has no such thing, argparse validates its own
input its own way).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from adaptive_disclosure_gateway.application.contracts import (
    DisclosureStrategy,
    GovernanceOverrides,
)
from adaptive_disclosure_gateway.application.presets import DocumentAnalysisPreset
from adaptive_disclosure_gateway.application.wire import (
    CONTRACT_VERSION,
    CategoryDisclosureSummaryModel,
    CompareResponse,
    DisclosureSummaryModel,
    DocumentPreviewResponse,
    ErrorResponse,
    ExamplesResponse,
    ExampleSummaryModel,
    ExecuteResponse,
    HealthResponse,
    PreviewResponse,
    ProviderHealthModel,
    ProviderModeModel,
    ProviderStageModel,
    ReconstructionStageModel,
    SafeGovernanceViewModel,
    StrategiesResponse,
    StrategyComparisonEntryModel,
    StrategyInfoModel,
)
from adaptive_disclosure_gateway.domain import PseudonymScope

__all__ = [
    "CONTRACT_VERSION",
    "CategoryDisclosureSummaryModel",
    "CompareResponse",
    "DisclosureRequestBody",
    "DisclosureSummaryModel",
    "DocumentPreviewResponse",
    "DocumentTypeModel",
    "DocumentTypesResponse",
    "ErrorResponse",
    "ExampleSummaryModel",
    "ExamplesResponse",
    "ExecuteResponse",
    "GovernanceOverridesBody",
    "HealthResponse",
    "PreviewResponse",
    "ProviderHealthModel",
    "ProviderModeModel",
    "ProviderStageModel",
    "ReconstructionStageModel",
    "SafeGovernanceViewModel",
    "StrategiesResponse",
    "StrategyComparisonEntryModel",
    "StrategyInfoModel",
    "ValidationErrorItem",
    "ValidationErrorResponse",
]


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
    caller -- NOT a multipart upload, and it cannot carry a PDF or DOCX. A
    structured document goes to ``POST /documents/preview``/
    ``POST /documents/execute`` instead, which take multipart form data and
    select governance through a server-validated preset rather than through
    ``governance`` below.
    """

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    filename: str | None = None
    file_content: str | None = None
    example_id: str | None = None
    task: str | None = None
    strategy: DisclosureStrategy | None = None
    governance: GovernanceOverridesBody | None = None


# --- document-upload vocabulary ---------------------------------------------


class DocumentTypeModel(BaseModel):
    """One entry of ``GET /documents/types``: the caller-facing vocabulary a
    UI needs to build an upload form, and deliberately nothing else.

    Carries the document-type token and its allowlisted analysis modes.
    It does NOT carry ``domain``, ``policy_version`` or ``requester_role``:
    those are what the server resolves *from* this token, and shipping them
    to the browser would invite a client to send them back as if they were
    its own decision -- the exact coupling ``application/presets.py`` exists
    to remove. Human-readable labels for these tokens belong in the UI's own
    copy layer, not in this contract.
    """

    model_config = ConfigDict(extra="forbid")

    document_type: str
    analysis_modes: list[str]
    default_analysis_mode: str

    @classmethod
    def from_domain(cls, preset: DocumentAnalysisPreset) -> DocumentTypeModel:
        return cls(
            document_type=preset.document_type,
            analysis_modes=list(preset.analysis_modes),
            default_analysis_mode=preset.default_analysis_mode,
        )


class DocumentTypesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = CONTRACT_VERSION
    document_types: list[DocumentTypeModel]

    @classmethod
    def from_domain(cls, presets: Sequence[DocumentAnalysisPreset]) -> DocumentTypesResponse:
        return cls(document_types=[DocumentTypeModel.from_domain(p) for p in presets])


# --- error bodies ----------------------------------------------------------------


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
