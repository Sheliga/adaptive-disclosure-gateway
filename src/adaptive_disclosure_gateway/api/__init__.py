"""The HTTP adapter for the T20 / issue #28 application boundary (slice 2).

    HTTP route (thin)  ->  DisclosureApplicationService  ->  existing core

See ``api/app.py``'s module docstring for the full architecture and
no-leak contract this package implements. Nothing under
``adaptive_disclosure_gateway.application`` or the core (``transformations``,
``pipeline``, ``domain``, ``policies``, ``providers``, ``detection``,
``vault``, ``audit``, ``experiments``, ``corpus``) may import from this
package or from ``fastapi``/``starlette`` -- the dependency arrow points one
way only, pinned by ``tests/test_api_architecture.py``.
"""

from __future__ import annotations

from adaptive_disclosure_gateway.api.app import create_app
from adaptive_disclosure_gateway.api.schemas import CONTRACT_VERSION

__all__ = ["CONTRACT_VERSION", "create_app"]
