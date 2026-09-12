"""Environment-driven configuration for the default demo
``DisclosureApplicationService`` shared by every adapter (T20 / issue #28,
slice 3: the CLI adapter).

``api/app.py``'s ``create_app()`` and ``cli.py``'s ``main()`` both need to
build the identical default service when no service is injected -- the same
real policy repository and HR pilot examples from this checkout, the same
deterministic ``FakeProvider``, the same default ``GovernanceContext``. This
was previously ``api/settings.py``/``api/app._build_default_service``, which
made it unreachable from the CLI without importing ``adaptive_disclosure_gateway.api``
(and therefore ``fastapi``, transitively, via ``api/__init__.py`` -- a hard
constraint this ticket's CLI adapter must not violate). Moving the
env-reading functions and ``build_default_service`` here, one level below
both adapters, means each adapter calls the same function instead of
maintaining two independently-drifting copies of "how is the default demo
service built" -- exactly this ticket's "no duplicated logic" rule.

Every value here has a safe, repository-relative default so the demo runs
out of the box in a fresh checkout with no environment configured at all; a
real deployment overrides paths/governance defaults through these env vars
instead of editing code. Tests never depend on any of this: they always
construct and inject their own ``DisclosureApplicationService``, so nothing
here is on the path of any test in this slice.

``allowed_origins()`` (HTTP CORS configuration) deliberately stays in
``api/settings.py`` -- it is HTTP-specific and the CLI has no equivalent
concept.
"""

from __future__ import annotations

import os
from pathlib import Path

from adaptive_disclosure_gateway.application.service import DisclosureApplicationService
from adaptive_disclosure_gateway.domain import GovernanceContext
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.providers import build_provider_from_env

# src/adaptive_disclosure_gateway/application/settings.py -> repo root is 3
# parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_POLICY_DIR = _REPO_ROOT / "configs" / "policies"
DEFAULT_EXAMPLES_DIR = _REPO_ROOT / "corpus" / "hr" / "v1" / "cases"


def policy_directory() -> Path:
    """``ADG_POLICY_DIR``, or the repository's own ``configs/policies``."""
    value = os.getenv("ADG_POLICY_DIR")
    return Path(value) if value else DEFAULT_POLICY_DIR


def examples_directory() -> Path:
    """``ADG_EXAMPLES_DIR``, or the repository's own frozen HR pilot
    corpus input directory.
    """
    value = os.getenv("ADG_EXAMPLES_DIR")
    return Path(value) if value else DEFAULT_EXAMPLES_DIR


def default_governance_context(*, provider_class: str) -> GovernanceContext:
    """The demo's default ``GovernanceContext``, env-overridable field by
    field except for ``provider_class``.

    ``provider_class`` is a required keyword argument with no default, and
    is deliberately NOT read from the environment. It must equal the
    declared class of the ``Provider`` the service is actually constructed
    with: ``providers.invoke_provider`` compares the two and refuses the
    call on a mismatch (``ProviderClassMismatchError``), and policy itself
    reads ``provider_class`` -- ``docs/hr-policy-matrix.md`` treats
    ``employee_name`` more restrictively for ``external_llm`` precisely
    because that call crosses the organizational boundary.

    It used to be hardcoded to ``"fake"``, which meant a deployment wiring
    in the real T22 adapter had to inject an entire custom service to avoid
    blocking every request. Deriving it from the constructed provider (see
    ``build_default_service``) removes that step and makes the two halves
    impossible to configure apart: there is no environment variable that can
    make the context disagree with the provider.

    The domain/purpose/policy defaults stay HR: the shipped
    ``examples_directory`` is the HR pilot corpus, and the Contracts demo
    path never relies on them -- an uploaded document selects its governance
    explicitly through ``application/presets.py`` (see
    ``DisclosureApplicationService.build_document_request``).
    """
    return GovernanceContext(
        domain=os.getenv("ADG_DEFAULT_DOMAIN", "hr"),
        purpose=os.getenv("ADG_DEFAULT_PURPOSE", "team_summary"),
        policy_version=os.getenv("ADG_DEFAULT_POLICY_VERSION", "hr-v1"),
        provider_class=provider_class,
        requester_role=os.getenv("ADG_DEFAULT_REQUESTER_ROLE", "hr_analyst"),
        session_id=os.getenv("ADG_DEFAULT_SESSION_ID", "demo-session"),
    )


def build_default_service() -> DisclosureApplicationService:
    """The default demo service every adapter builds when no service is
    injected: the real policy repository and HR pilot examples from this
    checkout, the provider ``ADG_PROVIDER`` selects, and a default
    ``GovernanceContext`` whose ``provider_class`` is derived from that
    provider.

    The provider comes from ``providers.build_provider_from_env`` -- the one
    place provider selection lives (T22 / issue #30). It returns a
    deterministic ``FakeProvider`` unless ``ADG_PROVIDER`` explicitly names
    the real adapter (issue #29 requires the fake mode be clearly labeled --
    see ``ServiceHealth.deterministic_demo_mode``), and raises on an
    unrecognized value rather than falling back to ``FakeProvider``. This
    function adds no fallback of its own: a misconfigured deployment fails
    to start instead of quietly serving synthetic answers.

    Selecting the real adapter builds no SDK client and reads no credential
    here -- ``AnthropicProvider`` constructs its client lazily at the first
    call, so an API without a key configured still starts and still serves
    ``/health``, and fails closed only when a call is actually attempted.
    """
    provider = build_provider_from_env()
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(policy_directory()),
        provider=provider,
        default_context=default_governance_context(provider_class=provider.provider_class),
        examples_directory=examples_directory(),
    )
