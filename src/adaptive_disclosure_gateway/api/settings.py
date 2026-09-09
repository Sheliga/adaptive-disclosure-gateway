"""Environment-driven configuration for the HTTP adapter (T20 / issue #28,
slice 2), plus a re-export of the default-service configuration shared with
the CLI adapter.

``policy_directory``/``examples_directory``/``default_governance_context``/
``build_default_service`` moved to ``application/settings.py`` in slice 3 (the
CLI adapter) so the CLI can build the identical default demo service without
importing anything under ``adaptive_disclosure_gateway.api`` (and therefore
``fastapi``). They are re-exported verbatim here so ``api/app.py`` and the
existing HTTP API tests keep importing them from this module unchanged --
the same re-export pattern ``experiments/treatments.py`` already uses for
``treatment_factory.build_treatment``.

``allowed_origins`` stays defined here: it is HTTP-specific (CORS) and has
no CLI equivalent.

Never defaults ``allowed_origins`` to ``"*"`` -- issue #28 requires CORS be
deployment-configurable (for T25/#42), and a wildcard origin on an API that
accepts document text would defeat the purpose of making it configurable at
all.
"""

from __future__ import annotations

import os

from adaptive_disclosure_gateway.application.settings import (
    DEFAULT_EXAMPLES_DIR,
    DEFAULT_POLICY_DIR,
    build_default_service,
    default_governance_context,
    examples_directory,
    policy_directory,
)

__all__ = [
    "DEFAULT_EXAMPLES_DIR",
    "DEFAULT_POLICY_DIR",
    "allowed_origins",
    "build_default_service",
    "default_governance_context",
    "examples_directory",
    "policy_directory",
]


def allowed_origins() -> tuple[str, ...]:
    """``ADG_ALLOWED_ORIGINS`` as a comma-separated list, empty by default.

    Empty means no cross-origin caller is allowed -- ``create_app`` never
    substitutes a wildcard for an empty result.
    """
    raw = os.getenv("ADG_ALLOWED_ORIGINS", "")
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())
