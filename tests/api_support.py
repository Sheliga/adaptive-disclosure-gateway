"""Shared fixtures for the T20 / issue #28 slice-2 HTTP adapter tests
(``tests/test_api_*.py``).

Deliberately named without a ``test_`` prefix so pytest never collects it as
a test module on its own -- mirrors ``tests/telemetry_assertions.py``.

Every helper builds a real ``DisclosureApplicationService`` (real core, real
policies, real detector) wired to a fixture provider -- only the provider is
ever a stub, exactly like ``tests/test_application_service.py``'s own style.
Tests always inject their own service into ``create_app`` -- never the
environment-driven default demo service -- so nothing here depends on the
environment either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from adaptive_disclosure_gateway.api.app import create_app
from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.domain import GovernanceContext
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import (
    FakeProvider,
    ProviderRequest,
    ProviderResponse,
    count_transmitted_bytes,
)

POLICY_DIR = Path(__file__).parent.parent / "configs" / "policies"
EXAMPLES_DIR = Path(__file__).parent.parent / "corpus" / "hr" / "v1" / "cases"

HR_TEXT = "Employee: Ana Souza\nCPF: 123.456.789-09\nSalary: R$ 8500.00\nDepartment: Engineering\n"
HR_TEXT_WITH_MEDICAL = HR_TEXT + "Medical notes: Reports chronic migraine.\n"


def policy_repository() -> PolicyRepository:
    return PolicyRepository.from_directory(POLICY_DIR)


def default_context(**overrides) -> GovernanceContext:
    values = {
        "domain": "hr",
        "purpose": "team_summary",
        "policy_version": "hr-v1",
        "provider_class": "fake",
        "requester_role": "hr_analyst",
        "session_id": "demo-session",
    }
    values.update(overrides)
    return GovernanceContext(**values)


@dataclass
class NeverCallMeProvider:
    """A provider whose ``generate`` must never be invoked -- used to prove
    ``POST /disclosure/preview`` never reaches the provider boundary.
    """

    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise AssertionError("preview must never call the provider")


@dataclass
class RecordingProvider:
    """Records every ``ProviderRequest`` it receives; used to prove the
    payload the treatment decided to disclose reaches the provider
    unchanged.
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


def build_service(
    provider=None, *, examples_directory: Path | None = EXAMPLES_DIR, **context_overrides
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=policy_repository(),
        provider=provider if provider is not None else FakeProvider(),
        default_context=default_context(**context_overrides),
        examples_directory=examples_directory,
    )


def build_client(service: DisclosureApplicationService, **create_app_kwargs) -> TestClient:
    app = create_app(service=service, **create_app_kwargs)
    return TestClient(app)
