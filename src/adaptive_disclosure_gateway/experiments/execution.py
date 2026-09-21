"""Ground-truth-isolated case execution for T10's experiment runner
(issue #8).

``execute_case`` is the single boundary between "everything a treatment may
see" and "everything the runner needs to score/report afterward". Its
signature takes a ``CorpusCaseInput`` -- never a ``CaseOracle`` or a
``CorpusCase`` (which would bundle the oracle alongside it) -- so a caller
cannot accidentally thread ground truth into treatment execution even by
mistake; there is no parameter here that could carry it.
``tests/test_experiments_ground_truth_isolation.py`` pins this both
structurally (AST/signature inspection) and behaviorally (spies that would
raise if ever handed anything oracle-shaped).

Every treatment runs through the real, unmodified
``pipeline.run_disclosure_case`` (via ``span_capture.run_case_with_span_capture``)
-- this module never reimplements or duplicates pipeline logic to measure
timing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from adaptive_disclosure_gateway.corpus.case_input import CorpusCaseInput
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import Treatment
from adaptive_disclosure_gateway.pipeline import ExecutionResult, ReconstructingTreatment
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import Provider, caller_timeout_for_provider
from adaptive_disclosure_gateway.task_analysis import TaskAnalyzer
from adaptive_disclosure_gateway.vault import InMemoryVault, Vault

from .b4_span_metadata import B4Metadata, extract_b4_metadata
from .corpus_source import build_request
from .detector_capture import DetectedSpanRef, RecordingDetector
from .post_pilot_protocol import CURRENT_PROTOCOL_ID, validate_scorable_protocol_id
from .provider_instrumentation import ProviderCallMetrics, TimingProviderDelegate
from .resource_metrics import ResourceMetrics, measure_resources
from .run_identity import (
    B3_TASK_AWARE_BASELINE_COMMIT,
    B4_POLICY_GOVERNED_COMMIT,
    SCHEMA_VERSION,
    RunClassification,
    RunIdentity,
)
from .span_capture import run_case_with_span_capture
from .stage_timing import StageTimings, extract_stage_timings
from .treatments import build_treatment

# PR #35 review, blocker 1: B3 and B4 are two distinct frozen
# implementations. treatment_version names *this result's own* frozen
# commit; task_aware_baseline_version separately names the B3 baseline the
# result's task-analysis/action-space machinery depends on -- identical to
# treatment_version for B3 itself, but B3's (older, different) commit for
# B4. Never conflate the two into one field again -- that was exactly the
# defect this split fixes (every B4 result previously reported B3's commit
# as if it were B4's own).
_TREATMENT_VERSION_BY_TREATMENT: dict[Treatment, str] = {
    Treatment.TASK_AWARE: B3_TASK_AWARE_BASELINE_COMMIT,
    Treatment.POLICY_GOVERNED: B4_POLICY_GOVERNED_COMMIT,
}
_TASK_AWARE_BASELINE_VERSION_BY_TREATMENT: dict[Treatment, str] = {
    Treatment.TASK_AWARE: B3_TASK_AWARE_BASELINE_COMMIT,
    Treatment.POLICY_GOVERNED: B3_TASK_AWARE_BASELINE_COMMIT,
}

# PR #35 review, blocker 3: the resource-measurement window wraps exactly
# the same call span_capture.run_case_with_span_capture makes to the real
# pipeline.run_disclosure_case -- detection, the treatment's own sanitize(),
# the provider call and, when applicable, reconstruction. Never presented as
# if it measured only the treatment's own sanitize() in isolation -- see
# resource_metrics.py's module docstring.
_RESOURCE_MEASUREMENT_SCOPE = (
    "detection+treatment+provider+reconstruction "
    "(whole pipeline.run_disclosure_case call, via run_case_with_span_capture)"
)


@dataclass(frozen=True)
class CaseExecution:
    """Everything one case's run through one treatment produced, safe to
    hand to the scorer. Carries the real ``ExecutionResult`` (including its
    ``AuditRecord`` and, only if the caller opted in, raw-value capture) --
    never anything from a ``CaseOracle``.
    """

    identity: RunIdentity
    treatment: Treatment
    execution: ExecutionResult
    stage_timings: StageTimings
    provider_metrics: ProviderCallMetrics | None
    b4_metadata: B4Metadata | None
    # The real spans the Detector produced for request.text during this
    # execution (PR #35 review, blocker 2) -- captured, never re-detected,
    # by a RecordingDetector wrapping the same Detector instance the
    # treatment actually ran against. Category/offset-only: never the
    # detected value itself (see detector_capture.py's module docstring).
    # Scored against the oracle strictly post-hoc, in
    # experiments/scoring/detector_scoring.py -- this field alone carries no
    # ground truth and nothing here changes if score_case is never called.
    detected_text_spans: tuple[DetectedSpanRef, ...]
    # Process CPU time and peak Python-level memory allocation across the
    # same call that produced `execution` (PR #35 review, blocker 3) -- see
    # resource_metrics.py's module docstring for exactly what is and is not
    # measured, and _RESOURCE_MEASUREMENT_SCOPE above for this field's own
    # measurement_scope value.
    resource_metrics: ResourceMetrics
    # ``execution.reconstructed_text`` reflects the *real* pipeline's
    # reconstruction, driven by FakeProvider's actual response text --
    # which never echoes any payload content at all (see
    # ``providers/fake.py``), so it is, honestly, always a no-op substitution
    # under FakeProvider: there is nothing in the response for a pseudonym
    # to be found and replaced in. That is a real, correctly-reported
    # property of using a non-echoing fake provider -- not a reconstruction
    # defect -- and ``execution.reconstructed_text`` is kept exactly as the
    # real pipeline produced it for that reason.
    #
    # To still measure the underlying round-trip *mechanism* (does the
    # vault correctly map a pseudonym back to its original under this
    # request's governance context), this field independently calls the
    # same treatment's own ``reconstruct()`` against ``external_payload``
    # itself -- which deterministically contains every pseudonym the
    # treatment just emitted, verbatim, by construction of
    # ``decision_application._allowed_result``. This simulates what a real,
    # content-echoing provider's response would make possible, and is the
    # basis for T10's reconstruction-scoring round trip
    # (``experiments/scoring/reconstruction.py``). ``None`` whenever the
    # treatment has no ``reconstruct`` capability (B0, B1) or the request
    # was blocked (nothing was disclosed to reconstruct against).
    payload_echo_reconstructed_text: str | None


def execute_case(
    *,
    case_input: CorpusCaseInput,
    treatment: Treatment,
    corpus_version: str,
    run_classification: RunClassification,
    policy_repository: PolicyRepository,
    vault: Vault | None = None,
    task_analyzer: TaskAnalyzer | None = None,
    detector: Detector | None = None,
    provider: Provider | None = None,
    context_overrides: Mapping[str, Any] | None = None,
    capture_raw_values_for_controlled_experiment: bool = False,
    protocol_id: str | None = None,
) -> CaseExecution:
    """Run ``case_input`` through ``treatment`` and return a structured,
    ground-truth-free result.

    ``vault`` defaults to a fresh, per-call ``InMemoryVault`` -- this pilot
    never shares or persists a vault across cases (out of scope per the T10
    brief). ``provider`` defaults to a fresh ``FakeProvider`` wrapped in a
    ``TimingProviderDelegate`` -- pass an already-wrapped delegate to reuse
    timing/volume capture, or a bare ``Provider`` to have it wrapped here.

    ``protocol_id`` (Issue #87 / M3) names the post-pilot scoring protocol
    this execution's ``RunIdentity.protocol_id`` will carry. Left ``None``
    (the default), it resolves to ``CURRENT_PROTOCOL_ID`` **at call time**
    -- never at import/module-load time -- so a test that monkeypatches
    ``CURRENT_PROTOCOL_ID`` still observes the effect. Resolved either way,
    it is validated as both frozen and currently scorable
    (``validate_scorable_protocol_id``) before ``RunIdentity`` is
    constructed. Passing an explicit id (e.g. ``"post-pilot-v3"``) is how a
    caller scores a legacy/historical corpus (``corpus/hr/v1``,
    ``corpus/contracts/v1``) that has no opted-in ``utility_references`` --
    scoring such a corpus under the current default would otherwise raise
    (see ``experiments/scoring/utility.py``'s compatibility matrix).

    A caller-supplied ``provider`` is used exactly as given. The default
    ``FakeProvider`` instead has its ``provider_class`` attribute set to
    match ``request.context.provider_class`` for *this* case -- never left
    at ``FakeProvider``'s own literal ``"fake"`` class attribute. Per
    ``providers.invoke_provider``'s own contract, a provider whose declared
    class disagrees with what ``GovernanceContext.provider_class`` names is
    never actually invoked (``ProviderClassMismatchError``, raised before
    ``generate()``) -- exactly what would happen on every pilot case, since
    every corpus case's context defaults to ``provider_class="external_llm"``,
    never ``"fake"``. ``FakeProvider`` stands in for *whichever* provider
    class a case is testing against (including the B4 contextual matrix's
    own ``external_llm``/``internal_llm`` comparison), so its declared class
    must track the request it is serving, not a fixed literal.
    """
    from adaptive_disclosure_gateway.providers import FakeProvider

    active_vault = vault if vault is not None else InMemoryVault()
    active_treatment = build_treatment(
        treatment,
        vault=active_vault,
        policy_repository=policy_repository,
        task_analyzer=task_analyzer,
    )
    request = build_request(case_input, context_overrides=context_overrides)

    if provider is not None:
        base_provider = provider
    else:
        base_provider = FakeProvider()
        base_provider.provider_class = request.context.provider_class
    timing_provider = (
        base_provider
        if isinstance(base_provider, TimingProviderDelegate)
        else TimingProviderDelegate(base_provider)
    )

    # PR #62 review, blocker 2: the caller-side wall-clock deadline must
    # genuinely exceed a real provider's native transport timeout, not rely
    # on run_case_with_span_capture's own default (30s) regardless of what
    # the injected provider's native timeout is (60s for AnthropicProvider's
    # default configuration). Derived from base_provider -- the provider as
    # the caller supplied it, before TimingProviderDelegate wraps it -- so a
    # provider exposing native_timeout_seconds (AnthropicProvider) drives its
    # own deadline; FakeProvider and every provider that predates this
    # attribute get the unchanged default.
    case_timeout = caller_timeout_for_provider(base_provider)

    recording_detector = RecordingDetector(detector if detector is not None else Detector())

    (exec_result, spans), resource_metrics = measure_resources(
        _RESOURCE_MEASUREMENT_SCOPE,
        lambda: run_case_with_span_capture(
            active_treatment,
            request,
            timing_provider,
            detector=recording_detector,
            timeout=case_timeout,
            capture_raw_values_for_controlled_experiment=(
                capture_raw_values_for_controlled_experiment
            ),
        ),
    )
    detected_text_spans = recording_detector.text_spans

    stage_timings = extract_stage_timings(spans)
    b4_metadata = extract_b4_metadata(spans) if treatment is Treatment.POLICY_GOVERNED else None

    provider_metrics = timing_provider.last_call
    model_id = (
        provider_metrics.model_id
        if provider_metrics is not None
        else base_provider.__class__.__name__
    )
    model_snapshot = (
        provider_metrics.model_snapshot if provider_metrics is not None else "not_called"
    )

    # Resolved at call time (never at import time) so a caller/test that
    # changes CURRENT_PROTOCOL_ID still observes the effect (M3 Gate 6 /
    # issue #38's own regression pin already depends on this). Fail closed
    # against an unregistered, misspelled or no-longer-scorable protocol id
    # rather than silently stamping every result with an unverified
    # constant (docs/research/post-pilot-protocol-v2.md's provenance
    # section; Issue #87 / M3 extends the check to scorability).
    resolved_protocol_id = protocol_id if protocol_id is not None else CURRENT_PROTOCOL_ID
    validate_scorable_protocol_id(resolved_protocol_id)

    identity = RunIdentity(
        schema_version=SCHEMA_VERSION,
        run_classification=run_classification,
        corpus_version=corpus_version,
        case_id=case_input.sample_id,
        treatment_code=treatment.value,
        treatment_name=treatment.name.lower(),
        treatment_version=_TREATMENT_VERSION_BY_TREATMENT.get(treatment),
        task_aware_baseline_version=_TASK_AWARE_BASELINE_VERSION_BY_TREATMENT.get(treatment),
        policy_version=request.context.policy_version,
        matrix_cell=(
            "|".join(b4_metadata.matrix_cells)
            if b4_metadata is not None and b4_metadata.matrix_cells
            else None
        ),
        provider_name=type(timing_provider._wrapped).__name__,
        provider_model_id=model_id,
        provider_model_snapshot=model_snapshot,
        protocol_id=resolved_protocol_id,
    )

    payload_echo_reconstructed_text: str | None = None
    if exec_result.disclosure_result.status == "allowed" and isinstance(
        active_treatment, ReconstructingTreatment
    ):
        # Called outside run_case_with_span_capture's tracer window on
        # purpose: this is a runner-only measurement call, not part of the
        # real pipeline's own span tree, and must not perturb
        # stage_timings' extraction of the real run's spans.
        payload_echo_reconstructed_text = active_treatment.reconstruct(
            exec_result.disclosure_result.external_payload,
            exec_result.disclosure_result,
            request.context,
        )

    return CaseExecution(
        identity=identity,
        treatment=treatment,
        execution=exec_result,
        stage_timings=stage_timings,
        provider_metrics=provider_metrics,
        b4_metadata=b4_metadata,
        detected_text_spans=detected_text_spans,
        resource_metrics=resource_metrics,
        payload_echo_reconstructed_text=payload_echo_reconstructed_text,
    )
