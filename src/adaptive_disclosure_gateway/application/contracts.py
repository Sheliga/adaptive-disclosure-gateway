"""The stable application-layer contract for the disclosure preview/execute
use cases (T20 / issue #28, slice 1).

Every result contract here is a frozen dataclass, and every one of them is
no-leak safe by construction:

- ``Transformation.original``/``Transformation.transformed`` (the vault
  mapping) never appear anywhere below -- only counts derived from them
  (``CategoryDisclosureSummary.occurrence_count``, see ``summaries.py``).
- ``DisclosurePreview.external_payload`` IS returned deliberately: it is
  exactly the representation that would cross the trust boundary, returned
  to the same caller who supplied the source content, and it is the whole
  point of a "review before sending" screen. This is not a leak -- it is the
  product surface this slice exists to build.
- ``SafeGovernanceView`` exposes only ``domain``/``purpose``/``policy_version``/
  ``provider_class``/``requester_role``/``requested_pseudonym_scope``. It
  never exposes ``requester_id`` or any lifecycle identifier
  (``session_id``/``document_id``/``request_id``) -- see
  ``tests/test_application_contracts.py``'s dedicated pin.
- ``DisclosureExecution.provider``/``.reconstruction`` reuse
  ``audit.ProviderStage``/``audit.ReconstructionStage`` verbatim rather than
  redefining an equivalent shape: those types are already no-leak safe by
  construction (metadata/hashes only, never a raw value or provider message
  -- see ``audit.py``'s own module docstring), and redefining them here
  would be exactly the kind of duplicated-shape drift this ticket's "no
  duplicated logic" rule warns against.

``DisclosureExecution.total_ms`` is a basic wall-clock convenience for the
UI (how long the whole use case took, start to finish). It is explicitly
NOT the T10 scientific latency metric (``experiments/stage_timing.py``,
which requires the exact span-topology proof T10 relies on) and must never
be used as one.

``StrategyComparisonEntry``/``StrategyComparison`` (T20 / issue #28's
"Compare strategies" slice, issue #29/#41): the educational surface that
runs the SAME content through every B0-B4 strategy and shows what each one
would disclose.

This comparison is PREVIEW-based and must NEVER call a provider, for any
strategy -- see ``service.compare_strategies``'s own docstring for the full
reasoning (in short: B0 -- Direct discloses the raw document unchanged by
design, so *executing* a comparison would send the caller's unprotected
document to an external provider merely to illustrate a teaching point;
with ``FakeProvider`` the responses carry no task utility at all today, so
executing adds nothing now and only creates that risk once T22/#30 wires in
a real provider). Showing exactly what each strategy *would* send is the
entire pedagogical content of the comparison. An execute-based/
utility-aware comparison is explicitly deferred, and would require both
T22 and a deliberate decision about whether B0 may ever run against a real
provider on user content.

This is also NOT an evaluation surface: it never imports
``experiments.scoring``, never touches the oracle, never computes
conformance/exposure/unnecessary-disclosure or any T10 metric, and never
ranks/scores/declares a "best" strategy -- it reports facts each preview
already produced. The only judgment it expresses is the pre-existing
``recommended`` flag ``list_strategy_options`` already documents as a
product/UX default, not a scientific claim. No aggregate counts, ratios,
deltas or "protection score" are added here -- a UI that wants those can
already derive them from ``summary.categories`` on each entry.

``StrategyComparisonEntry.strategy`` is always one of the five explicit
``b0``-``b4`` values, never ``DisclosureStrategy.RECOMMENDED`` --
``recommended`` is a separate boolean precisely so ``RECOMMENDED`` (a
sentinel meaning "resolve this for me") never needs to appear as a value
alongside the four explicit strategies it could resolve to.
``unsafe_control_baseline`` is derived from the existing
``pipeline.UnsafeControlTreatment`` capability marker -- never a hardcoded
comparison against ``Treatment.DIRECT`` -- so it stays correct if a future
treatment ever gained the same marker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from adaptive_disclosure_gateway.application.ingestion import NormalizedContent
from adaptive_disclosure_gateway.audit import ProviderStage, ReconstructionStage
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    GovernanceContext,
    PseudonymScope,
    Treatment,
)


class DisclosureStrategy(StrEnum):
    """What the caller asks for. ``RECOMMENDED`` is the novice default and
    is the only value the guided UI needs to know; the explicit B0-B4
    values exist for the optional research/comparison surface.

    Values reuse ``Treatment``'s own frozen ``"b0"``-``"b4"`` codes verbatim
    (CLAUDE.md: frozen codes must never change) -- no new codes are minted
    here.
    """

    RECOMMENDED = "recommended"
    DIRECT = "b0"
    STATIC_SANITIZATION = "b1"
    REVERSIBLE_PSEUDONYMIZATION = "b2"
    TASK_AWARE = "b3"
    POLICY_GOVERNED = "b4"


# RECOMMENDED -> POLICY_GOVERNED is a product/UX default for the guided demo
# -- "the treatment we recommend a novice caller use" -- and is not a
# scientific claim that B4 dominates every comparison; it never changes any
# treatment's semantics, and every explicit B0-B4 value still maps to
# exactly the treatment it names.
_STRATEGY_TO_TREATMENT: dict[DisclosureStrategy, Treatment] = {
    DisclosureStrategy.DIRECT: Treatment.DIRECT,
    DisclosureStrategy.STATIC_SANITIZATION: Treatment.STATIC_SANITIZATION,
    DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION: Treatment.REVERSIBLE_PSEUDONYMIZATION,
    DisclosureStrategy.TASK_AWARE: Treatment.TASK_AWARE,
    DisclosureStrategy.POLICY_GOVERNED: Treatment.POLICY_GOVERNED,
    DisclosureStrategy.RECOMMENDED: Treatment.POLICY_GOVERNED,
}


def resolve_treatment(strategy: DisclosureStrategy) -> Treatment:
    """Map a caller-facing ``DisclosureStrategy`` to the ``Treatment`` the
    core actually runs. See the module-level comment above for why
    ``RECOMMENDED`` maps to ``Treatment.POLICY_GOVERNED``.
    """
    return _STRATEGY_TO_TREATMENT[strategy]


# CLAUDE.md's canonical treatment sequence, Direct -> Static Sanitization ->
# Reversible Pseudonymization -> Task-aware -> Policy-governed, expressed as
# an explicit, named tuple of the five explicit DisclosureStrategy values
# (never RECOMMENDED) -- deliberately NOT `tuple(DisclosureStrategy)` (whose
# declaration order happens to put RECOMMENDED first and would silently
# change if that enum's declaration order ever did) and not derived from
# Treatment's own declaration order either. `service.compare_strategies`
# iterates this tuple, and only this tuple, to decide entry order.
CANONICAL_COMPARISON_ORDER: tuple[DisclosureStrategy, ...] = (
    DisclosureStrategy.DIRECT,
    DisclosureStrategy.STATIC_SANITIZATION,
    DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
    DisclosureStrategy.TASK_AWARE,
    DisclosureStrategy.POLICY_GOVERNED,
)


@dataclass(frozen=True)
class StrategyOption:
    """One entry of the B0-B4 + recommended discovery list (T20 / issue #28,
    slice 2's ``GET /strategies``). Pure data -- listing these never
    executes anything, and never carries human prose: the UI owns copy
    (issue #29 -- "no scientific identifiers should be translated
    internally").
    """

    strategy: DisclosureStrategy
    treatment: Treatment
    recommended: bool


def list_strategy_options() -> tuple[StrategyOption, ...]:
    """Every ``DisclosureStrategy`` value paired with the ``Treatment`` it
    resolves to and whether it is the novice default -- in
    ``DisclosureStrategy``'s own declaration order, so ``RECOMMENDED`` is
    always first.
    """
    return tuple(
        StrategyOption(
            strategy=strategy,
            treatment=resolve_treatment(strategy),
            recommended=strategy is DisclosureStrategy.RECOMMENDED,
        )
        for strategy in DisclosureStrategy
    )


@dataclass(frozen=True)
class GovernanceOverrides:
    """Optional per-request overrides for the server-configured default
    ``GovernanceContext``. Every field optional: a novice caller supplies
    none of these and gets the server's configured defaults untouched.
    """

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


@dataclass(frozen=True)
class DocumentRequestDescriptor:
    """The caller-facing selection an uploaded document was analysed under.

    Carried on the request so the preview-confirmation fingerprint can bind
    what the *caller asked for* (``document_type``/``analysis_mode``) and not
    only what the server resolved it to. The two are not interchangeable: a
    future preset could map two document types onto one governance
    configuration, and an approval of one must not authorise the other.

    ``analysis_mode`` is always the resolved mode -- never ``None`` -- so a
    preview that accepted the preset's default and an execute that named
    that same mode explicitly describe one state rather than two.
    """

    document_type: str
    analysis_mode: str


@dataclass(frozen=True)
class DisclosureApplicationRequest:
    """The single input shape both ``preview`` and ``execute`` accept.

    ``document`` is set only by ``build_document_request`` (the structured
    upload path) and stays ``None`` for pasted text, ``.txt``/``.md`` files
    and prepared examples. It is what distinguishes a request that must
    carry a preview confirmation from one on the historical ``/disclosure/*``
    surface, which is unchanged by that mechanism.
    """

    content: NormalizedContent
    task: str
    strategy: DisclosureStrategy = DisclosureStrategy.RECOMMENDED
    governance: GovernanceOverrides = field(default_factory=GovernanceOverrides)
    document: DocumentRequestDescriptor | None = None


class DisclosureOutcome(StrEnum):
    """Stable, presentation-facing outcome codes. The UI maps these to
    localized copy; this layer never emits localized prose.
    """

    REMOVED = "removed"
    PSEUDONYMIZED = "pseudonymized"
    GENERALIZED = "generalized"
    PRESERVED = "preserved"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CategoryDisclosureSummary:
    """One detected category's disclosure outcome for the "what happens to
    my data" screen. Never carries a raw value or pseudonym -- only counts,
    flags and the treatment's own (non-sensitive) reasoning text.
    """

    category: str
    outcome: DisclosureOutcome
    action: DisclosureAction
    crosses_trust_boundary: bool
    occurrence_count: int
    required_for_task: bool | None
    technical_reason: str
    policy_version: str | None
    policy_restricted: bool | None
    impossible_under_policy: bool | None


@dataclass(frozen=True)
class DisclosureSummary:
    """The full "what happens to my data" picture for one request, shared
    verbatim between ``DisclosurePreview`` and ``DisclosureExecution`` --
    see ``summaries.build_disclosure_summary``.
    """

    status: Literal["allowed", "blocked"]
    categories: tuple[CategoryDisclosureSummary, ...]
    detected_span_count: int
    detected_categories: tuple[str, ...]


@dataclass(frozen=True)
class SafeGovernanceView:
    """A ``GovernanceContext`` projected down to what is safe to hand back
    to the same caller who supplied it: domain/purpose/policy_version/
    provider_class/requester_role/pseudonym scope only.

    Deliberately excludes ``requester_id`` and every lifecycle identifier
    (``session_id``/``document_id``/``request_id``): those identify a
    specific requester/session/document and partition the pseudonym vault,
    and have no presentational value to a "what happens to my data" screen
    -- see ``tests/test_application_contracts.py``'s dedicated pin that this
    type has no such field at all, not merely that it is left unset.
    """

    domain: str
    purpose: str
    policy_version: str
    provider_class: str
    requester_role: str | None
    requested_pseudonym_scope: PseudonymScope


def safe_governance_view(context: GovernanceContext) -> SafeGovernanceView:
    """Project a real ``GovernanceContext`` down to ``SafeGovernanceView``."""
    return SafeGovernanceView(
        domain=context.domain,
        purpose=context.purpose,
        policy_version=context.policy_version,
        provider_class=context.provider_class,
        requester_role=context.requester_role,
        requested_pseudonym_scope=context.requested_pseudonym_scope,
    )


@dataclass(frozen=True)
class ProviderMode:
    """Which provider *would* handle a previewed request, known without
    ever calling it -- just the provider's own declared ``provider_class``.
    Populated by ``preview``, which never invokes a provider at all (see
    ``service.py``).
    """

    provider_class: str


@dataclass(frozen=True)
class DisclosurePreview:
    """The "review before sending" result: everything about what would
    happen, plus the exact payload that would cross the trust boundary --
    without ever calling a provider.
    """

    summary: DisclosureSummary
    external_payload: str
    payload_byte_count: int
    treatment: Treatment
    strategy: DisclosureStrategy
    governance: SafeGovernanceView
    provider_mode: ProviderMode


@dataclass(frozen=True)
class DocumentDisclosurePreview:
    """A structured-document preview plus the server-signed proof of what
    was reviewed.

    A separate type rather than an optional field on ``DisclosurePreview``:
    the historical ``/disclosure/preview`` surface does not have (or need) a
    confirmation, and giving it a permanently-null ``confirmation_token``
    would change its contract for every existing caller to describe a
    mechanism that does not apply to it. See
    ``application/preview_confirmation.py``.
    """

    preview: DisclosurePreview
    confirmation_token: str


class UnsafeControlExecutionError(Exception):
    """Raised when an unsafe-control treatment (B0 -- Direct) is asked to
    execute an uploaded document against a provider outside the trust
    boundary.

    A product/demo-surface rule, not an experimental one. B0's experimental
    semantics are untouched and it stays fully visible in preview and in the
    B0-B4 comparison; what it must not do is send an advisor's untransformed
    document across the organizational boundary. This is the same stance
    ``compare_strategies`` already takes when it refuses to execute any
    comparison entry.

    Its message names the treatment class and the surface only -- never the
    document, the task or the payload.
    """


@dataclass(frozen=True)
class DisclosureExecution:
    """The real result of running a request all the way through the core:
    provider call, local reconstruction (if the treatment supports it), and
    the same disclosure summary ``preview`` would have shown for this input.
    """

    summary: DisclosureSummary
    final_answer: str | None
    provider: ProviderStage
    reconstruction: ReconstructionStage
    treatment: Treatment
    strategy: DisclosureStrategy
    governance: SafeGovernanceView
    total_ms: float


class ExportRefusedError(Exception):
    """Raised when ``DisclosureApplicationService.export`` is asked to
    export a request whose disclosure decision is not ``"allowed"`` (T26 /
    issue #67) -- a ``BLOCK_REQUEST`` outcome, or any other case where
    ``preview`` would not have produced a disclosed representation at all.

    Export exists to hand a caller the SAME disclosed representation
    ``preview`` already shows them, plus a restore handle for it -- there is
    nothing to export for a request that never produced one. Its message
    names the surface only, never the document, the task, or which category
    caused the block (that detail already exists, safely, on the ordinary
    preview response).
    """


@dataclass(frozen=True)
class DisclosureExport:
    """The result of ``DisclosureApplicationService.export`` (T26 / issue
    #67): the same disclosed representation ``preview``/``execute`` would
    show, plus a stateless, sealed restore handle for it.

    ``external_payload`` is exactly ``DisclosurePreview.external_payload``
    for the same input -- see that field's own docstring for why returning
    it is the product, not a leak. ``restore_handle`` is an opaque,
    self-contained envelope (see ``application/restore_handle.py``); this
    service never retains anything server-side to make it work later.
    ``restorable_count`` is the number of pseudonym entries the handle
    actually carries -- zero for B0 -- Direct and B1 -- Static Sanitization,
    which never pseudonymize anything, and for any category a treatment
    removed or generalized instead.
    """

    external_payload: str
    restore_handle: str
    expires_at: int
    restorable_count: int
    treatment: Treatment
    strategy: DisclosureStrategy
    governance: SafeGovernanceView


@dataclass(frozen=True)
class DisclosureRestore:
    """The result of ``DisclosureApplicationService.restore`` (T26 / issue
    #67): the submitted text with every pseudonym the handle recognizes
    replaced by its original, plus two counts -- never the mapping, and
    never an original for a pseudonym absent from the submitted text.

    ``unresolved_count`` is the number of pseudonym-shaped tokens present in
    the submitted text that this handle does NOT know about -- e.g. because
    they belong to a different document's export. They are left untouched in
    ``restored_text``, never reported individually.
    """

    restored_text: str
    restored_count: int
    unresolved_count: int


@dataclass(frozen=True)
class StrategyComparisonEntry:
    """One strategy's preview within a ``StrategyComparison`` -- see the
    module docstring's "Compare strategies" section.

    ``strategy`` is always an explicit ``b0``-``b4`` value, never
    ``DisclosureStrategy.RECOMMENDED``. ``recommended`` is ``True`` only for
    the one entry whose ``treatment`` is the treatment
    ``DisclosureStrategy.RECOMMENDED`` currently resolves to.
    ``unsafe_control_baseline`` is ``True`` only for the entry produced by a
    treatment implementing ``pipeline.UnsafeControlTreatment`` -- today only
    B0 -- Direct.
    """

    strategy: DisclosureStrategy
    treatment: Treatment
    recommended: bool
    unsafe_control_baseline: bool
    summary: DisclosureSummary
    external_payload: str
    payload_byte_count: int


@dataclass(frozen=True)
class StrategyComparison:
    """The full "compare strategies" result: one ``StrategyComparisonEntry``
    per B0-B4 strategy, in ``CANONICAL_COMPARISON_ORDER``, plus the
    governance view and provider mode shared identically by every entry
    (content/task/governance are byte-for-byte identical across entries by
    construction -- see ``service.compare_strategies``).
    """

    entries: tuple[StrategyComparisonEntry, ...]
    governance: SafeGovernanceView
    provider_mode: ProviderMode
