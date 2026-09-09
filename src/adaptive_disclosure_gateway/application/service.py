"""The application/use-case boundary between a future adapter (HTTP/CLI/MCP
-- not part of this slice) and the existing disclosure-control core (T20 /
issue #28, slice 1).

``DisclosureApplicationService`` calls the real core -- ``pipeline.decide_disclosure``
for ``preview``, ``pipeline.run_disclosure_case`` for ``execute`` -- and
never reimplements detection, treatment decisions, policy resolution, task
analysis, pseudonymization, generalization, reconstruction or the
fail-closed task check.

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
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from adaptive_disclosure_gateway.application.contracts import (
    DisclosureApplicationRequest,
    DisclosureExecution,
    DisclosurePreview,
    DisclosureStrategy,
    GovernanceOverrides,
    ProviderMode,
    StrategyOption,
    list_strategy_options,
    resolve_treatment,
    safe_governance_view,
)
from adaptive_disclosure_gateway.application.examples import (
    ExampleSummary,
    list_examples,
    load_example,
)
from adaptive_disclosure_gateway.application.ingestion import normalize_text, normalize_text_file
from adaptive_disclosure_gateway.application.requests import (
    ContentSourceError,
    MissingTaskError,
    apply_example_governance_defaults,
)
from adaptive_disclosure_gateway.application.summaries import build_disclosure_summary
from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext, Treatment
from adaptive_disclosure_gateway.observability import elapsed_ms_since, get_tracer
from adaptive_disclosure_gateway.pipeline import (
    DisclosureDecision,
    decide_disclosure,
    run_disclosure_case,
)
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import FakeProvider, Provider
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
            summary = build_disclosure_summary(decision)

            # Metadata only -- status, treatment code, counts, category
            # names (safe, non-sensitive -- already used the same way by
            # detection.detect/<treatment>.sanitize's own spans) and timing.
            span.set_attribute("application.status", decision.result.status)
            span.set_attribute("application.treatment", treatment_code.value)
            span.set_attribute("application.detected_span_count", len(decision.spans))
            span.set_attribute("application.detected_categories", list(summary.detected_categories))
            span.set_attribute("application.duration_ms", elapsed_ms_since(started))

            return DisclosurePreview(
                summary=summary,
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
        """
        tracer = get_tracer()
        started = time.perf_counter()
        with tracer.start_as_current_span("application.execute") as span:
            treatment_code, treatment = self._build_treatment(request)
            disclosure_request, context = self._build_disclosure_request(request)

            execution_result = run_disclosure_case(
                treatment, disclosure_request, self._provider, detector=self._detector
            )
            # The decision this very execution made -- never a second,
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
            span.set_attribute(
                "application.provider_called", execution_result.audit.provider.called
            )
            span.set_attribute(
                "application.provider_failed", execution_result.audit.provider.failed
            )
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
            content = normalize_text_file(filename, file_bytes)
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
