"""Pins issue #26's end-to-end execution path acceptance criteria: one call
site runs a case through any of B0 -- Direct, B1 -- Static Sanitization or
B2 -- Reversible Pseudonymization with no treatment-specific branching,
wiring detection, the treatment and the provider (via ``invoke_provider``)
together, plus authorized reconstruction for a treatment that supports it.

These are end-to-end demonstrations, not restatements of the per-treatment
unit tests already covered by tests/test_static_sanitization.py,
tests/test_reversible_pseudonymization.py and tests/test_providers.py:
assertions here are made against what a *recording provider* actually
received, not against what a treatment's ``DisclosureResult`` merely
claims it produced.
"""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.domain import (
    DisclosureRequest,
    GovernanceContext,
    Treatment,
)
from adaptive_disclosure_gateway.pipeline import run_disclosure_case
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    ProviderRequest,
    ProviderResponse,
    count_transmitted_bytes,
)
from adaptive_disclosure_gateway.transformations import ReversiblePseudonymizer, StaticSanitizer
from adaptive_disclosure_gateway.transformations.direct_disclosure import DirectDiscloser
from adaptive_disclosure_gateway.vault import InMemoryVault
from tests.telemetry_assertions import assert_span_attributes_never_leak

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"
PIPELINE_PATH = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway" / "pipeline.py"

HR_FIXTURE_NO_MEDICAL = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)
HR_FIXTURE_WITH_MEDICAL = HR_FIXTURE_NO_MEDICAL + (
    "Medical notes: Reports chronic migraine and requested leave.\n"
)


@dataclass
class RecordingProvider:
    """Records every ``ProviderRequest`` it actually receives, for asserting
    on what reached the provider boundary rather than trusting a
    treatment's own ``DisclosureResult``.
    """

    provider_class: str = "fake"
    received: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.received.append(request)
        return ProviderResponse(
            text=f"ack over {len(request.payload)} chars",
            model_id="stub-model",
            model_snapshot="stub-snapshot",
            decoding_config={},
            transmitted_bytes=count_transmitted_bytes(request.payload),
        )


@dataclass
class EchoingRecordingProvider:
    """Echoes the payload it received back in its response text, so a B2
    round trip through the full pipeline has something real to reconstruct
    -- exactly like a real model quoting an entity back in its answer.
    """

    provider_class: str = "fake"
    received: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.received.append(request)
        return ProviderResponse(
            text=f"Summary acknowledged: {request.payload}",
            model_id="stub-model",
            model_snapshot="stub-snapshot",
            decoding_config={},
            transmitted_bytes=count_transmitted_bytes(request.payload),
        )


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
        "provider_class": "fake",
        "session_id": "s1",
    }
    values.update(overrides)
    return GovernanceContext(**values)


def _request(text: str, **context_overrides) -> DisclosureRequest:
    return DisclosureRequest(
        text=text,
        task="summarize personnel record",
        context=_context(**context_overrides),
    )


def _request_with_task(text: str, task: str, **context_overrides) -> DisclosureRequest:
    return DisclosureRequest(
        text=text,
        task=task,
        context=_context(**context_overrides),
    )


def _b2() -> ReversiblePseudonymizer:
    return ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )


# --- Structural: no treatment-specific branching at the call site -----------


def test_pipeline_call_site_never_imports_a_concrete_treatment_class():
    """The shared execution path must know only the sanitize/reconstruct
    *shape* (structural typing), never the concrete B0/B1/B2 classes -- an
    import of one would mean something in the call site could special-case
    it by name.
    """
    tree = ast.parse(PIPELINE_PATH.read_text(encoding="utf-8"), filename=str(PIPELINE_PATH))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            imported_names.update(alias.name for alias in node.names)

    forbidden = {"DirectDiscloser", "StaticSanitizer", "ReversiblePseudonymizer"}
    assert not (imported_names & forbidden), (
        f"pipeline.py must not import concrete treatment classes: {imported_names & forbidden}"
    )


def test_pipeline_call_site_never_branches_on_which_treatment_is_running():
    """No branch may key on a specific ``Treatment`` enum member (e.g.
    ``if treatment.treatment is Treatment.DIRECT``); the only outcomes the
    call site may branch on are generic ones every treatment already
    exposes (``DisclosureResult.status``, whether the object happens to
    implement ``reconstruct``).
    """
    tree = ast.parse(PIPELINE_PATH.read_text(encoding="utf-8"), filename=str(PIPELINE_PATH))
    forbidden_members = {
        "DIRECT",
        "STATIC_SANITIZATION",
        "REVERSIBLE_PSEUDONYMIZATION",
        "TASK_AWARE",
        "POLICY_GOVERNED",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden_members:
            raise AssertionError(
                f"pipeline.py:{node.lineno} references Treatment.{node.attr} -- the call "
                "site must not branch on which treatment is running"
            )


# --- Same case through all three treatments produces comparable results -----


def test_same_hr_case_runs_through_b0_b1_b2_with_no_call_site_branching():
    request = _request(HR_FIXTURE_NO_MEDICAL)
    treatments = {
        Treatment.DIRECT: DirectDiscloser(),
        Treatment.STATIC_SANITIZATION: StaticSanitizer(),
        Treatment.REVERSIBLE_PSEUDONYMIZATION: _b2(),
    }

    executions = {}
    for expected_treatment, treatment in treatments.items():
        provider = RecordingProvider()
        executions[expected_treatment] = run_disclosure_case(treatment, request, provider)
        assert executions[expected_treatment].audit.treatment == expected_treatment

    # Comparable: the same detector ran over the same text for every
    # treatment, so detection is identical across all three -- only what
    # each treatment *did* with the spans differs.
    span_counts = {execution.audit.detection.span_count for execution in executions.values()}
    assert len(span_counts) == 1
    categories = {tuple(execution.audit.detection.categories) for execution in executions.values()}
    assert len(categories) == 1

    # All three actually ran to completion (none blocked over this fixture).
    for execution in executions.values():
        assert execution.disclosure_result.status == "allowed"
        assert execution.provider_response is not None

    b0 = executions[Treatment.DIRECT]
    b1 = executions[Treatment.STATIC_SANITIZATION]
    b2 = executions[Treatment.REVERSIBLE_PSEUDONYMIZATION]

    # B0 is the unsafe baseline: the payload really is the raw text.
    assert b0.disclosure_result.external_payload == HR_FIXTURE_NO_MEDICAL
    # B1 removes what it cannot reverse.
    assert "Ana Souza" not in b1.disclosure_result.external_payload
    assert "123.456.789-09" not in b1.disclosure_result.external_payload
    assert "Engineering" in b1.disclosure_result.external_payload
    # B2 pseudonymizes instead of removing.
    assert "Ana Souza" not in b2.disclosure_result.external_payload
    assert "PSEUDO-employee_name-" in b2.disclosure_result.external_payload

    # Only B2 has anything to reconstruct.
    assert b0.reconstructed_text is None
    assert b1.reconstructed_text is None
    assert b2.reconstructed_text is not None
    assert b0.audit.reconstruction.attempted is False
    assert b1.audit.reconstruction.attempted is False
    assert b2.audit.reconstruction.attempted is True


# --- REMOVE content never reaches the provider that actually ran -----------


def test_remove_mapped_originals_never_reach_the_provider_b1_actually_used():
    request = _request(HR_FIXTURE_NO_MEDICAL)
    provider = RecordingProvider()

    run_disclosure_case(StaticSanitizer(), request, provider)

    assert len(provider.received) == 1
    received = provider.received[0]
    for field_name in ("payload", "task"):
        value = getattr(received, field_name)
        assert "Ana Souza" not in value
        assert "123.456.789-09" not in value


# --- BLOCK_REQUEST stops the entire external request ------------------------


@pytest.mark.parametrize("treatment_factory", [StaticSanitizer, lambda: _b2()])
def test_block_request_means_the_provider_is_never_called_at_all(treatment_factory):
    request = _request(HR_FIXTURE_WITH_MEDICAL)
    provider = RecordingProvider()

    execution = run_disclosure_case(treatment_factory(), request, provider)

    assert execution.disclosure_result.status == "blocked"
    assert provider.received == [], "provider must never be invoked for a blocked request"
    assert execution.provider_response is None
    assert execution.audit.provider.called is False
    assert execution.reconstructed_text is None


# --- Vault originals and pseudonym-generation state never leak -------------


def test_vault_originals_never_reach_the_provider_or_telemetry_through_the_pipeline(
    recorded_spans,
):
    request = _request(HR_FIXTURE_NO_MEDICAL)
    provider = RecordingProvider()

    execution = run_disclosure_case(_b2(), request, provider)

    pseudonym = next(
        t.transformed
        for t in execution.disclosure_result.transformations
        if t.category == "employee_name"
    )
    pseudonym_mapping = f"Ana Souza:{pseudonym}"

    received = provider.received[0]
    for field_name in ("payload", "task"):
        value = getattr(received, field_name)
        assert "Ana Souza" not in value
        assert "123.456.789-09" not in value

    finished = recorded_spans.get_finished_spans()
    assert_span_attributes_never_leak(
        finished,
        "Ana Souza",
        "123.456.789-09",
        HR_FIXTURE_NO_MEDICAL,
        pseudonym_mapping,
    )


# --- The path requires the caller to supply pseudonym-scope identifiers;
# it does not invent them, and a missing one is caller-visible, not a
# silently-resolved artifact. ------------------------------------------------


def test_pipeline_blocks_when_the_caller_omits_the_identifier_the_resolved_scope_needs():
    # hr_analyst's ceiling is SESSION (configs/policies/hr-v1.yaml); the
    # default requested scope is also SESSION. Omitting session_id means
    # the resolved scope has no identifier to key the vault partition on,
    # so B2 fails closed -- this is disclosure control working correctly,
    # not an artifact of this pipeline forgetting to pass something through.
    request = _request(HR_FIXTURE_NO_MEDICAL, requester_role="hr_analyst", session_id=None)
    provider = RecordingProvider()

    execution = run_disclosure_case(_b2(), request, provider)

    assert execution.disclosure_result.status == "blocked"
    assert provider.received == []


def test_pipeline_succeeds_once_the_caller_supplies_the_identifier_the_resolved_scope_needs():
    # Identical case, but with the identifier the resolved SESSION scope
    # requires actually supplied -- proving the block above is about the
    # caller's own GovernanceContext, not something this pipeline fails to
    # wire through even when the caller did the right thing.
    request = _request(
        HR_FIXTURE_NO_MEDICAL, requester_role="hr_analyst", session_id="analyst-session"
    )
    provider = RecordingProvider()

    execution = run_disclosure_case(_b2(), request, provider)

    assert execution.disclosure_result.status == "allowed"
    assert len(provider.received) == 1


# --- B2 response round trip through the full pipeline -----------------------


def test_b2_response_round_trip_reconstructs_authorized_pseudonyms_through_the_full_pipeline():
    text = "Employee: Ana Souza\n"
    request = _request(text)
    provider = EchoingRecordingProvider()

    execution = run_disclosure_case(_b2(), request, provider)

    assert execution.disclosure_result.status == "allowed"
    pseudonym = next(
        t.transformed
        for t in execution.disclosure_result.transformations
        if t.category == "employee_name"
    )
    # The provider really did receive (and echo back) the pseudonym, never
    # the original name.
    assert pseudonym in provider.received[0].payload
    assert "Ana Souza" not in provider.received[0].payload
    assert execution.provider_response is not None
    assert pseudonym in execution.provider_response.text

    # The full path reconstructs the original back in, and the pseudonym is
    # gone from the final answer.
    assert execution.reconstructed_text == f"Summary acknowledged: {text}"
    assert pseudonym not in execution.reconstructed_text
    assert "Ana Souza" in execution.reconstructed_text

    assert execution.audit.reconstruction.attempted is True
    assert execution.audit.reconstruction.changed_from_provider_response is True


# --- Defect 1: a sensitive value present only in request.task must never
# reach the provider for B1/B2, and B0 -- Direct is exempt by design --------

# Deliberately reuses the HR fixture's employee name and CPF, but embeds them
# ONLY in the task, never in the text: detection/every treatment only ever
# inspects request.text, so before the fix these values sailed straight
# through to the provider in the task field, for both B1 and B2.
SENSITIVE_TASK = "Please prepare a summary.\nEmployee: Ana Souza\nCPF: 123.456.789-09\n"
INNOCUOUS_TEXT = "Please summarize the attached quarterly report.\n"


@pytest.mark.parametrize("treatment_factory", [StaticSanitizer, lambda: _b2()])
def test_sensitive_value_present_only_in_task_causes_b1_and_b2_to_fail_closed_and_never_reach_the_provider(
    treatment_factory,
):
    request = _request_with_task(INNOCUOUS_TEXT, SENSITIVE_TASK, session_id="s1")
    provider = RecordingProvider()

    execution = run_disclosure_case(treatment_factory(), request, provider)

    assert provider.received == [], "provider must never see a task-only sensitive value"
    assert execution.disclosure_result.status == "blocked"
    assert execution.provider_response is None
    assert execution.reconstructed_text is None
    assert execution.audit.provider.called is False
    assert any(
        "task" in decision.reason.lower() for decision in execution.disclosure_result.decisions
    ), "the block reason must record that the task was why this request failed closed"


def test_b0_direct_still_sends_a_sensitive_task_to_the_provider_unchanged_as_the_unsafe_control():
    """Regression pin: B0 -- Direct is the intentionally unsafe control every
    other treatment is measured against (see direct_disclosure.py's module
    docstring). It must keep sending request.task (and request.text)
    completely raw -- including the exact sensitive content that makes B1/B2
    fail closed in the test above -- or every B0->B1/B2 comparison would be
    silently biased in B0's favor. This must stay green forever: if a future
    change makes B0 start inspecting/blocking on task content, this is the
    test that should catch it.
    """
    request = _request_with_task(INNOCUOUS_TEXT, SENSITIVE_TASK, session_id="s1")
    provider = RecordingProvider()

    execution = run_disclosure_case(DirectDiscloser(), request, provider)

    assert execution.disclosure_result.status == "allowed"
    assert len(provider.received) == 1
    assert provider.received[0].task == SENSITIVE_TASK
    assert "Ana Souza" in provider.received[0].task
    assert "123.456.789-09" in provider.received[0].task


# --- Defect 3: a provider error or timeout must still fail closed with a
# metadata-only audit record, not an unhandled exception and no audit at
# all ---------------------------------------------------------------------


@dataclass
class AlwaysFailingProvider:
    """A stub whose ``generate`` always raises. The message deliberately
    echoes something that looks like request content (the way a real HTTP
    client can quote the request body it failed to send) so a test can
    confirm that text never resurfaces in the audit record.
    """

    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise RuntimeError(f"boom: could not deliver payload of {len(request.payload)} chars")


@dataclass
class AlwaysTimingOutProvider:
    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        time.sleep(1.0)
        return ProviderResponse(
            text="unreachable",
            model_id="unreachable-model",
            model_snapshot="unreachable-snapshot",
            decoding_config={},
            transmitted_bytes=0,
        )


def test_provider_error_fails_closed_with_a_metadata_only_audit_record_instead_of_an_unhandled_exception():
    request = _request(HR_FIXTURE_NO_MEDICAL)
    provider = AlwaysFailingProvider()

    execution = run_disclosure_case(StaticSanitizer(), request, provider)

    assert execution.provider_response is None
    assert execution.reconstructed_text is None
    assert execution.audit.provider.called is True
    assert execution.audit.provider.failed is True
    assert execution.audit.provider.failure_kind == "ProviderError"

    dumped = execution.audit.model_dump_json()
    assert "boom" not in dumped
    assert "Ana Souza" not in dumped
    assert "123.456.789-09" not in dumped
    assert HR_FIXTURE_NO_MEDICAL not in dumped


def test_provider_timeout_fails_closed_with_a_metadata_only_audit_record_instead_of_an_unhandled_exception():
    request = _request(HR_FIXTURE_NO_MEDICAL)
    provider = AlwaysTimingOutProvider()

    started = time.perf_counter()
    execution = run_disclosure_case(StaticSanitizer(), request, provider, timeout=0.05)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5, "the timeout must actually be enforced, not just eventually return"
    assert execution.provider_response is None
    assert execution.reconstructed_text is None
    assert execution.audit.provider.called is True
    assert execution.audit.provider.failed is True
    assert execution.audit.provider.failure_kind == "ProviderTimeoutError"

    dumped = execution.audit.model_dump_json()
    assert "Ana Souza" not in dumped
    assert HR_FIXTURE_NO_MEDICAL not in dumped
