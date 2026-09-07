"""Tests for the shared external-provider adapter interface (issue #12 / T11).

Covers the acceptance criteria not already pinned by
``tests/test_provider_isolation.py``: deterministic ``FakeProvider``,
reproducibility metadata, the documented transmitted-volume counting rule,
fail-closed behavior on provider error/timeout (never retried, never
degraded to B0 -- Direct), ``provider_class`` mismatch detection, and a
runtime check that nothing a treatment withheld reaches a provider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pytest

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext
from adaptive_disclosure_gateway.providers import (
    FakeProvider,
    ProviderClassMismatchError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    count_transmitted_bytes,
    invoke_provider,
)
from adaptive_disclosure_gateway.transformations import StaticSanitizer

HR_FIXTURE_NO_MEDICAL = (
    "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
)


# --- FakeProvider: determinism and reproducibility metadata -----------------


def test_fake_provider_returns_identical_response_for_identical_requests():
    provider = FakeProvider()
    request = ProviderRequest(payload="Department: Engineering", task="summarize")

    first = provider.generate(request)
    second = provider.generate(request)

    assert first.text == second.text
    assert first.model_id == second.model_id
    assert first.model_snapshot == second.model_snapshot
    assert first.decoding_config == second.decoding_config


def test_fake_provider_response_differs_for_different_payloads():
    # Guards against a stub that ignores its input entirely -- a constant
    # response would still pass the determinism test above.
    provider = FakeProvider()
    a = provider.generate(ProviderRequest(payload="Department: Engineering", task="summarize"))
    b = provider.generate(ProviderRequest(payload="Department: Sales", task="summarize"))

    assert a.text != b.text


def test_two_independent_fake_provider_instances_report_the_same_reproducibility_metadata():
    # Reproducibility metadata must identify the model/snapshot/decoding
    # configuration, not be freshly (and differently) generated per instance
    # -- otherwise two runs of the "same" provider could not be compared.
    first = FakeProvider().generate(ProviderRequest(payload="x", task="t"))
    second = FakeProvider().generate(ProviderRequest(payload="x", task="t"))

    assert first.model_id == second.model_id
    assert first.model_snapshot == second.model_snapshot
    assert first.decoding_config == second.decoding_config


# --- Transmitted volume counting rule ---------------------------------------


def test_transmitted_bytes_counts_utf8_encoded_payload_length():
    payload = "héllo wörld"  # multi-byte UTF-8 characters
    assert count_transmitted_bytes(payload) == len(payload.encode("utf-8"))
    assert count_transmitted_bytes(payload) != len(payload)  # would be wrong if counting chars


def test_fake_provider_transmitted_bytes_ignores_task_length():
    # The counting rule is defined over the payload alone (see
    # count_transmitted_bytes's docstring): task/prompt scaffolding is held
    # constant across treatments per docs/experimental-design.md, so it must
    # not move this metric.
    provider = FakeProvider()
    short_task = provider.generate(ProviderRequest(payload="same payload", task="a"))
    long_task = provider.generate(
        ProviderRequest(payload="same payload", task="a much longer task description string")
    )

    assert short_task.transmitted_bytes == long_task.transmitted_bytes
    assert short_task.transmitted_bytes == count_transmitted_bytes("same payload")


# --- invoke_provider: provider_class wiring ---------------------------------


@dataclass
class _CountingStubProvider:
    provider_class: str
    response: ProviderResponse | None = None
    error: Exception | None = None
    delay_seconds: float = 0.0
    received: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.received.append(request)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _stub_response() -> ProviderResponse:
    return ProviderResponse(
        text="stub-response",
        model_id="stub-model",
        model_snapshot="stub-snapshot",
        decoding_config={},
        transmitted_bytes=0,
    )


def test_invoke_provider_succeeds_when_provider_class_matches():
    stub = _CountingStubProvider(provider_class="external_llm", response=_stub_response())
    request = ProviderRequest(payload="p", task="t")

    result = invoke_provider(stub, request, expected_provider_class="external_llm")

    assert result.text == "stub-response"
    assert len(stub.received) == 1


def test_invoke_provider_blocks_on_provider_class_mismatch_without_calling_generate():
    stub = _CountingStubProvider(provider_class="fake", response=_stub_response())
    request = ProviderRequest(payload="p", task="t")

    with pytest.raises(ProviderClassMismatchError):
        invoke_provider(stub, request, expected_provider_class="external_llm")

    # Detected, not ignored: the mismatched provider must never actually be
    # invoked -- a request that would have been answered by the wrong
    # provider class must not silently proceed.
    assert stub.received == []


# --- invoke_provider: fail closed on error/timeout, no retry ---------------


def test_invoke_provider_fails_closed_and_never_retries_when_provider_raises():
    stub = _CountingStubProvider(provider_class="fake", error=RuntimeError("boom"))
    request = ProviderRequest(payload="p", task="t")

    with pytest.raises(ProviderError):
        invoke_provider(stub, request, expected_provider_class="fake")

    # Exactly one attempt: a provider error must fail the request, not
    # trigger a retry that re-sends a payload the treatment did not
    # authorize a second time.
    assert len(stub.received) == 1


def test_invoke_provider_fails_closed_on_timeout_and_returns_before_the_call_finishes():
    stub = _CountingStubProvider(
        provider_class="fake", delay_seconds=1.0, response=_stub_response()
    )
    request = ProviderRequest(payload="p", task="t")

    started = time.perf_counter()
    with pytest.raises(ProviderTimeoutError):
        invoke_provider(stub, request, expected_provider_class="fake", timeout=0.05)
    elapsed = time.perf_counter() - started

    # The timeout must actually be enforced by invoke_provider itself
    # (rather than merely being a documentation promise the slow provider
    # happens to honor): the call must fail well before the stub's 1s delay
    # elapses.
    assert elapsed < 0.5
    assert len(stub.received) == 1


def test_provider_timeout_error_is_a_provider_error_so_callers_can_fail_closed_uniformly():
    assert issubclass(ProviderTimeoutError, ProviderError)


# --- Runtime payload isolation: nothing a treatment withheld reaches a
# provider ------------------------------------------------------------------


@dataclass
class _RecordingStubProvider:
    """Records every ``ProviderRequest`` it is given, for asserting on what
    actually reached the provider boundary -- not just what the treatment's
    ``DisclosureResult`` claims it produced.
    """

    provider_class: str = "fake"
    received: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.received.append(request)
        return ProviderResponse(
            text="ack",
            model_id="stub",
            model_snapshot="stub",
            decoding_config={},
            transmitted_bytes=count_transmitted_bytes(request.payload),
        )


def test_provider_never_receives_sensitive_originals_from_the_hr_fixture():
    text = HR_FIXTURE_NO_MEDICAL
    spans = Detector().detect(text)
    request = DisclosureRequest(
        text=text,
        task="summarize personnel record",
        context=GovernanceContext(domain="hr", purpose="team_summary", policy_version="hr-v1"),
    )

    result = StaticSanitizer().sanitize(request, spans)
    assert result.status == "allowed"

    provider_request = ProviderRequest(payload=result.external_payload, task=request.task)
    stub = _RecordingStubProvider()
    invoke_provider(stub, provider_request, expected_provider_class=stub.provider_class)

    assert len(stub.received) == 1
    received = stub.received[0]
    sensitive_originals = ("Ana Souza", "123.456.789-09", "8500")
    for field_name in ("payload", "task"):
        value = getattr(received, field_name)
        for original in sensitive_originals:
            assert original not in value, (
                f"provider received sensitive original {original!r} via field {field_name!r}"
            )
