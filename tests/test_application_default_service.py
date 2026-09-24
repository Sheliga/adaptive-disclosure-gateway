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
  health record;
- a deployment wired to an external provider starting up without the durable
  preview-confirmation key material that makes a document execute provably
  bound to a reviewed preview -- or starting up with that check silently
  switched off;
- the confirmation signing secret reaching a health record, a repr, a
  configuration record or a token.
"""

from __future__ import annotations

import json

import pytest

from adaptive_disclosure_gateway.application.preview_confirmation import (
    PreviewConfirmationConfigurationError,
    PreviewConfirmationError,
    PreviewConfirmationState,
)
from adaptive_disclosure_gateway.application.restore_handle import (
    RestoreHandleConfigurationError,
    RestoreUnavailableError,
)
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
MARKER_CONFIRMATION_SECRET = "confirmation-marker-DO-NOT-LEAK-4e7d1b8a-2c5f"
MARKER_RESTORE_HANDLE_SECRET = "restore-handle-marker-DO-NOT-LEAK-9c2f7a1e-6b3d"


def _confirmation_state() -> PreviewConfirmationState:
    """A minimal approved state, so a signer can be exercised without
    standing up the whole document surface."""
    return PreviewConfirmationState(
        normalized_document="Contracting party: Aurora Servicos Digitais Ltda",
        task="Summarize the obligations of each party.",
        document_type="contract",
        analysis_mode="contract_summary",
        domain="contracts",
        policy_version="contracts-v1",
        purpose="contract_summary",
        requester_role="contract_analyst",
        requested_pseudonym_scope="request",
        governance_provider_class="external_llm",
        provider_class="external_llm",
        strategy="recommended",
        treatment="b4",
        external_payload="Contracting party: PSEUDO-party_name-0001",
    )


def test_the_default_service_uses_the_deterministic_fake_provider_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)

    health = build_default_service().describe_health()

    assert health.provider_class == "fake"
    assert health.deterministic_demo_mode is True


def test_the_default_service_uses_the_real_adapter_when_adg_provider_selects_it(monkeypatch):
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", MARKER_CONFIRMATION_SECRET)

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
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", MARKER_CONFIRMATION_SECRET)
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
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", MARKER_CONFIRMATION_SECRET)
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
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", MARKER_CONFIRMATION_SECRET)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    service = build_default_service()

    assert service.describe_health().provider_class == "external_llm"


# --- preview confirmation is deployment configuration, not an option --------
#
# A deployment that can reach an external provider must be able to prove
# which preview authorised each call. That needs durable key material: a
# per-process secret dies with the worker, so a preview issued by one worker
# would not verify on another, and a restart would invalidate every open
# review. The deployment therefore fails to start rather than serving
# structured uploads it cannot bind.


def test_a_real_provider_deployment_without_a_confirmation_secret_fails_to_start(monkeypatch):
    """The fail-closed direction. Starting *without* confirmation, or with
    it silently disabled, would let a client execute an uploaded contract
    against the real model with no reviewed preview behind it.
    """
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.delenv("ADG_PREVIEW_CONFIRMATION_SECRET", raising=False)

    with pytest.raises(PreviewConfirmationConfigurationError):
        build_default_service()


def test_a_blank_confirmation_secret_is_not_treated_as_configured(monkeypatch):
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", "   ")

    with pytest.raises(PreviewConfirmationConfigurationError):
        build_default_service()


def test_a_confirmation_secret_too_short_to_key_an_hmac_fails_to_start(monkeypatch):
    """Refused rather than accepted as weaker-but-working key material."""
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", "too-short")

    with pytest.raises(PreviewConfirmationConfigurationError):
        build_default_service()


def test_the_development_default_enforces_confirmation_rather_than_disabling_it(monkeypatch):
    """No secret plus the deterministic provider is the one case that
    starts. It must still refuse an execute that no preview authorised --
    generated key material, not a disabled check.
    """
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.delenv("ADG_PREVIEW_CONFIRMATION_SECRET", raising=False)

    signer = build_default_service()._preview_confirmation_signer

    with pytest.raises(PreviewConfirmationError):
        signer.verify("document-preview-confirmation-v1.e30.abc", _confirmation_state())


def test_a_configured_confirmation_secret_survives_across_constructions(monkeypatch):
    """What the ephemeral development signer cannot do, and why a real
    deployment must configure one: a token issued by one process verifies in
    another.
    """
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", MARKER_CONFIRMATION_SECRET)
    state = _confirmation_state()

    issuing = build_default_service()._preview_confirmation_signer
    verifying = build_default_service()._preview_confirmation_signer

    verifying.verify(issuing.issue(state), state)


def test_the_confirmation_secret_reaches_no_health_record_repr_or_token(monkeypatch):
    """The signing secret is key material: it is not a configuration value a
    client, a log line or an audit record may ever see.
    """
    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    monkeypatch.setenv("ADG_PREVIEW_CONFIRMATION_SECRET", MARKER_CONFIRMATION_SECRET)

    service = build_default_service()
    signer = service._preview_confirmation_signer
    rendered = " ".join(
        (
            repr(service),
            repr(signer),
            repr(service.describe_health()),
            json.dumps(service._provider.configuration_record(), default=str, sort_keys=True),
            signer.issue(_confirmation_state()),
        )
    )

    assert MARKER_CONFIRMATION_SECRET not in rendered
    assert MARKER_API_KEY not in rendered


# --- restore handle configuration (T26 / issue #67, D2/D3) -------------------
#
# Unlike the preview-confirmation secret above, an unset restore-handle
# secret is a deliberate, supported state: the deployment must still start
# and serve every other route, with only export/restore themselves failing
# closed at call time.


def test_the_default_service_starts_with_no_restore_handle_secret_and_still_serves_health(
    monkeypatch,
):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.delenv("ADG_RESTORE_HANDLE_SECRET", raising=False)

    service = build_default_service()  # must not raise

    assert service.describe_health().provider_class == "fake"


def test_export_fails_closed_on_the_default_service_with_no_restore_handle_secret(monkeypatch):
    from adaptive_disclosure_gateway.application.contracts import (
        DisclosureApplicationRequest,
        DisclosureStrategy,
        GovernanceOverrides,
    )
    from adaptive_disclosure_gateway.application.ingestion import normalize_text

    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.delenv("ADG_RESTORE_HANDLE_SECRET", raising=False)

    service = build_default_service()
    request = DisclosureApplicationRequest(
        content=normalize_text("Employee: Ana Souza\n"),
        task="summarize",
        strategy=DisclosureStrategy.REVERSIBLE_PSEUDONYMIZATION,
        governance=GovernanceOverrides(),
    )

    with pytest.raises(RestoreUnavailableError):
        service.export(request)


def test_a_configured_restore_handle_secret_survives_across_constructions(monkeypatch):
    """What an unset secret cannot do, and why a deployment that wants
    export/restore must configure one: a handle issued by one process opens
    in another.
    """
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.setenv("ADG_RESTORE_HANDLE_SECRET", MARKER_RESTORE_HANDLE_SECRET)

    issuing_sealer = build_default_service()._restore_handle_sealer
    opening_sealer = build_default_service()._restore_handle_sealer

    issued = issuing_sealer.issue({"PSEUDO-x-" + "0" * 32: "original"})
    assert opening_sealer.open(issued.handle) == {"PSEUDO-x-" + "0" * 32: "original"}


def test_an_unparseable_restore_handle_ttl_fails_closed(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.setenv("ADG_RESTORE_HANDLE_SECRET", MARKER_RESTORE_HANDLE_SECRET)
    monkeypatch.setenv("ADG_RESTORE_HANDLE_TTL_SECONDS", "not-a-number")

    with pytest.raises(RestoreHandleConfigurationError):
        build_default_service()


def test_a_restore_handle_ttl_beyond_seven_days_fails_closed(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.setenv("ADG_RESTORE_HANDLE_SECRET", MARKER_RESTORE_HANDLE_SECRET)
    monkeypatch.setenv("ADG_RESTORE_HANDLE_TTL_SECONDS", str(604800 + 1))

    with pytest.raises(RestoreHandleConfigurationError):
        build_default_service()


def test_the_restore_handle_secret_reaches_no_health_record_or_repr(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.setenv("ADG_RESTORE_HANDLE_SECRET", MARKER_RESTORE_HANDLE_SECRET)

    service = build_default_service()
    sealer = service._restore_handle_sealer
    issued = sealer.issue({"PSEUDO-x-" + "1" * 32: "some original value"})

    rendered = " ".join(
        (repr(service), repr(sealer), repr(service.describe_health()), issued.handle)
    )
    assert MARKER_RESTORE_HANDLE_SECRET not in rendered


# --- demo inspection flag (T27 / issue #69) --------------------------------


def test_the_default_service_has_demo_inspection_disabled_when_unset(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.delenv("ADG_ENABLE_DEMO_INSPECTION", raising=False)

    service = build_default_service()

    assert service._demo_inspection_enabled is False


def test_the_default_service_has_demo_inspection_enabled_when_set_to_one(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)
    monkeypatch.setenv("ADG_ENABLE_DEMO_INSPECTION", "1")

    service = build_default_service()

    assert service._demo_inspection_enabled is True


def test_demo_inspection_does_not_affect_health_or_readiness(monkeypatch):
    monkeypatch.delenv("ADG_PROVIDER", raising=False)

    monkeypatch.delenv("ADG_ENABLE_DEMO_INSPECTION", raising=False)
    disabled = build_default_service()

    monkeypatch.setenv("ADG_ENABLE_DEMO_INSPECTION", "1")
    enabled = build_default_service()

    assert disabled.describe_health() == enabled.describe_health()
    assert disabled.describe_readiness() == enabled.describe_readiness()
