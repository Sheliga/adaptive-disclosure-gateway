"""The real provider adapter at the pipeline/audit/telemetry/runner
boundary (T22 / issue #30).

``tests/test_providers_anthropic.py`` pins the adapter in isolation. This
module asks the adversarial question CLAUDE.md's disclosure-surface rule
requires: with a *real* adapter substituted for ``FakeProvider``, is there
any path by which something a treatment withheld -- or the credential -- can
still get out? Every channel named in that rule is checked here against the
same run: the provider request itself, the audit record serialized whole,
the OTel span attributes, and the runner's serialized case result.

Every test is offline: the adapter is constructed with a fake SDK client.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from adaptive_disclosure_gateway.audit import build_audit_record
from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext, Treatment
from adaptive_disclosure_gateway.experiments.execution import execute_case
from adaptive_disclosure_gateway.experiments.provider_instrumentation import (
    TimingProviderDelegate,
)
from adaptive_disclosure_gateway.experiments.runner import run_case_for_treatment
from adaptive_disclosure_gateway.pipeline import run_disclosure_case
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    AnthropicProvider,
    AnthropicProviderConfig,
    ProviderError,
    ProviderRequest,
)
from adaptive_disclosure_gateway.transformations import StaticSanitizer
from tests import telemetry_assertions

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"
CORPUS_DIR = Path(__file__).parents[1] / "corpus" / "hr" / "v1" / "cases"

MARKER_API_KEY = "sk-ant-marker-boundary-DO-NOT-LEAK"

SENSITIVE_TEXT = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)
BLOCKED_TEXT = "Employee: Ana Souza\nMedical notes: Reports chronic migraine.\n"
SENSITIVE_ORIGINALS = ("Ana Souza", "123.456.789-09", "8500", "chronic migraine")


class _Block:
    def __init__(self, type: str, text: str) -> None:
        self.type = type
        self.text = text


class _Usage:
    input_tokens = 41
    output_tokens = 13
    cache_creation_input_tokens = None
    cache_read_input_tokens = None


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Block("text", text)]
        self.model = "claude-opus-5"
        self.stop_reason = "end_turn"
        self.usage = _Usage()
        self.stop_details = None


class _RecordingMessages:
    def __init__(self, text: str, error: Exception | None) -> None:
        self._text = text
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Message:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _Message(self._text)


class _RecordingClient:
    def __init__(self, text: str = "an answer", error: Exception | None = None) -> None:
        self.messages = _RecordingMessages(text, error)


def _adapter(client: _RecordingClient) -> AnthropicProvider:
    return AnthropicProvider(AnthropicProviderConfig(), client=client)


def _request(text: str, task: str = "summarize the team record") -> DisclosureRequest:
    return DisclosureRequest(
        text=text,
        task=task,
        context=GovernanceContext(
            domain="hr",
            purpose="team_summary",
            policy_version="hr-v1",
            provider_class="external_llm",
        ),
    )


# --- Disclosure control still holds with a real adapter ----------------------


def test_a_blocked_request_never_reaches_the_real_provider():
    # BLOCK_REQUEST is the strongest disclosure control there is. If
    # swapping in a real adapter let a blocked case make an outbound HTTP
    # call, every other guarantee in this codebase would be worthless.
    client = _RecordingClient()

    result = run_disclosure_case(StaticSanitizer(), _request(BLOCKED_TEXT), _adapter(client))

    assert result.disclosure_result.status == "blocked"
    assert result.provider_response is None
    assert client.messages.calls == []


def test_a_sensitive_task_still_blocks_before_the_real_provider_is_called():
    # The regression from CLAUDE.md's leak history: a sensitive value living
    # only in request.task. The pipeline blocks it; a real adapter must not
    # become a new way for it to reach the wire.
    client = _RecordingClient()

    result = run_disclosure_case(
        StaticSanitizer(),
        _request(SENSITIVE_TEXT, task="Medical notes: Reports chronic migraine."),
        _adapter(client),
    )

    assert result.disclosure_result.status == "blocked"
    assert client.messages.calls == []


def test_removed_and_pseudonymized_content_never_reaches_the_real_provider():
    client = _RecordingClient()

    result = run_disclosure_case(StaticSanitizer(), _request(SENSITIVE_TEXT), _adapter(client))

    assert result.disclosure_result.status == "allowed"
    assert len(client.messages.calls) == 1
    sent = json.dumps(client.messages.calls[0])
    for original in SENSITIVE_ORIGINALS:
        assert original not in sent, f"{original!r} reached the provider request"


def test_a_real_provider_failure_never_degrades_to_direct_disclosure():
    # post-pilot-protocol-v1 section 9.4: a provider failure is recorded as
    # a provider_failure outcome, never silently answered by a different
    # provider and never by disclosing the original document.
    client = _RecordingClient(error=RuntimeError("upstream is down"))

    result = run_disclosure_case(StaticSanitizer(), _request(SENSITIVE_TEXT), _adapter(client))

    assert result.provider_response is None
    assert result.audit.provider.failed is True
    assert result.audit.provider.called is True
    serialized = json.dumps(result.audit.model_dump(mode="json"), default=str)
    for original in SENSITIVE_ORIGINALS:
        assert original not in serialized
    assert "upstream is down" not in serialized


# --- Audit and telemetry stay metadata-only ---------------------------------


def test_the_audit_record_of_a_real_provider_call_stays_metadata_only():
    client = _RecordingClient(text="a model answer mentioning nothing sensitive")

    result = run_disclosure_case(StaticSanitizer(), _request(SENSITIVE_TEXT), _adapter(client))

    serialized = json.dumps(result.audit.model_dump(mode="json"), default=str)
    for original in SENSITIVE_ORIGINALS:
        assert original not in serialized
    assert MARKER_API_KEY not in serialized
    assert "a model answer mentioning nothing sensitive" not in serialized
    # The reproducibility metadata that *should* be there still is.
    assert result.audit.provider.model_id == "claude-opus-5"
    assert result.audit.provider.decoding_config is not None


def test_span_attributes_never_carry_the_payload_the_answer_or_the_credential(
    recorded_spans, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    client = _RecordingClient(text="model answer text")

    run_disclosure_case(StaticSanitizer(), _request(SENSITIVE_TEXT), _adapter(client))

    telemetry_assertions.assert_span_attributes_never_leak(
        recorded_spans.get_finished_spans(),
        *SENSITIVE_ORIGINALS,
        MARKER_API_KEY,
        "model answer text",
        SENSITIVE_TEXT,
    )


def test_a_real_provider_response_never_lands_in_the_default_audit_record():
    spans = Detector().detect(SENSITIVE_TEXT)
    request = _request(SENSITIVE_TEXT)
    result = StaticSanitizer().sanitize(request, spans)
    response = _adapter(_RecordingClient(text="ANSWER-MARKER")).generate(
        ProviderRequest(payload=result.external_payload, task=request.task)
    )

    record = build_audit_record(
        request=request,
        spans=spans,
        result=result,
        treatment=Treatment.STATIC_SANITIZATION,
        provider_response=response,
        provider_class="external_llm",
        reconstructed_text=None,
    )

    assert "ANSWER-MARKER" not in json.dumps(record.model_dump(mode="json"), default=str)


# --- Usage metadata reaches the runner schema --------------------------------


def test_provider_call_metrics_carry_the_real_usage_numbers():
    # Issue #30: "actual provider token/cost fields should populate the
    # runner schema rather than being estimated heuristically".
    delegate = TimingProviderDelegate(_adapter(_RecordingClient()))

    delegate.generate(ProviderRequest(payload="p", task="t"))

    assert delegate.last_call is not None
    assert delegate.last_call.input_tokens == 41
    assert delegate.last_call.output_tokens == 13


def test_provider_call_metrics_report_usage_as_unavailable_under_the_fake_provider():
    # FakeProvider has no tokenizer and no usage accounting (protocol
    # section 9.2). The runner must be able to say "unavailable" rather than
    # report a fabricated zero.
    from adaptive_disclosure_gateway.providers import FakeProvider

    delegate = TimingProviderDelegate(FakeProvider())

    delegate.generate(ProviderRequest(payload="p", task="t"))

    assert delegate.last_call is not None
    assert delegate.last_call.input_tokens is None
    assert delegate.last_call.output_tokens is None


# --- Runner wiring -----------------------------------------------------------


def test_the_runner_uses_an_injected_real_provider_for_every_case():
    from adaptive_disclosure_gateway.corpus.loader import load_case

    client = _RecordingClient()
    case = load_case(min(CORPUS_DIR.glob("*.yaml")))

    result = run_case_for_treatment(
        case,
        Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification="pilot_development",
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        experiment_run_id="test-run",
        provider=_adapter(client),
    )

    assert result.identity.provider_name == "AnthropicProvider"
    assert result.identity.provider_model_id == "claude-opus-5"


def test_the_runner_still_defaults_to_the_fake_provider_when_none_is_injected():
    # The default must not move: TDD, CI and every deterministic regression
    # depend on FakeProvider being what a runner call uses unless a caller
    # explicitly asks for something else.
    from adaptive_disclosure_gateway.corpus.loader import load_case

    case = load_case(min(CORPUS_DIR.glob("*.yaml")))

    result = run_case_for_treatment(
        case,
        Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification="pilot_development",
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        experiment_run_id="test-run",
    )

    assert result.identity.provider_name == "FakeProvider"


def test_a_serialized_case_result_from_a_real_provider_run_leaks_nothing():
    from adaptive_disclosure_gateway.corpus.loader import load_case
    from adaptive_disclosure_gateway.experiments.case_result import to_safe_dict

    client = _RecordingClient(text="ANSWER-MARKER")
    case = load_case(min(CORPUS_DIR.glob("*.yaml")))

    result = run_case_for_treatment(
        case,
        Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification="pilot_development",
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        experiment_run_id="test-run",
        provider=_adapter(client),
    )

    serialized = json.dumps(to_safe_dict(result), default=str)
    assert "ANSWER-MARKER" not in serialized
    assert case.input.text not in serialized


def test_execute_case_accepts_the_real_adapter_without_widening_its_signature():
    # execute_case's ground-truth isolation depends on its parameter list;
    # the real provider must ride the existing ``provider`` parameter rather
    # than needing a new one.
    from adaptive_disclosure_gateway.corpus.loader import load_case

    case = load_case(min(CORPUS_DIR.glob("*.yaml")))

    execution = execute_case(
        case_input=case.input,
        treatment=Treatment.STATIC_SANITIZATION,
        corpus_version="hr/v1",
        run_classification="pilot_development",
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=_adapter(_RecordingClient()),
    )

    assert execution.provider_metrics is not None


# --- Provider class wiring ----------------------------------------------------


def test_a_provider_class_mismatch_still_blocks_the_real_adapter_before_any_call():
    client = _RecordingClient()
    provider = AnthropicProvider(
        AnthropicProviderConfig(provider_class="internal_llm"), client=client
    )

    result = run_disclosure_case(StaticSanitizer(), _request(SENSITIVE_TEXT), provider)

    # The request's context declares external_llm; the adapter declares
    # internal_llm. invoke_provider must refuse before generate() runs.
    assert result.provider_response is None
    assert result.audit.provider.called is False
    assert client.messages.calls == []


def test_the_adapter_raises_provider_error_not_a_bare_exception_for_the_pipeline():
    provider = _adapter(_RecordingClient(error=RuntimeError("boom")))

    with pytest.raises(ProviderError):
        provider.generate(ProviderRequest(payload="p", task="t"))
