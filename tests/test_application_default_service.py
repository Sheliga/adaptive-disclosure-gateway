"""The default/deployed service construction (T20 / issue #28's
demo-integration slice; issue #41 gate A, blocker 5).

``build_default_service`` is what ``api/app.create_app()`` and ``cli.main()``
build when no service is injected -- i.e. what a real deployment actually
runs. Until this slice it hardcoded ``FakeProvider`` and a
``provider_class="fake"`` governance context, so the only way to run the
hosted demo against the real T22 adapter was to hand-inject a custom service.

What these tests exist to catch:

- ``ADG_PROVIDER=anthropic`` silently still running on ``FakeProvider``, so a
  demo believed to be hitting the real model is not (the no-silent-fallback
  rule of ``docs/research/post-pilot-protocol-v1.md`` section 9.4);
- the default ``GovernanceContext`` keeping ``provider_class="fake"`` while
  the wired provider declares ``external_llm`` -- a mismatch that fails
  closed at every single provider call, making the deployment look broken
  rather than misconfigured;
- the inverse: a governance context claiming ``external_llm`` over a
  deterministic ``FakeProvider``, which would let policy apply the *external*
  rules to a call that never leaves the process;
- an unrecognized ``ADG_PROVIDER`` value being coerced back to the default;
- the API credential reaching the constructed service, its provider, or its
  health record.
"""

from __future__ import annotations

import json

import pytest

from adaptive_disclosure_gateway.application.settings import (
    build_default_service,
    default_governance_context,
)
from adaptive_disclosure_gateway.providers import (
    AnthropicProvider,
    FakeProvider,
    ProviderConfigurationError,
)

MARKER_API_KEY = "sk-ant-marker-DO-NOT-LEAK-9f3b2a1c"


def test_the_default_service_uses_the_deterministic_fake_provider_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)

    health = build_default_service().describe_health()

    assert health.provider_class == "fake"
    assert health.deterministic_demo_mode is True


def test_the_default_service_uses_the_real_adapter_when_adg_provider_selects_it(monkeypatch):
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")

    service = build_default_service()
    health = service.describe_health()

    assert health.provider_class == "external_llm"
    assert health.deterministic_demo_mode is False


def test_the_default_governance_context_provider_class_matches_the_configured_provider(monkeypatch):
    """The load-bearing one. ``invoke_provider`` compares
    ``context.provider_class`` against the provider's own and refuses the
    call on a mismatch, so a hardcoded ``"fake"`` here would block every
    real-provider request in the deployed demo.
    """
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    real_service = build_default_service()

    monkeypatch.setenv("ADG_PROVIDER", "fake")
    fake_service = build_default_service()

    assert (
        default_governance_context(provider_class="external_llm").provider_class == "external_llm"
    )
    # Reading the private attribute deliberately: the whole point of this
    # test is that the two halves of the constructed service agree, and no
    # public surface exposes the default context.
    assert real_service._default_context.provider_class == AnthropicProvider.provider_class
    assert fake_service._default_context.provider_class == FakeProvider().provider_class


def test_an_unrecognized_provider_name_fails_closed_rather_than_falling_back(monkeypatch):
    monkeypatch.setenv("ADG_PROVIDER", "anthrpic")

    with pytest.raises(ProviderConfigurationError):
        build_default_service()


def test_the_constructed_service_carries_no_api_credential(monkeypatch):
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)

    service = build_default_service()
    health = service.describe_health()

    assert MARKER_API_KEY not in repr(service)
    assert MARKER_API_KEY not in repr(service._provider)
    assert MARKER_API_KEY not in repr(health)
    assert MARKER_API_KEY not in json.dumps(
        service._provider.configuration_record(), default=str, sort_keys=True
    )


def test_selecting_the_real_provider_builds_no_client_and_makes_no_call(monkeypatch):
    """Construction must stay offline and credential-free: the SDK client is
    built lazily at the first ``generate``, so a deployment can start up and
    serve ``/health`` with no key configured and fail closed only when a
    call is actually attempted.
    """
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    service = build_default_service()

    assert service.describe_health().provider_class == "external_llm"
