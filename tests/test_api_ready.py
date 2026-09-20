"""T25 review finding 2: ``GET /ready``.

Distinct from ``GET /health`` (``tests/test_api_health.py``): ``/ready`` is a
purely local readiness probe -- no network call, no provider call, no SDK
client construction -- and returns 503 (not 200) when not ready, so a
container healthcheck/orchestrator can act on the status code directly.
"""

from __future__ import annotations

import logging

from adaptive_disclosure_gateway.application.presets import CONTRACT_DOCUMENT_TYPE
from adaptive_disclosure_gateway.application.preview_confirmation import PreviewConfirmationSigner
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.domain import GovernanceContext
from adaptive_disclosure_gateway.providers import (
    AnthropicProvider,
    AnthropicProviderConfig,
    FakeProvider,
)
from adaptive_disclosure_gateway.providers import readiness as readiness_module
from tests.api_support import build_client, policy_repository
from tests.contracts_fixture import CONTRACTS_FIXTURE
from tests.test_api_documents_export_restore import CONTRACT_TASK
from tests.test_application_document_presets import StubContractParser
from tests.test_application_service_readiness import _UnrecognizedProvider

DURABLE_SECRET = "b" * 32
MARKER_API_KEY = "sk-ant-marker-api-ready-test"
MARKER_CONFIRMATION_SECRET = "c" * 32


def _context(provider_class: str) -> GovernanceContext:
    return GovernanceContext(
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
        provider_class=provider_class,
        requester_role="hr_analyst",
        session_id="demo-session",
    )


def _service(provider, *, signer=None) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=policy_repository(),
        provider=provider,
        default_context=_context(provider.provider_class),
        preview_confirmation_signer=signer,
    )


def test_ready_reports_200_ready_for_fake_provider():
    client = build_client(_service(FakeProvider()))

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_reports_200_for_anthropic_with_credential_and_durable_signer(monkeypatch):
    # The `anthropic` package is an optional extra (pyproject.toml) -- the
    # baseline dev/test/CI environment never installs it. Patching find_spec
    # on the readiness module exercises the "SDK importable" branch through
    # the same hook tests/test_providers_readiness.py's negative SDK test
    # already uses, without depending on whether `anthropic` happens to be
    # installed in whatever environment runs the suite.
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    monkeypatch.setattr(readiness_module, "find_spec", lambda name: object())
    client = build_client(
        _service(
            AnthropicProvider(AnthropicProviderConfig()),
            signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
        )
    )

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_reports_503_when_credential_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = build_client(
        _service(
            AnthropicProvider(AnthropicProviderConfig()),
            signer=PreviewConfirmationSigner(secret=DURABLE_SECRET),
        )
    )

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["reason"] == "provider_credential_missing"


def test_ready_reports_503_for_ephemeral_signer_with_external_provider(monkeypatch):
    # See the comment on test_ready_reports_200_for_anthropic_with_credential_and_durable_signer
    # above: needs the SDK to be considered importable so the ephemeral-signer
    # check below is the thing actually under test.
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    monkeypatch.setattr(readiness_module, "find_spec", lambda name: object())
    client = build_client(
        _service(
            AnthropicProvider(AnthropicProviderConfig()),
            signer=PreviewConfirmationSigner.with_ephemeral_secret(),
        )
    )

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["reason"] == "confirmation_secret_not_durable"


def test_ready_and_health_ok_while_export_and_restore_refuse_in_the_same_app():
    """T26 / issue #67 reconciliation. A single app instance, no
    ``ADG_RESTORE_HANDLE_SECRET`` configured (the default -- the service
    below never receives a ``restore_handle_sealer``, so
    ``DisclosureApplicationService`` falls back to
    ``RestoreHandleSealer(secret=None)``): ``/ready`` and ``/health`` must
    both report healthy while ``/documents/export`` and
    ``/documents/restore`` -- on that exact same app -- both refuse with
    503. Proves the two facts live in the same running service without
    coupling: a defect that made ``describe_readiness`` consult the restore
    sealer would flip ``/ready`` to 503 here even though nothing about the
    provider or preview-confirmation signer changed.
    """
    service = DisclosureApplicationService(
        policy_repository=policy_repository(),
        provider=FakeProvider(),
        default_context=_context("fake"),
        document_parser=StubContractParser(),
    )
    client = build_client(service)

    ready_response = client.get("/ready")
    health_response = client.get("/health")
    export_response = client.post(
        "/documents/export",
        files={"file": ("contract.pdf", CONTRACTS_FIXTURE.encode("utf-8"), "application/pdf")},
        data={"task": CONTRACT_TASK, "document_type": CONTRACT_DOCUMENT_TYPE},
    )
    restore_response = client.post(
        "/documents/restore", json={"text": "irrelevant", "restore_handle": "irrelevant"}
    )

    assert ready_response.status_code == 200
    assert ready_response.json() == {"status": "ready"}
    assert health_response.status_code == 200
    assert export_response.status_code == 503
    assert restore_response.status_code == 503


def test_ready_reports_503_for_unrecognized_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    client = build_client(
        _service(_UnrecognizedProvider(), signer=PreviewConfirmationSigner(secret=DURABLE_SECRET))
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["reason"] == "provider_unrecognized"


class TestReadyNoLeak:
    """Adversarial no-leak check (CLAUDE.md): the credential and the
    confirmation secret must never surface through ``/ready`` -- in its
    response body, in logs, or (transitively, through ``/health`` too, since
    both share the same wired service) anywhere else on this boundary.
    """

    def test_neither_sentinel_appears_in_ready_or_health_bodies_or_logs(self, monkeypatch, caplog):
        monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
        service = _service(
            AnthropicProvider(AnthropicProviderConfig()),
            signer=PreviewConfirmationSigner(secret=MARKER_CONFIRMATION_SECRET),
        )
        client = build_client(service)

        with caplog.at_level(logging.DEBUG):
            ready_response = client.get("/ready")
            health_response = client.get("/health")

        haystack = f"{ready_response.text}\n{health_response.text}\n{caplog.text}"
        assert MARKER_API_KEY not in haystack
        assert MARKER_CONFIRMATION_SECRET not in haystack
        assert "ANTHROPIC_API_KEY" not in ready_response.text
        assert "ANTHROPIC_API_KEY" not in health_response.text

    def test_neither_sentinel_appears_for_the_not_ready_path(self, monkeypatch, caplog):
        monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
        service = _service(
            AnthropicProvider(AnthropicProviderConfig()),
            signer=PreviewConfirmationSigner.with_ephemeral_secret(),
        )
        client = build_client(service)

        with caplog.at_level(logging.DEBUG):
            response = client.get("/ready")

        assert response.status_code == 503
        assert MARKER_API_KEY not in response.text
        assert MARKER_API_KEY not in caplog.text
        assert "ANTHROPIC_API_KEY" not in response.text
