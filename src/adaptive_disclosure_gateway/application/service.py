"""The application/use-case boundary between a future adapter (HTTP/CLI/MCP
-- not part of this slice) and the existing disclosure-control core (T20 /
issue #28, slice 1).

``DisclosureApplicationService`` calls the real core -- ``pipeline.decide_disclosure``
for ``preview``, ``pipeline.run_disclosure_case`` for ``execute``, and
``pipeline.decide_disclosure`` + ``pipeline.execute_disclosure_decision`` for
the confirmed document flow -- and never reimplements detection, treatment
decisions, policy resolution, task analysis, pseudonymization,
generalization, reconstruction, provider invocation, audit construction or
the fail-closed task check.

Design decision -- where ``build_treatment`` lives: this service needs to
construct a treatment object from a resolved ``Treatment``, exactly like
``experiments.treatments.build_treatment`` (T10's runner) already does.
Importing that runner module directly from here would make a demo-facing
product service depend on the T10 experiment-runner package for no reason
other than convenience -- ``experiments`` is itself a *consumer* of the
core, not something other consumers of the core should depend on, and nothing
about building a treatment object is runner-specific logic. Writing a
second, parallel factory here was also ruled out: two independently
maintained ``Treatment -> class`` mappings are exactly the kind of drift
this ticket's "no duplicated logic" rule exists to prevent. So
``build_treatment`` was moved verbatim to the neutral
``adaptive_disclosure_gateway.treatment_factory`` module (see its own
docstring), which both this service and ``experiments.treatments`` (now a
thin re-export, kept for backward compatibility) import from.

Vault ownership: the service creates and holds one ``Vault`` for its own
lifetime (an ``InMemoryVault`` unless a caller supplies one) and never
exposes it. It is never constructed with
``capture_raw_values_for_controlled_experiment=True`` -- that flag is a T10
experiment-only escape hatch (see ``audit.py``'s module docstring) and has
no place in a product-facing service.

Lifecycle identifiers: like ``pipeline.run_disclosure_case`` itself, this
service never invents, defaults, or infers a pseudonym-scope lifecycle
identifier (``request_id``/``document_id``/``session_id``) on the caller's
behalf beyond what the deployer already configured on ``default_context``
at construction time. If a deployer wants a stable identifier across a demo
session, they set ``session_id`` on the ``default_context`` they pass into
the constructor; this service does not silently manufacture one, for the
same reason ``pipeline.py`` does not (a case blocked only because this
layer forgot to pass an identifier the caller/deployer did supply would be
a wiring artifact, not disclosure control).

``execute``'s summary is built from the decision ``run_disclosure_case``
itself made -- ``ExecutionResult.disclosure_result`` plus
``ExecutionResult.spans`` -- never from a second, standalone
``decide_disclosure`` call. This matters beyond saving work: the summary
this method returns is the user's answer to "what happened to my data", so
it must describe *the run that actually contacted the provider*, not a
parallel recomputation that is merely expected to have agreed with it. The
decision phase therefore runs exactly once per ``execute()`` call, pinned by
``tests/test_application_service.py::test_execute_runs_the_decision_phase_exactly_once``.
``preview`` calls ``decide_disclosure`` directly for the same reason in
reverse: it must run that phase and nothing after it.

``execute_document`` states the same property in its strongest form, because
the structured-document surface's whole guarantee depends on it: it computes
the decision **exactly once**, verifies the preview confirmation against that
exact decision, and hands that same ``DisclosureDecision`` to
``pipeline.execute_disclosure_decision``. The payload the token authenticates
and the payload the provider receives are therefore one object rather than
two objects expected to agree -- an expectation that would have rested on
``Detector``/``TaskAnalyzer``, both replaceable injections, happening to be
deterministic. See that method's own docstring and
``tests/test_application_document_presets.py``'s stateful-component tests.

``build_application_request``/``describe_health``/``list_strategies`` (T20 /
issue #28, slice 2): three small additions for the forthcoming HTTP adapter
under ``api/``, none of which touch ``preview``/``execute``'s own logic.

- ``build_application_request`` decides *which* of the three content
  sources (pasted text, an uploaded ``.txt``/``.md`` file, a prepared
  example) a caller supplied and resolves task/governance defaults for an
  example source. This is genuinely application logic -- not routing -- so
  it lives here rather than in ``api/``, which CLAUDE.md's "no domain logic
  in the HTTP layer" rule limits to parse/call/map. It is a method (not a
  free function in ``application/requests.py``, which holds only the pure,
  service-independent parts of this) specifically because it needs this
  service's own configured ``examples_directory``/``load_example`` -- a
  free function would just need those same two things threaded through as
  extra parameters at every call site, which is the same state this object
  already holds.
- ``describe_health``/``list_strategies`` exist so the HTTP adapter's
  ``GET /health``/``GET /strategies`` can stay a thin
  call-one-method-map-to-schema shell too, instead of either reaching into
  this service's private ``_provider`` attribute (breaking encapsulation)
  or reimplementing "is this a FakeProvider" / "which Treatment does each
  DisclosureStrategy resolve to" itself -- both of which are exactly the
  kind of interpretation-of-the-service's-own-configuration that CLAUDE.md's
  rule means to keep out of ``api/``. Both are read-only introspection:
  ``describe_health`` never calls ``self._provider.generate`` (see its own
  docstring), and ``list_strategies`` is a pure passthrough to
  ``contracts.list_strategy_options``.

``compare_strategies`` (T20 / issue #28's "Compare strategies" slice, issue
#29/#41): runs the SAME content through every B0-B4 strategy and reports
what each one would disclose. This is the "educational" surface, not an
evaluation one -- see ``application/contracts.py``'s module docstring for
the full no-oracle/no-scoring rationale.

It is PREVIEW-based and must NEVER call a provider, for any strategy:

- B0 -- Direct discloses the raw document unchanged (that is its whole
  point as an experimental control, see
  ``transformations/direct_disclosure.py``). *Executing* a comparison would
  send the caller's unprotected document to the external provider merely to
  illustrate a teaching point -- actively harmful once T22/#30 wires in a
  real provider.
- With ``FakeProvider``, the responses carry no task utility at all, so
  executing adds nothing today and only creates that risk tomorrow.
- Showing exactly what each strategy *would* send is the entire pedagogical
  content of the comparison.

An execute-based/utility-aware comparison is explicitly deferred, and would
require both T22 and a deliberate decision about whether B0 may ever run
against a real provider on user content.

``compare_strategies`` calls ``self.preview`` once per treatment, in
``contracts.CANONICAL_COMPARISON_ORDER`` (CLAUDE.md's canonical sequence,
B0 -> B1 -> B2 -> B3 -> B4) -- never enum-definition order by accident, and
never a different order per call. Each per-strategy request is built from
the incoming one with ``dataclasses.replace(request, strategy=<treatment>)``
so content/task/governance are byte-for-byte identical across entries --
that identity is the entire point of a comparison. This reuses ``preview``
rather than reimplementing or inlining the decision phase: the comparison
IS n previews.

All entries share this service's one vault (``self._vault``, see the
vault-ownership note above), so a pseudonym for the same original is
identical across the B2/B3/B4 entries. That is correct and desirable: it is
the same vault every other call on this service instance shares, and a
comparison run is not a special case.

``StrategyComparisonEntry.unsafe_control_baseline`` is read from the
existing ``pipeline.UnsafeControlTreatment`` capability marker via
``isinstance`` -- exactly how ``pipeline.run_disclosure_case`` itself
checks it -- never a hardcoded ``treatment is Treatment.DIRECT`` comparison.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from pathlib import Path

from adaptive_disclosure_gateway.application.contracts import (
    CANONICAL_COMPARISON_ORDER,
    DisclosureApplicationRequest,
    DisclosureExecution,
    DisclosureExport,
    DisclosurePreview,
    DisclosureRestore,
    DisclosureStrategy,
    DocumentDisclosurePreview,
    DocumentRequestDescriptor,
    ExportRefusedError,
    GovernanceOverrides,
    ProviderMode,
    StrategyComparison,
    StrategyComparisonEntry,
    StrategyOption,
    UnsafeControlExecutionError,
    list_strategy_options,
    resolve_treatment,
    safe_governance_view,
)
from adaptive_disclosure_gateway.application.examples import (
    ExampleSummary,
    list_examples,
    load_example,
)
from adaptive_disclosure_gateway.application.ingestion import (
    DocumentParser,
    normalize_text,
    normalize_text_file,
)
from adaptive_disclosure_gateway.application.presets import (
    resolve_analysis_mode,
    resolve_governance_preset,
)
from adaptive_disclosure_gateway.application.preview_confirmation import (
    REASON_CONFIRMATION_SECRET_NOT_DURABLE,
    PreviewConfirmationError,
    PreviewConfirmationSigner,
    PreviewConfirmationState,
)
from adaptive_disclosure_gateway.application.requests import (
    ContentSourceError,
    MissingTaskError,
    apply_example_governance_defaults,
)
from adaptive_disclosure_gateway.application.restore_handle import (
    RestoreHandleSealer,
    restore_pseudonyms,
)
from adaptive_disclosure_gateway.application.summaries import build_disclosure_summary
from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
    Treatment,
)
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer
from adaptive_disclosure_gateway.pipeline import (
    DisclosureDecision,
    ExecutionResult,
    UnsafeControlTreatment,
    decide_disclosure,
    execute_disclosure_decision,
    run_disclosure_case,
)
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import DEFAULT_PROVIDER_NAME, FakeProvider, Provider
from adaptive_disclosure_gateway.providers.readiness import provider_readiness
from adaptive_disclosure_gateway.task_analysis import TaskAnalyzer
from adaptive_disclosure_gateway.treatment_factory import build_treatment
from adaptive_disclosure_gateway.vault import InMemoryVault, Vault

# Every GovernanceOverrides field, in the order GovernanceContext declares
# them, used to build the model_copy(update=...) mapping below with only
# the fields the caller actually set (non-None) included.
_OVERRIDE_FIELDS = (
    "purpose",
    "requester_role",
    "requester_id",
    "provider_class",
    "policy_version",
    "requested_pseudonym_scope",
    "session_id",
    "document_id",
    "request_id",
    "domain",
)


def _merge_overrides(
    default_context: GovernanceContext, overrides: GovernanceOverrides
) -> GovernanceContext:
    """Merge ``overrides`` onto ``default_context``, ignoring every ``None``
    field on ``overrides`` -- a novice caller supplying no overrides gets
    ``default_context`` back unchanged.
    """
    updates = {
        field_name: value
        for field_name in _OVERRIDE_FIELDS
        if (value := getattr(overrides, field_name)) is not None
    }
    return default_context.model_copy(update=updates)


@dataclass(frozen=True)
class ServiceHealth:
    """Read-only provider/treatment introspection for the HTTP adapter's
    ``GET /health`` (T20 / issue #28, slice 2). ``describe_health`` builds
    this from attributes only -- it never calls ``Provider.generate``.

    ``model_id``/``model_snapshot`` are read via ``getattr`` with a
    ``None`` fallback: ``Provider`` (``providers/base.py``) only requires
    ``provider_class`` and ``generate`` -- ``model_id``/``model_snapshot``
    are ``FakeProvider``'s own class attributes, not part of the protocol,
    so a hypothetical provider that only exposes them on
    ``ProviderResponse`` (i.e. only after a real call) reports ``None``
    here rather than this raising.
    """

    provider_class: str
    model_id: str | None
    model_snapshot: str | None
    deterministic_demo_mode: bool
    treatments_available: tuple[Treatment, ...]


@dataclass(frozen=True)
class ServiceReadiness:
    """Purely local readiness for ``GET /ready`` (T25 review finding 2):
    built with no network access, no provider ``generate()`` call and no SDK
    client construction -- see ``describe_readiness``'s own docstring and
    ``providers.readiness.provider_readiness``'s for what "purely local"
    excludes.

    ``reason`` is populated only when ``ready`` is ``False`` and is always
    one of the closed-vocabulary codes ``application.wire.ReadinessReason``
    validates against -- never free text, a credential, an environment
    variable's value or any other config detail.
    """

    ready: bool
    reason: str | None = None


class DisclosureApplicationService:
    """The use-case boundary: builds a treatment via the existing
    ``treatment_factory.build_treatment``, then calls
    ``pipeline.decide_disclosure``/``pipeline.run_disclosure_case`` -- never
    anything else -- to answer ``preview``/``execute``.
    """

    def __init__(
        self,
        *,
        policy_repository: PolicyRepository,
        provider: Provider,
        vault: Vault | None = None,
        task_analyzer: TaskAnalyzer | None = None,
        detector: Detector | None = None,
        default_context: GovernanceContext,
        examples_directory: str | Path | None = None,
        document_parser: DocumentParser | None = None,
        preview_confirmation_signer: PreviewConfirmationSigner | None = None,
        restore_handle_sealer: RestoreHandleSealer | None = None,
    ) -> None:
        self._policy_repository = policy_repository
        self._provider = provider
        # Created once, held for this service's lifetime, and never
        # exposed: see the module docstring's vault-ownership note.
        self._vault: Vault = vault if vault is not None else InMemoryVault()
        self._task_analyzer = task_analyzer
        self._detector = detector
        self._default_context = default_context
        self._examples_directory = examples_directory
        # The T12 ingestion parser adapter, injectable so the boundary stays
        # replaceable (issue #9) and so the offline test suite can exercise
        # the whole upload path without Docling's cached model artifacts.
        # ``None`` means "let ingestion load its default Docling adapter
        # lazily, only if a document format actually needs it".
        self._document_parser = document_parser
        # Held for this service's lifetime and never exposed, exactly like
        # the vault above. ``None`` does NOT mean "no confirmation": it
        # means per-process key material (see
        # ``PreviewConfirmationSigner.with_ephemeral_secret``), so a service
        # constructed without configuration still refuses an execute that
        # no preview authorised. There is deliberately no way to build this
        # service with confirmation disabled -- a deployment that must have
        # a *durable* secret is refused at construction in
        # ``application/settings.build_default_service``, not here.
        self._preview_confirmation_signer = (
            preview_confirmation_signer
            if preview_confirmation_signer is not None
            else PreviewConfirmationSigner.with_ephemeral_secret()
        )
        # T26 / issue #67. Unlike the preview-confirmation signer above,
        # there is no ephemeral-key fallback here: a restore handle is
        # meant to outlive this process, so a per-process key would
        # silently defeat the whole feature (see
        # ``application/restore_handle.py``'s module docstring). ``None``
        # here means "no secret configured" -- the sealer itself still
        # constructs (so a service with no restore-handle secret still
        # starts and serves every other route), and only fails, closed, the
        # moment ``export``/``restore`` are actually called.
        self._restore_handle_sealer = (
            restore_handle_sealer
            if restore_handle_sealer is not None
            else RestoreHandleSealer(secret=None)
        )

    def _build_treatment(self, request: DisclosureApplicationRequest):
        treatment_code = resolve_treatment(request.strategy)
        treatment = build_treatment(
            treatment_code,
            vault=self._vault,
            policy_repository=self._policy_repository,
            task_analyzer=self._task_analyzer,
        )
        return treatment_code, treatment

    def _build_disclosure_request(
        self, request: DisclosureApplicationRequest
    ) -> tuple[DisclosureRequest, GovernanceContext]:
        context = _merge_overrides(self._default_context, request.governance)
        return (
            DisclosureRequest(text=request.content.text, task=request.task, context=context),
            context,
        )

    def preview(self, request: DisclosureApplicationRequest) -> DisclosurePreview:
        """Run only the decision phase (detect -> sanitize -> fail-closed
        task check) -- no provider call, no reconstruction. Exactly the
        "review before sending" screen's data.
        """
        tracer = get_tracer()
        started = time.perf_counter()
        with tracer.start_as_current_span("application.preview") as span:
            treatment_code, treatment = self._build_treatment(request)
            disclosure_request, context = self._build_disclosure_request(request)

            decision = decide_disclosure(treatment, disclosure_request, detector=self._detector)
            preview = self._preview_of(
                request, treatment_code=treatment_code, context=context, decision=decision
            )

            # Metadata only -- status, treatment code, counts, category
            # names (safe, non-sensitive -- already used the same way by
            # detection.detect/<treatment>.sanitize's own spans) and timing.
            span.set_attribute("application.status", decision.result.status)
            span.set_attribute("application.treatment", treatment_code.value)
            span.set_attribute("application.detected_span_count", len(decision.spans))
            span.set_attribute(
                "application.detected_categories", list(preview.summary.detected_categories)
            )
            span.set_attribute("application.duration_ms", elapsed_ms_since(started))

            return preview

    def _preview_of(
        self,
        request: DisclosureApplicationRequest,
        *,
        treatment_code: Treatment,
        context: GovernanceContext,
        decision: DisclosureDecision,
    ) -> DisclosurePreview:
        """The "review before sending" view of one ``DisclosureDecision``.

        Pure projection of a decision that was already made -- it runs no
        part of the decision phase itself. That is what lets
        ``execute_document`` build the state a confirmation authenticates
        from the very decision it is about to execute, instead of computing
        a second one (see that method's docstring).
        """
        return DisclosurePreview(
            summary=build_disclosure_summary(decision),
            external_payload=decision.result.external_payload,
            payload_byte_count=len(decision.result.external_payload.encode("utf-8")),
            treatment=treatment_code,
            strategy=request.strategy,
            governance=safe_governance_view(context),
            provider_mode=ProviderMode(provider_class=self._provider.provider_class),
        )

    def execute(self, request: DisclosureApplicationRequest) -> DisclosureExecution:
        """Run the request all the way through the real, unchanged
        ``pipeline.run_disclosure_case`` -- provider call and, if the
        treatment supports it, local reconstruction included.

        See the module docstring for why the summary is built from a
        standalone ``decide_disclosure`` call rather than from
        ``run_disclosure_case``'s own internal one.

        A request from the structured-document surface is refused here. That
        surface's whole guarantee is that what reaches the provider is what
        a reviewer approved, and this method has no confirmation to check
        against -- so the guard is structural rather than a convention the
        HTTP layer is trusted to follow: ``execute_document`` is the only
        way to execute an uploaded document, and a future adapter cannot
        reach the provider with one by calling the more obvious method.
        """
        if request.document is not None:
            raise PreviewConfirmationError(
                "a request from the structured-document surface is executed only through "
                "execute_document, which verifies the confirmation issued by its preview"
            )
        return self._execute(request)

    def _execute(self, request: DisclosureApplicationRequest) -> DisclosureExecution:
        tracer = get_tracer()
        started = time.perf_counter()
        with tracer.start_as_current_span("application.execute") as span:
            treatment_code, treatment = self._build_treatment(request)
            disclosure_request, context = self._build_disclosure_request(request)

            execution_result = run_disclosure_case(
                treatment, disclosure_request, self._provider, detector=self._detector
            )
            return self._execution_of(
                request,
                treatment_code=treatment_code,
                context=context,
                execution_result=execution_result,
                span=span,
                started=started,
            )

    def _execution_of(
        self,
        request: DisclosureApplicationRequest,
        *,
        treatment_code: Treatment,
        context: GovernanceContext,
        execution_result: ExecutionResult,
        span,
        started: float,
    ) -> DisclosureExecution:
        """The client-facing view of one ``pipeline.ExecutionResult``, plus
        the ``application.execute`` span's metadata.

        Every field is read off the ``ExecutionResult`` of the run that
        actually contacted the provider -- summary, final answer, provider
        record and reconstruction record all describe that one run, never a
        parallel recomputation merely expected to have agreed with it. Both
        execute paths (``execute`` and ``execute_document``) share this, so
        there is one definition of what a ``DisclosureExecution`` reports.
        """
        # The decision the execution stage was handed -- never a second,
        # standalone decide_disclosure call. See the module docstring.
        decision = DisclosureDecision(
            spans=execution_result.spans, result=execution_result.disclosure_result
        )
        summary = build_disclosure_summary(decision)

        provider_response = execution_result.provider_response
        final_answer: str | None = None
        if provider_response is not None:
            final_answer = (
                execution_result.reconstructed_text
                if execution_result.reconstructed_text is not None
                else provider_response.text
            )

        total_ms = elapsed_ms_since(started)

        span.set_attribute("application.status", execution_result.disclosure_result.status)
        span.set_attribute("application.treatment", treatment_code.value)
        span.set_attribute("application.detected_span_count", len(decision.spans))
        span.set_attribute("application.detected_categories", list(summary.detected_categories))
        span.set_attribute("application.provider_called", execution_result.audit.provider.called)
        span.set_attribute("application.provider_failed", execution_result.audit.provider.failed)
        span.set_attribute(
            "application.reconstruction_attempted",
            execution_result.audit.reconstruction.attempted,
        )
        span.set_attribute("application.duration_ms", total_ms)

        return DisclosureExecution(
            summary=summary,
            final_answer=final_answer,
            provider=execution_result.audit.provider,
            reconstruction=execution_result.audit.reconstruction,
            treatment=treatment_code,
            strategy=request.strategy,
            governance=safe_governance_view(context),
            total_ms=total_ms,
        )

    def export(self, request: DisclosureApplicationRequest) -> DisclosureExport:
        """Export the disclosed representation of ``request`` together with
        a sealed restore handle for it (T26 / issue #67).

        Runs the SAME decision phase ``preview`` runs -- exactly once, never
        calling the provider -- and refuses (``ExportRefusedError``) unless
        the decision is ``"allowed"``: a ``BLOCK_REQUEST`` outcome has no
        disclosed representation to export at all.

        The ``(pseudonym -> original)`` entries sealed into the handle come
        directly from ``decision.result.transformations`` -- the same
        ``DisclosureResult`` field ``decision_application.reconstruct``
        already reads for local reconstruction -- filtered to
        ``DisclosureAction.PSEUDONYMIZE``. This needs no vault call and no
        new ``Vault`` method: every transformation the decision itself
        produced already carries both the pseudonym it emitted and the
        original it stands for, so there is nothing extra to look up.
        Categories the treatment removed or generalized never appear here,
        which is what gives B1 -- Static Sanitization (and any REMOVE/
        GENERALIZE category under any treatment) zero restorable entries.
        B0 -- Direct never pseudonymizes anything either, so it also always
        has zero -- with no special-casing needed for either.

        Raises ``RestoreUnavailableError`` (via the sealer) if no restore
        handle secret is configured -- export fails closed exactly like
        restore, never silently succeeding with an unusable handle.
        """
        tracer = get_tracer()
        started = time.perf_counter()
        with tracer.start_as_current_span("application.export") as span:
            treatment_code, treatment = self._build_treatment(request)
            disclosure_request, context = self._build_disclosure_request(request)

            decision = decide_disclosure(treatment, disclosure_request, detector=self._detector)
            span.set_attribute("application.status", decision.result.status)
            span.set_attribute("application.treatment", treatment_code.value)

            if decision.result.status != "allowed":
                raise ExportRefusedError(
                    "export is available only for a disclosure decision that was allowed; "
                    "this request's decision was blocked"
                )

            preview = self._preview_of(
                request, treatment_code=treatment_code, context=context, decision=decision
            )
            entries = {
                transformation.transformed: transformation.original
                for transformation in decision.result.transformations
                if transformation.action is DisclosureAction.PSEUDONYMIZE
                and transformation.transformed is not None
            }
            issued = self._restore_handle_sealer.issue(entries)

            span.set_attribute("application.restorable_count", len(entries))
            span.set_attribute("application.duration_ms", elapsed_ms_since(started))

            return DisclosureExport(
                external_payload=preview.external_payload,
                restore_handle=issued.handle,
                expires_at=issued.expires_at,
                restorable_count=len(entries),
                treatment=treatment_code,
                strategy=request.strategy,
                governance=preview.governance,
            )

    def restore(self, *, text: str, restore_handle: str) -> DisclosureRestore:
        """Replace, in ``text``, only the pseudonyms that ``restore_handle``
        recognizes (T26 / issue #67).

        Stateless: nothing about this call depends on this service's own
        vault or on any prior request -- the handle alone carries what is
        needed, which is what lets a handle survive a restart or land on a
        different worker. Pseudonym-shaped tokens in ``text`` that the
        handle does NOT recognize (a different document's export, or a
        tampered/foreign token) are left untouched and counted only, never
        echoed. Raises ``RestoreUnavailableError`` if no secret is
        configured, or one of ``RestoreHandleError``'s subclasses if the
        handle itself is invalid or expired -- both fail closed, nothing
        reconstructed.
        """
        tracer = get_tracer()
        with tracer.start_as_current_span("application.restore"):
            mapping = self._restore_handle_sealer.open(restore_handle)
            restored_text, restored_count, unresolved_count = restore_pseudonyms(text, mapping)
            return DisclosureRestore(
                restored_text=restored_text,
                restored_count=restored_count,
                unresolved_count=unresolved_count,
            )

    def compare_strategies(self, request: DisclosureApplicationRequest) -> StrategyComparison:
        """Run ``request`` through every B0-B4 strategy via ``preview`` --
        never the provider -- in ``CANONICAL_COMPARISON_ORDER``. See the
        module docstring for the full design rationale.
        """
        recommended_treatment = resolve_treatment(DisclosureStrategy.RECOMMENDED)
        # request.strategy plays no role in _build_disclosure_request (it
        # only reads content/task/governance), so this single call already
        # produces the governance view/provider mode identical to what every
        # per-strategy preview() below computes for itself.
        _, context = self._build_disclosure_request(request)
        governance = safe_governance_view(context)
        provider_mode = ProviderMode(provider_class=self._provider.provider_class)

        entries = []
        for strategy in CANONICAL_COMPARISON_ORDER:
            per_strategy_request = dataclasses.replace(request, strategy=strategy)
            preview = self.preview(per_strategy_request)
            # Built only for its capability marker (unsafe_control_baseline
            # below) -- never used to reimplement any part of the decision
            # phase, which preview() above already ran in full.
            _, treatment = self._build_treatment(per_strategy_request)
            entries.append(
                StrategyComparisonEntry(
                    strategy=strategy,
                    treatment=preview.treatment,
                    recommended=preview.treatment == recommended_treatment,
                    unsafe_control_baseline=isinstance(treatment, UnsafeControlTreatment),
                    summary=preview.summary,
                    external_payload=preview.external_payload,
                    payload_byte_count=preview.payload_byte_count,
                )
            )

        return StrategyComparison(
            entries=tuple(entries), governance=governance, provider_mode=provider_mode
        )

    def list_examples(self) -> tuple[ExampleSummary, ...]:
        """Convenience passthrough to ``examples.list_examples`` bound to
        this service's configured ``examples_directory``. Raises
        ``ValueError`` if the service was not configured with one.
        """
        if self._examples_directory is None:
            raise ValueError("no examples_directory configured for this service")
        return list_examples(self._examples_directory)

    def load_example(self, example_id: str) -> CorpusCaseInput:
        """Convenience passthrough to ``examples.load_example`` bound to
        this service's configured ``examples_directory``.
        """
        if self._examples_directory is None:
            raise ValueError("no examples_directory configured for this service")
        return load_example(self._examples_directory, example_id)

    def describe_health(self) -> ServiceHealth:
        """Read-only provider/treatment introspection for ``GET /health``.
        Reads only attributes already on ``self._provider`` -- never calls
        ``self._provider.generate``. See ``ServiceHealth``'s own docstring.
        """
        return ServiceHealth(
            provider_class=self._provider.provider_class,
            model_id=getattr(self._provider, "model_id", None),
            model_snapshot=getattr(self._provider, "model_snapshot", None),
            deterministic_demo_mode=isinstance(self._provider, FakeProvider),
            treatments_available=tuple(Treatment),
        )

    def describe_readiness(self) -> ServiceReadiness:
        """Purely local readiness for ``GET /ready`` (T25 review finding 2):
        no network call, no provider ``generate()``, no SDK client
        construction -- a stricter contract than ``describe_health`` above,
        which is also call-free but exists for richer introspection instead
        of gating a container healthcheck.

        Delegates the provider-shaped half of the check to
        ``providers.readiness.provider_readiness`` (obeying
        ``tests/test_provider_isolation.py``'s one-way import wall -- this
        service calls into ``providers/``, never the reverse) and adds the
        one check that belongs at this layer: a service wired to a provider
        outside the trust boundary (``FakeProvider`` excepted) needs a
        *durable* preview-confirmation signer. This mirrors the same
        distinction ``application.settings.build_preview_confirmation_signer``
        already fails closed on at startup -- an ephemeral, per-process
        signer surviving to runtime here would mean a load-balanced or
        restarted deployment could report ``/ready`` while a document
        preview issued by one worker/process could never be confirmed by
        another.
        """
        ready, reason = provider_readiness(self._provider)
        if not ready:
            return ServiceReadiness(ready=False, reason=reason)
        if (
            self._provider.provider_class != DEFAULT_PROVIDER_NAME
            and not self._preview_confirmation_signer.is_durable
        ):
            return ServiceReadiness(ready=False, reason=REASON_CONFIRMATION_SECRET_NOT_DURABLE)
        return ServiceReadiness(ready=True)

    def list_strategies(self) -> tuple[StrategyOption, ...]:
        """Convenience passthrough to ``contracts.list_strategy_options`` for
        ``GET /strategies``. Pure data -- see ``StrategyOption``'s docstring.
        """
        return list_strategy_options()

    def build_application_request(
        self,
        *,
        text: str | None = None,
        filename: str | None = None,
        file_bytes: bytes | None = None,
        example_id: str | None = None,
        task: str | None = None,
        strategy: DisclosureStrategy = DisclosureStrategy.RECOMMENDED,
        governance: GovernanceOverrides | None = None,
    ) -> DisclosureApplicationRequest:
        """Build a ``DisclosureApplicationRequest`` from whichever single
        content source the caller supplied -- see the module docstring for
        why this is a method rather than a free function.

        Exactly one of ``text``, (``filename`` and ``file_bytes`` together),
        or ``example_id`` must be supplied; any other count raises
        ``ContentSourceError`` naming which source *slots* were supplied,
        never their content (CLAUDE.md's no-leak invariant).

        A missing ``task`` for a non-example source raises
        ``MissingTaskError``. For an example source, an explicit ``task``
        wins over the example's own; otherwise the example's task is used.
        Likewise, the example's own domain/purpose/policy_version/
        requester_role/provider_class/requested_pseudonym_scope apply as
        defaults *under* any explicit ``governance`` override -- see
        ``requests.apply_example_governance_defaults``.

        Never touches the oracle: the only corpus access here is
        ``self.load_example``, which returns ``CorpusCaseInput`` (the input
        half) only.
        """
        overrides = governance if governance is not None else GovernanceOverrides()

        supplied_sources = []
        if text is not None:
            supplied_sources.append("text")
        if filename is not None or file_bytes is not None:
            supplied_sources.append("file")
        if example_id is not None:
            supplied_sources.append("example_id")

        if len(supplied_sources) != 1:
            raise ContentSourceError(
                "expected exactly one content source (text, file, example_id); "
                f"received {len(supplied_sources)}: {supplied_sources}"
            )

        source = supplied_sources[0]

        if source == "text":
            content = normalize_text(text)
            if task is None:
                raise MissingTaskError("no task supplied for a direct text content source")
            return DisclosureApplicationRequest(
                content=content, task=task, strategy=strategy, governance=overrides
            )

        if source == "file":
            if filename is None or file_bytes is None:
                raise ContentSourceError(
                    "the file content source requires both filename and file_bytes"
                )
            content = normalize_text_file(
                filename, file_bytes, document_parser=self._document_parser
            )
            if task is None:
                raise MissingTaskError("no task supplied for a file content source")
            return DisclosureApplicationRequest(
                content=content, task=task, strategy=strategy, governance=overrides
            )

        # source == "example_id"
        example = self.load_example(example_id)
        content = normalize_text(example.text)
        resolved_task = task if task is not None else example.task
        resolved_overrides = apply_example_governance_defaults(example, overrides)
        return DisclosureApplicationRequest(
            content=content, task=resolved_task, strategy=strategy, governance=resolved_overrides
        )

    def build_document_request(
        self,
        *,
        filename: str,
        file_bytes: bytes,
        task: str,
        document_type: str,
        analysis_mode: str | None = None,
        strategy: DisclosureStrategy = DisclosureStrategy.RECOMMENDED,
    ) -> DisclosureApplicationRequest:
        """Build a request for an uploaded structured document under an
        explicit, server-validated governance preset (T20 / issue #28's
        demo-integration slice; issue #41 gate A).

        This is the only entry point an upload adapter uses. It differs from
        ``build_application_request`` in exactly one way, and that difference
        is the point: governance is not a set of caller-supplied strings, it
        is resolved from ``(document_type, analysis_mode)`` by
        ``application/presets.py``'s server-owned allowlist. There is no
        ``governance`` parameter here on purpose -- an upload adapter must
        not be able to pass a ``domain``/``policy_version``/``purpose`` of
        its own choosing, and ``document_type`` is required, so an uploaded
        contract can never fall through to the deployer's HR default
        (issue #41's blocker 4).

        Normalization is delegated unchanged to ``build_application_request``
        -> ``ingestion.normalize_text_file`` -> the T12 parser adapter. No
        parsing, format detection or document logic is duplicated here, and
        the caller's declared media type is deliberately NOT accepted: the
        filename extension is the single authoritative dispatch key at the
        T12 boundary (``ingestion._extension``), and letting a client-declared
        MIME type influence parser selection would hand the client a
        dispatch decision. An extension the boundary does not support fails
        closed there with ``IngestionError``.
        """
        overrides = resolve_governance_preset(document_type, analysis_mode=analysis_mode)
        request = self.build_application_request(
            filename=filename,
            file_bytes=file_bytes,
            task=task,
            strategy=strategy,
            governance=overrides,
        )
        # Records that this request came from the structured-document
        # surface, and under which caller-facing selection. That is what
        # makes ``preview_document``/``execute_document`` applicable to it,
        # and what the preview-confirmation fingerprint binds.
        return dataclasses.replace(
            request,
            document=DocumentRequestDescriptor(
                document_type=document_type,
                analysis_mode=resolve_analysis_mode(document_type, analysis_mode=analysis_mode),
            ),
        )

    # --- the confirmed structured-document flow ------------------------------
    #
    # ``preview_document`` -> the reviewer reads the disclosure review ->
    # ``execute_document`` with that preview's own token.
    #
    # These wrap ``preview``/``execute`` rather than reimplementing either:
    # what they add is the binding between the two calls. See
    # ``application/preview_confirmation.py`` for the mechanism and for the
    # defect it closes.

    def _confirmation_state(
        self, request: DisclosureApplicationRequest, preview: DisclosurePreview
    ) -> PreviewConfirmationState:
        """The exact state an approval is an approval of.

        Every field is read from the request being handled and from the
        preview just computed for it -- never from a token. That is what
        makes ``execute_document`` a re-computation rather than a decoding:
        a client cannot assert its own state, only present a proof that the
        server once computed the identical one.
        """
        document = request.document
        if document is None:
            # Not reachable through ``build_document_request``; a guard so a
            # future caller cannot obtain a confirmation for a request that
            # carries no document selection to bind.
            raise PreviewConfirmationError(
                "preview confirmation applies to the structured-document surface only"
            )
        governance = preview.governance
        return PreviewConfirmationState(
            normalized_document=request.content.text,
            task=request.task,
            document_type=document.document_type,
            analysis_mode=document.analysis_mode,
            domain=governance.domain,
            policy_version=governance.policy_version,
            purpose=governance.purpose,
            requester_role=governance.requester_role,
            requested_pseudonym_scope=governance.requested_pseudonym_scope.value,
            # Both provider classes are bound: the one the governance
            # context *declares* (which policy itself reads) and the one the
            # wired provider actually *is*. They can legitimately differ,
            # and a change to either changes where the payload would go.
            governance_provider_class=governance.provider_class,
            provider_class=preview.provider_mode.provider_class,
            strategy=preview.strategy.value,
            treatment=preview.treatment.value,
            external_payload=preview.external_payload,
        )

    def preview_document(self, request: DisclosureApplicationRequest) -> DocumentDisclosurePreview:
        """``preview``, plus the server-signed proof of what was shown.

        Nothing about the review itself changes -- this still never reaches
        the provider. The token is what lets a later ``execute_document``
        establish that it is executing this very state and not another.
        """
        preview = self.preview(request)
        return DocumentDisclosurePreview(
            preview=preview,
            confirmation_token=self._preview_confirmation_signer.issue(
                self._confirmation_state(request, preview)
            ),
        )

    def execute_document(
        self, request: DisclosureApplicationRequest, *, confirmation_token: str
    ) -> DisclosureExecution:
        """Execute an uploaded document only if this exact request is the
        preview a reviewer approved -- and execute *that* decision.

        The decision phase over the document runs **exactly once** here. The
        one ``DisclosureDecision`` it produces is projected into the approved
        state, the confirmation is verified against that state, and the very
        same object is then handed to
        ``pipeline.execute_disclosure_decision``. So the payload the token
        authenticates and the payload the provider receives are one object,
        not two objects expected to agree.

        That distinction is the whole point of this method, and it was the
        second review finding on this slice. Verifying one decision and then
        asking ``run_disclosure_case`` to compute another left the demo's
        central guarantee resting on ``Detector``/``TaskAnalyzer`` happening
        to be deterministic -- both are replaceable injections, so a
        stateful, non-deterministic or simply buggy one would have made the
        reviewer approve one payload while the provider received a different
        one (pinned by
        ``tests/test_application_document_presets.py::test_execute_document_sends_the_exact_decision_authenticated_by_the_preview_confirmation``).

        Order matters. The confirmation is verified first, so the
        unsafe-control refusal below cannot be reached by an execute that no
        preview authorised, and so that refusal is provably a rule of its
        own rather than the confirmation check under another name.

        Span topology note: this path decides *outside* any
        ``pipeline.run_disclosure_case`` span -- it has none, because it
        never calls ``run_disclosure_case`` -- so ``detection.detect`` /
        ``<treatment>.sanitize`` / ``<treatment>.reconstruct`` are children
        of this method's ``application.execute`` span instead. The T10
        scientific runner is untouched by that: it calls
        ``run_disclosure_case`` directly and keeps the exact topology
        ``experiments/stage_timing.py`` reads.
        """
        tracer = get_tracer()
        started = time.perf_counter()
        with tracer.start_as_current_span("application.execute") as span:
            treatment_code, treatment = self._build_treatment(request)
            disclosure_request, context = self._build_disclosure_request(request)

            decision = decide_disclosure(treatment, disclosure_request, detector=self._detector)
            approved = self._preview_of(
                request, treatment_code=treatment_code, context=context, decision=decision
            )

            self._preview_confirmation_signer.verify(
                confirmation_token, self._confirmation_state(request, approved)
            )
            self._refuse_unsafe_control_outside_the_trust_boundary(treatment)

            execution_result = execute_disclosure_decision(
                treatment, disclosure_request, self._provider, decision=decision
            )
            return self._execution_of(
                request,
                treatment_code=treatment_code,
                context=context,
                execution_result=execution_result,
                span=span,
                started=started,
            )

    def _refuse_unsafe_control_outside_the_trust_boundary(self, treatment) -> None:
        """B0 -- Direct discloses the document unchanged. On the advisor
        demo's document surface it may be previewed and compared, never
        executed against a provider outside the trust boundary.

        Read from the existing ``pipeline.UnsafeControlTreatment`` capability
        marker -- exactly how ``run_disclosure_case`` and
        ``compare_strategies`` already check it -- rather than a hardcoded
        ``Treatment.DIRECT`` comparison, so a future treatment carrying the
        same marker inherits the rule.

        "Outside the trust boundary" is read from the provider's own
        declared ``provider_class`` -- the same field policy itself reads,
        and the same one ``invoke_provider`` checks against the governance
        context -- rather than from its concrete Python class. Only the
        deterministic in-process class (``providers.DEFAULT_PROVIDER_NAME``)
        is exempt, because nothing leaves the process for it and the
        confirmation flow still applies to it in full. Anything else,
        including a class this codebase does not recognize, is refused: the
        check fails closed on an unknown provider class rather than
        enumerating the ones known to be external.

        This changes no experimental semantics -- B0 itself is unchanged, it
        stays available in preview and comparison, and the T10 runner builds
        its own treatments and never goes through this service.

        Takes the treatment object the caller already built, rather than
        rebuilding one from the request: the rule must be applied to the
        very treatment that is about to be executed.
        """
        if (
            isinstance(treatment, UnsafeControlTreatment)
            and self._provider.provider_class != DEFAULT_PROVIDER_NAME
        ):
            raise UnsafeControlExecutionError(
                "the direct/unsafe-control treatment is available for preview and strategy "
                "comparison only; it is never executed against a provider outside the trust "
                "boundary through the document surface"
            )
