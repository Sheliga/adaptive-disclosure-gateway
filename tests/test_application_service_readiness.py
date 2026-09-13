"""``DisclosureApplicationService.describe_readiness()`` (T25 review finding
2 -- ``GET /ready``): purely local readiness, combining
``providers.readiness.provider_readiness`` with the one check that belongs
at this layer -- whether this service's own preview-confirmation signer is
durable when the wired provider is outside the trust boundary.

Never starts Docker, never touches the network, never constructs an SDK
client.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adaptive_disclosure_gateway.application.preview_confirmation import (
    REASON_CONFIRMATION_SECRET_NOT_DURABLE,
    PreviewConfirmationSigner,
)
from adaptive_disclosure_gateway.application.restore_handle import RestoreHandleSealer
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.domain import GovernanceContext
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    REASON_PROVIDER_CREDENTIAL_MISSING,
    REASON_PROVIDER_SDK_UNAVAILABLE,
    REASON_PROVIDER_UNRECOGNIZED,
    AnthropicProvider,
    AnthropicProviderConfig,
    FakeProvider,
)
from adaptive_disclosure_gateway.providers import readiness as readiness_module

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"
DURABLE_SECRET = "a" * 32
MARKER_API_KEY = "sk-ant-marker-readiness-service-test"


class _UnrecognizedProvider:
    provider_class = "mystery"

    def generate(self, request):  # pragma: no cover -- never invoked
        raise AssertionError("describe_readiness must never call generate()")


def _context(provider_class: str) -> GovernanceContext:
    return GovernanceContext(
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
        provider_class=provider_class,
        requester_role="hr_analyst",
        session_id="demo-session",
    )


def _service(provider, *, signer=None, restore_handle_sealer=None) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(POLICY_DIR),
        provider=provider,
        default_context=_context(provider.provider_class),
        preview_confirmation_signer=signer,
        restore_handle_sealer=restore_handle_sealer,
    )


def test_fake_provider_is_ready_even_with_an_ephemeral_signer():
    service = _service(FakeProvider(), signer=PreviewConfirmationSigner.with_ephemeral_secret())

    readiness = service.describe_readiness()

    assert readiness.ready is True
    assert readiness.reason is None


def test_anthropic_provider_ready_with_credential_and_durable_signer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    service = _service(
        AnthropicProvider(AnthropicProviderConfig()),
        signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
    )

    readiness = service.describe_readiness()

    assert readiness.ready is True
    assert readiness.reason is None


def test_anthropic_provider_not_ready_with_ephemeral_signer_even_with_credential(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    service = _service(
        AnthropicProvider(AnthropicProviderConfig()),
        signer=PreviewConfirmationSigner.with_ephemeral_secret(),
    )

    readiness = service.describe_readiness()

    assert readiness.ready is False
    assert readiness.reason == REASON_CONFIRMATION_SECRET_NOT_DURABLE


def test_anthropic_provider_not_ready_when_credential_missing_regardless_of_signer(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    service = _service(
        AnthropicProvider(AnthropicProviderConfig()),
        signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
    )

    readiness = service.describe_readiness()

    assert readiness.ready is False
    assert readiness.reason == REASON_PROVIDER_CREDENTIAL_MISSING


def test_anthropic_provider_not_ready_when_sdk_unavailable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    monkeypatch.setattr(readiness_module, "find_spec", lambda name: None)
    service = _service(
        AnthropicProvider(AnthropicProviderConfig()),
        signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
    )

    readiness = service.describe_readiness()

    assert readiness.ready is False
    assert readiness.reason == REASON_PROVIDER_SDK_UNAVAILABLE


def test_unrecognized_provider_class_not_ready_regardless_of_signer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    service = _service(
        _UnrecognizedProvider(), signer=PreviewConfirmationSigner(secret=DURABLE_SECRET)
    )

    readiness = service.describe_readiness()

    assert readiness.ready is False
    assert readiness.reason == REASON_PROVIDER_UNRECOGNIZED


def test_describe_readiness_never_calls_the_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    service = _service(
        AnthropicProvider(AnthropicProviderConfig()),
        signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
    )

    service.describe_readiness()  # must not raise -- generate() would assert


@pytest.mark.parametrize("credential", [MARKER_API_KEY])
def test_credential_never_appears_in_the_readiness_result(monkeypatch, credential):
    monkeypatch.setenv("ANTHROPIC_API_KEY", credential)
    service = _service(
        AnthropicProvider(AnthropicProviderConfig()),
        signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
    )

    readiness = service.describe_readiness()

    assert credential not in repr(readiness)


# --- T26 / issue #67 reconciliation: readiness must not depend on the -----------
# restore-handle secret. export/restore fail closed on their OWN routes
# (RestoreUnavailableError, HTTP 503) when no ADG_RESTORE_HANDLE_SECRET is
# configured; that must never make describe_readiness report the whole
# service not-ready. These are regression pins: describe_readiness today
# never even looks at the restore-handle sealer, so both pass immediately --
# they exist to fail the moment a future change wires a restore-availability
# check into readiness (deliberately without adding a new ReadinessReason
# member for it).


def test_fake_provider_ready_regardless_of_restore_handle_secret_being_unset():
    service = _service(FakeProvider(), restore_handle_sealer=RestoreHandleSealer(secret=None))

    readiness = service.describe_readiness()

    assert readiness.ready is True
    assert readiness.reason is None


def test_fake_provider_ready_regardless_of_restore_handle_secret_being_configured():
    service = _service(FakeProvider(), restore_handle_sealer=RestoreHandleSealer(secret="a" * 32))

    readiness = service.describe_readiness()

    assert readiness.ready is True
    assert readiness.reason is None


def test_anthropic_provider_ready_with_credential_and_durable_signer_and_no_restore_secret(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    service = _service(
        AnthropicProvider(AnthropicProviderConfig()),
        signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
        restore_handle_sealer=RestoreHandleSealer(secret=None),
    )

    readiness = service.describe_readiness()

    assert readiness.ready is True
    assert readiness.reason is None
