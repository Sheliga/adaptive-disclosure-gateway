"""Purely local readiness checks per ``Provider`` implementation (T25 review
finding 2). ``providers.readiness.provider_readiness`` must never touch the
network, never construct an SDK client and never call ``generate()`` -- see
that module's own docstring for why this is a different, stricter contract
than ``DisclosureApplicationService.describe_health``.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.providers import AnthropicProvider, AnthropicProviderConfig
from adaptive_disclosure_gateway.providers import readiness as readiness_module
from adaptive_disclosure_gateway.providers.fake import FakeProvider
from adaptive_disclosure_gateway.providers.readiness import (
    REASON_PROVIDER_CREDENTIAL_MISSING,
    REASON_PROVIDER_SDK_UNAVAILABLE,
    REASON_PROVIDER_UNRECOGNIZED,
    provider_readiness,
)

MARKER_API_KEY = "sk-ant-marker-readiness-test-value"


class _UnrecognizedProvider:
    provider_class = "mystery"

    def generate(self, request):  # pragma: no cover -- never invoked
        raise AssertionError("readiness must never call generate()")


def test_fake_provider_is_always_ready_with_no_credential_needed(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    ready, reason = provider_readiness(FakeProvider())

    assert ready is True
    assert reason is None


def test_anthropic_provider_ready_when_key_present_and_sdk_importable(monkeypatch):
    """The ``anthropic`` package is an optional extra (pyproject.toml) --
    the baseline dev/test/CI environment never installs it. This test must
    still exercise the "SDK importable" branch without depending on whether
    it happens to be installed in whatever environment runs the suite, so
    ``find_spec`` is monkeypatched to report the package present, the same
    hook the adjacent not-importable test already uses.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    monkeypatch.setattr(readiness_module, "find_spec", lambda name: object())
    provider = AnthropicProvider(AnthropicProviderConfig())

    ready, reason = provider_readiness(provider)

    assert ready is True
    assert reason is None


def test_anthropic_provider_not_ready_when_credential_env_var_is_unset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicProvider(AnthropicProviderConfig())

    ready, reason = provider_readiness(provider)

    assert ready is False
    assert reason == REASON_PROVIDER_CREDENTIAL_MISSING


def test_anthropic_provider_not_ready_when_credential_is_blank_or_whitespace(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    provider = AnthropicProvider(AnthropicProviderConfig())

    ready, reason = provider_readiness(provider)

    assert ready is False
    assert reason == REASON_PROVIDER_CREDENTIAL_MISSING


def test_anthropic_provider_not_ready_when_sdk_is_not_importable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    monkeypatch.setattr(readiness_module, "find_spec", lambda name: None)
    provider = AnthropicProvider(AnthropicProviderConfig())

    ready, reason = provider_readiness(provider)

    assert ready is False
    assert reason == REASON_PROVIDER_SDK_UNAVAILABLE


def test_unrecognized_provider_class_fails_closed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)

    ready, reason = provider_readiness(_UnrecognizedProvider())

    assert ready is False
    assert reason == REASON_PROVIDER_UNRECOGNIZED


def test_credential_value_never_appears_in_the_readiness_result(monkeypatch):
    """Adversarial no-leak check: the credential is read only to test for
    non-blank and must never surface in the returned ``(ready, reason)``
    tuple, however it is stringified.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    provider = AnthropicProvider(AnthropicProviderConfig())

    ready, reason = provider_readiness(provider)

    assert MARKER_API_KEY not in repr((ready, reason))
