"""Adversarial egress/no-leak coverage for Task-aware (B3, T07 / issue #6),
following the pattern of the existing egress tests
(``tests/test_telemetry_privacy.py``, ``tests/test_pipeline.py``'s
provider-error/audit tests): a sensitive value planted in the input must
never surface through the external payload, the outbound ``task``/prompt,
the ``ProviderRequest`` a provider actually receives, an exception message,
telemetry, the audit record, or any hash/identifier ``build_audit_record``
derives from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from adaptive_disclosure_gateway.audit import build_audit_record
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext
from adaptive_disclosure_gateway.pipeline import run_disclosure_case
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    ProviderRequest,
    ProviderResponse,
    count_transmitted_bytes,
)
from adaptive_disclosure_gateway.transformations import TaskAwareDiscloser
from adaptive_disclosure_gateway.vault import InMemoryVault
from tests.telemetry_assertions import assert_span_attributes_never_leak

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"

PLANTED_NAME = "Ana Souza"
PLANTED_CPF = "123.456.789-09"
PLANTED_SALARY_DIGITS = "8500"
TEXT = f"Employee: {PLANTED_NAME}\nCPF: {PLANTED_CPF}\nSalary: R$ {PLANTED_SALARY_DIGITS}.00\nDepartment: Engineering\n"
TASK = (
    "Confirm whether this employee's salary matches Finance department policy exactly. "
    "The employee's name and CPF are not required for this review."
)


def _discloser() -> TaskAwareDiscloser:
    return TaskAwareDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "compensation_review",
        "policy_version": "hr-v1",
        "provider_class": "fake",
        "session_id": "s1",
    }
    values.update(overrides)
    return GovernanceContext(**values)


@dataclass
class RecordingProvider:
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


def _forbidden_values() -> tuple[str, ...]:
    return (PLANTED_NAME, PLANTED_CPF, PLANTED_SALARY_DIGITS, TEXT)


def test_external_payload_never_contains_the_planted_values():
    request = DisclosureRequest(text=TEXT, task=TASK, context=_context())
    result = _discloser().sanitize(request, Detector().detect(TEXT))

    for forbidden in (PLANTED_NAME, PLANTED_CPF):
        assert forbidden not in result.external_payload


def test_provider_request_never_carries_the_planted_values_through_the_pipeline():
    request = DisclosureRequest(text=TEXT, task=TASK, context=_context())
    provider = RecordingProvider()

    run_disclosure_case(_discloser(), request, provider)

    assert len(provider.received) == 1
    received = provider.received[0]
    for field_name in ("payload", "task"):
        value = getattr(received, field_name)
        assert PLANTED_NAME not in value
        assert PLANTED_CPF not in value


def test_provider_class_mismatch_under_b3_never_calls_generate_or_leaks_the_planted_values():
    # Discovered while diagnosing this file's own provider-request test: a
    # GovernanceContext.provider_class that does not match what the actual
    # provider declares makes invoke_provider's pre-flight check fail
    # *before* generate() is ever called (see providers.invoke_provider and
    # tests/test_pipeline.py's B1-specific pin of the same behavior). This
    # is disclosure control working correctly, not a B3 defect -- pinned
    # here for B3 specifically since it is easy to mistake this fail-closed
    # block for a task-analysis bug (as the diagnosis for this test file
    # initially did).
    request = DisclosureRequest(
        text=TEXT, task=TASK, context=_context(provider_class="external_llm")
    )
    provider = RecordingProvider(provider_class="fake")  # deliberately mismatched

    execution = run_disclosure_case(_discloser(), request, provider)

    assert provider.received == []
    assert execution.disclosure_result.status == "allowed"  # B3's own sanitize() succeeded
    assert execution.provider_response is None
    assert execution.audit.provider.called is False
    assert execution.audit.provider.failure_kind == "ProviderClassMismatchError"
    dumped = execution.audit.model_dump_json()
    assert PLANTED_NAME not in dumped
    assert PLANTED_CPF not in dumped


def test_task_field_itself_never_carries_the_planted_values_when_it_should_not():
    # request.task in this module never mentions the planted values at all
    # (it only discusses categories, never quotes them) -- this pins that
    # invariant explicitly rather than assuming it.
    assert PLANTED_NAME not in TASK
    assert PLANTED_CPF not in TASK


def test_a_sensitive_value_present_only_in_task_still_fails_the_whole_pipeline_closed():
    # Mirrors tests/test_pipeline.py's defect-1 regression: B3 must not get
    # a free pass just because it is task-*aware* -- request.task is still
    # never inspected by sanitize() itself, so the shared pipeline's own
    # Detector-over-task check is what has to catch this, exactly like B1/B2.
    sensitive_task = f"Please prepare a summary.\nEmployee: {PLANTED_NAME}\nCPF: {PLANTED_CPF}\n"
    innocuous_text = "Please summarize the attached quarterly report.\n"
    request = DisclosureRequest(text=innocuous_text, task=sensitive_task, context=_context())
    provider = RecordingProvider()

    execution = run_disclosure_case(_discloser(), request, provider)

    assert provider.received == []
    assert execution.disclosure_result.status == "blocked"
    assert execution.provider_response is None


def test_exception_from_a_hostile_analyzer_never_resurfaces_the_planted_values():
    class HostileAnalyzer:
        def analyze(self, task, categories):
            raise RuntimeError(f"boom while looking at {PLANTED_NAME} / {PLANTED_CPF}")

    discloser = TaskAwareDiscloser(
        vault=InMemoryVault(),
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        task_analyzer=HostileAnalyzer(),
    )
    request = DisclosureRequest(text=TEXT, task=TASK, context=_context())

    result = discloser.sanitize(request, Detector().detect(TEXT))

    assert result.status == "blocked"
    dumped = result.model_dump_json()
    assert PLANTED_NAME not in dumped
    assert PLANTED_CPF not in dumped
    assert "boom" not in dumped


def test_telemetry_never_carries_the_planted_values_or_task_text(recorded_spans):
    request = DisclosureRequest(text=TEXT, task=TASK, context=_context())
    spans = Detector().detect(TEXT)
    recorded_spans.clear()

    result = _discloser().sanitize(request, spans)

    finished = recorded_spans.get_finished_spans()
    assert_span_attributes_never_leak(finished, *_forbidden_values(), TASK, result.external_payload)


def test_audit_record_never_carries_the_planted_values_even_serialized_whole():
    request = DisclosureRequest(text=TEXT, task=TASK, context=_context())
    spans = Detector().detect(TEXT)
    discloser = _discloser()
    result = discloser.sanitize(request, spans)

    audit = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=discloser.treatment,
        provider_response=None,
        provider_class=None,
        reconstructed_text=None,
        provider_attempted=False,
    )

    dumped = audit.model_dump_json()
    for forbidden in _forbidden_values():
        assert forbidden not in dumped
    assert TASK not in dumped


def test_audit_content_hashes_do_not_let_an_outsider_dictionary_attack_the_planted_value():
    # The hash itself is fine to record (that is its whole purpose), but it
    # must be keyed so a low-entropy value like an 11-digit CPF cannot be
    # recovered by an outsider recomputing a public digest offline -- see
    # audit.py's module docstring. Pinning this for B3 specifically closes
    # the same defect class issue #24/audit.py already closed for B1/B2.
    import hashlib

    request = DisclosureRequest(text=TEXT, task=TASK, context=_context())
    spans = Detector().detect(TEXT)
    discloser = _discloser()
    result = discloser.sanitize(request, spans)

    audit = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=discloser.treatment,
        provider_response=None,
        provider_class=None,
        reconstructed_text=None,
        provider_attempted=False,
    )

    naive_digest = hashlib.sha256(result.external_payload.encode("utf-8")).hexdigest()
    assert audit.transformation.payload_hash != naive_digest


def test_reconstructed_response_and_its_hash_never_expose_the_pseudonym_mapping(recorded_spans):
    request = DisclosureRequest(
        text=f"Employee: {PLANTED_NAME}\n",
        task="Draft an announcement addressed by name to this employee.",
        context=_context(),
    )
    discloser = _discloser()
    result = discloser.sanitize(request, Detector().detect(request.text))
    pseudonym = next(t.transformed for t in result.transformations if t.category == "employee_name")
    recorded_spans.clear()

    response_text = f"Hello {pseudonym}, welcome."
    reconstructed = discloser.reconstruct(response_text, result, request.context)
    assert reconstructed == f"Hello {PLANTED_NAME}, welcome."

    pseudonym_mapping = f"{PLANTED_NAME}:{pseudonym}"
    finished = recorded_spans.get_finished_spans()
    assert_span_attributes_never_leak(finished, PLANTED_NAME, pseudonym_mapping)

    audit = build_audit_record(
        request=request,
        spans=Detector().detect(request.text),
        result=result,
        treatment=discloser.treatment,
        provider_response=ProviderResponse(
            text=response_text,
            model_id="stub",
            model_snapshot="stub",
            decoding_config={},
            transmitted_bytes=0,
        ),
        provider_class="fake",
        reconstructed_text=reconstructed,
        provider_attempted=True,
    )
    dumped = audit.model_dump_json()
    assert PLANTED_NAME not in dumped
    assert pseudonym_mapping not in dumped
