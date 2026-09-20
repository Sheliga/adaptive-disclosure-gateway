"""Purely local readiness checks per ``Provider`` implementation (T25 review
finding 2 -- ``GET /ready``).

"Purely local" is a stricter contract than ``GET /health``
(``DisclosureApplicationService.describe_health``), which is already
call-free but exists for richer introspection. Nothing in this module may:

- open a network connection or make a provider ``generate()`` call;
- construct an SDK client (``AnthropicProvider`` builds its client lazily on
  first use -- this module never triggers that);
- log, return or interpolate a credential's value into anything -- only
  whether the named environment variable is set to a non-blank value is
  ever tested, and the value itself is discarded immediately after.

Every "not ready" outcome carries one closed-vocabulary reason code, never
free text -- see ``application.wire.ReadinessReason`` for the fixed enum
``GET /ready``'s response model validates these strings against.

Lives in ``providers/`` rather than ``application/`` because knowing what
"ready" means for a specific provider implementation (which environment
variable carries its credential, whether its SDK package is importable) is
exactly the kind of provider-shaped knowledge ``providers/settings.py`` and
``providers/anthropic_api.py`` already hold --
``DisclosureApplicationService.describe_readiness`` delegates to
``provider_readiness`` below instead of duplicating that knowledge at the
application layer. This module imports nothing from ``policy``/``vault``/
``detection`` (``tests/test_provider_isolation.py``'s import wall), exactly
like every other module in this package.

An unrecognized ``Provider`` implementation fails closed
(``REASON_PROVIDER_UNRECOGNIZED``) rather than being assumed ready: a future
provider must add itself here deliberately, matching the same fail-closed
posture ``DisclosureApplicationService._refuse_unsafe_control_outside_the_trust_boundary``
already applies to an unrecognized provider class.
"""

from __future__ import annotations

import os
from importlib.util import find_spec

from .anthropic_api import AnthropicProvider
from .base import Provider
from .fake import FakeProvider

REASON_PROVIDER_CREDENTIAL_MISSING = "provider_credential_missing"
REASON_PROVIDER_SDK_UNAVAILABLE = "provider_sdk_unavailable"
REASON_PROVIDER_UNRECOGNIZED = "provider_unrecognized"

_ANTHROPIC_SDK_MODULE_NAME = "anthropic"


def _anthropic_provider_readiness(provider: AnthropicProvider) -> tuple[bool, str | None]:
    """``AnthropicProvider`` is ready only when its credential environment
    variable (``provider.config.api_key_env_var``) is set to a non-blank
    value and the ``anthropic`` package is importable.

    ``AnthropicProviderConfig.__post_init__`` already validated the rest of
    the configuration (model id, effort, thinking mode, timeout, ...) at
    construction time -- this function does not repeat those checks.

    The credential is read only to test ``str.strip()`` truthiness and is
    never stored, returned or otherwise retained.
    """
    api_key = os.getenv(provider.config.api_key_env_var)
    if api_key is None or not api_key.strip():
        return False, REASON_PROVIDER_CREDENTIAL_MISSING
    if find_spec(_ANTHROPIC_SDK_MODULE_NAME) is None:
        return False, REASON_PROVIDER_SDK_UNAVAILABLE
    return True, None


def provider_readiness(provider: Provider) -> tuple[bool, str | None]:
    """``(ready, reason)`` for one wired ``Provider``, computed with no
    network access, no SDK client construction and no ``generate()`` call.

    ``FakeProvider`` is always ready -- it is deterministic, in-process, and
    needs no credential. Any provider type this function does not
    recognize -- including a future, not-yet-added implementation -- is
    refused rather than assumed ready.
    """
    if isinstance(provider, FakeProvider):
        return True, None
    if isinstance(provider, AnthropicProvider):
        return _anthropic_provider_readiness(provider)
    return False, REASON_PROVIDER_UNRECOGNIZED
