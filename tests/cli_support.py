"""Shared fixtures for the T20 / issue #28 slice-3 CLI adapter tests
(``tests/test_cli_*.py``).

Deliberately named without a ``test_`` prefix so pytest never collects it as
a test module on its own -- mirrors ``tests/api_support.py`` and
``tests/telemetry_assertions.py``.

Deliberately does NOT import ``tests.api_support`` or anything under
``adaptive_disclosure_gateway.api`` at module scope: most CLI tests must
prove the CLI works without ``fastapi`` conceptually available to it, and
importing ``api_support`` here would pull ``fastapi`` into every CLI test's
import graph regardless. The one test that legitimately needs both
(comparing CLI and HTTP output) imports ``tests.api_support`` itself,
directly, exactly as its own docstring explains.

Every helper builds a real ``DisclosureApplicationService`` (real core, real
policies, real detector) wired to a fixture provider -- only the provider is
ever a stub, exactly like ``tests/test_application_service.py``'s own style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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

SENSITIVE_NAME = "Ana Souza"
SENSITIVE_CPF = "123.456.789-09"
MAPPING_SHAPED = "Ana Souza:"


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
    ``preview`` never reaches the provider boundary, from the CLI too.
    """

    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise AssertionError("preview must never call the provider")


@dataclass
class RecordingProvider:
    """Records every ``ProviderRequest`` it receives; used to prove the
    payload the treatment decided to disclose reaches the provider
    unchanged, and to count calls.
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
class FailingProvider:
    """A provider whose ``generate`` always raises -- used to prove
    ``execute`` reports a failed provider call as a recorded outcome
    (exit 0) rather than an unexpected CLI error.
    """

    provider_class: str = "fake"

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise RuntimeError("simulated provider failure")


def build_service(
    provider=None,
    *,
    examples_directory: Path | None = EXAMPLES_DIR,
    restore_handle_sealer=None,
    **context_overrides,
) -> DisclosureApplicationService:
    return DisclosureApplicationService(
        policy_repository=policy_repository(),
        provider=provider if provider is not None else FakeProvider(),
        default_context=default_context(**context_overrides),
        examples_directory=examples_directory,
        restore_handle_sealer=restore_handle_sealer,
    )
