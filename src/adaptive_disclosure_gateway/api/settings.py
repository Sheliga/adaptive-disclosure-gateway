"""Environment-driven configuration for the default demo service
``api.app.create_app`` builds when called with no injected service (T20 /
issue #28, slice 2).

Every value here has a safe, repository-relative default so the demo runs
out of the box in a fresh checkout with no environment configured at all; a
real deployment overrides paths/origins/governance defaults through these
env vars instead of editing code. Tests never depend on any of this: they
always construct and inject their own ``DisclosureApplicationService``
(``api.app.create_app(service=...)``), so nothing here is on the path of
any test in this slice.

Never defaults ``allowed_origins`` to ``"*"`` -- issue #28 requires CORS be
deployment-configurable (for T25/#42), and a wildcard origin on an API that
accepts document text would defeat the purpose of making it configurable at
all.
"""

from __future__ import annotations

import os
from pathlib import Path

from adaptive_disclosure_gateway.domain import GovernanceContext

# src/adaptive_disclosure_gateway/api/settings.py -> repo root is 3 parents up.
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


def allowed_origins() -> tuple[str, ...]:
    """``ADG_ALLOWED_ORIGINS`` as a comma-separated list, empty by default.

    Empty means no cross-origin caller is allowed -- ``create_app`` never
    substitutes a wildcard for an empty result.
    """
    raw = os.getenv("ADG_ALLOWED_ORIGINS", "")
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def default_governance_context() -> GovernanceContext:
    """The demo's default ``GovernanceContext``, env-overridable field by
    field. ``provider_class`` is fixed at ``"fake"`` here because it must
    match the default demo provider (``FakeProvider``) this same module's
    caller (``api.app._build_default_service``) constructs -- a deployment
    that wires in a real provider must inject its own service (and its own
    matching ``GovernanceContext``) via ``create_app(service=...)`` rather
    than relying on this default at all.
    """
    return GovernanceContext(
        domain=os.getenv("ADG_DEFAULT_DOMAIN", "hr"),
        purpose=os.getenv("ADG_DEFAULT_PURPOSE", "team_summary"),
        policy_version=os.getenv("ADG_DEFAULT_POLICY_VERSION", "hr-v1"),
        provider_class="fake",
        requester_role=os.getenv("ADG_DEFAULT_REQUESTER_ROLE", "hr_analyst"),
        session_id=os.getenv("ADG_DEFAULT_SESSION_ID", "demo-session"),
    )
