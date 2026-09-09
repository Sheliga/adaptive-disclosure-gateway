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
from adaptive_disclosure_gateway.providers import FakeProvider

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


def default_governance_context() -> GovernanceContext:
    """The demo's default ``GovernanceContext``, env-overridable field by
    field. ``provider_class`` is fixed at ``"fake"`` here because it must
    match the default demo provider (``FakeProvider``) ``build_default_service``
    below constructs -- a deployment that wires in a real provider must
    inject its own service (and its own matching ``GovernanceContext``) via
    ``create_app(service=...)``/``cli.main(service=...)`` rather than
    relying on this default at all.
    """
    return GovernanceContext(
        domain=os.getenv("ADG_DEFAULT_DOMAIN", "hr"),
        purpose=os.getenv("ADG_DEFAULT_PURPOSE", "team_summary"),
        policy_version=os.getenv("ADG_DEFAULT_POLICY_VERSION", "hr-v1"),
        provider_class="fake",
        requester_role=os.getenv("ADG_DEFAULT_REQUESTER_ROLE", "hr_analyst"),
        session_id=os.getenv("ADG_DEFAULT_SESSION_ID", "demo-session"),
    )


def build_default_service() -> DisclosureApplicationService:
    """The default demo service every adapter builds when no service is
    injected: the real policy repository and HR pilot examples from this
    checkout, a deterministic ``FakeProvider`` (issue #29 requires this be
    clearly labeled -- see ``ServiceHealth.deterministic_demo_mode``), and a
    documented default ``GovernanceContext``.
    """
    return DisclosureApplicationService(
        policy_repository=PolicyRepository.from_directory(policy_directory()),
        provider=FakeProvider(),
        default_context=default_governance_context(),
        examples_directory=examples_directory(),
    )
