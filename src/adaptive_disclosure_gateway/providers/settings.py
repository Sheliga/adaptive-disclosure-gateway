"""Environment-driven provider selection and real-provider configuration
(T22 / issue #30).

Follows the same shape as ``application/settings.py``: plain functions that
read ``ADG_*`` environment variables, every one with a safe default, so a
fresh checkout runs offline with no environment configured at all. The
default is, and stays, ``FakeProvider`` -- ``provider_name()`` returns
``"fake"`` unless ``ADG_PROVIDER`` explicitly says otherwise. Nothing here
switches the global default provider; a caller that wants the real one asks
for it (``build_provider_from_env``) or constructs it directly.

**No credential lives in this module or in the configuration object it
builds.** ``AnthropicProviderConfig`` carries only the *name* of the
environment variable to read (``api_key_env_var``), never the key itself, so
the key cannot reach a repr, a dataclass serialization, an artifact, an
audit record or a manifest by construction rather than by remembering to
strip it. The key is read from the environment at client-construction time
and handed straight to the SDK client -- see ``anthropic_api.py``.

This module is deliberately free of any policy/vault/detection import (see
``tests/test_provider_isolation.py``): provider configuration is transport
configuration, and must not become a second place where governance
decisions are made.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# The default provider everywhere: deterministic, offline, no credential.
# TDD, CI, the pilot/development corpora and every regression test run on
# this. Changing this constant is a methodological change, not a config
# tweak -- see docs/research/post-pilot-protocol-v1.md §9.
DEFAULT_PROVIDER_NAME = "fake"
ANTHROPIC_PROVIDER_NAME = "anthropic"

# Exact model id, never date-suffixed.
DEFAULT_ANTHROPIC_MODEL_ID = "claude-opus-5"

# Model ids this adapter version has actually verified end-to-end: sampling
# parameters (removed and rejected), thinking, effort, max_tokens, response
# shape and usage metadata. This allowlist exists for reproducibility and
# methodology, not because the shared ``Provider`` protocol architecturally
# limits which models could be called -- see anthropic_api.py's module
# docstring. `AnthropicProviderConfig.__post_init__` refuses any other
# model id at construction time: an older or unvalidated model id would
# make this adapter's recorded decoding_config/sampling provenance a false
# claim, verified only for the models actually checked here. Extend this
# set only after independently verifying a new id against all six
# properties above -- never merely because "the API will validate it
# later".
SUPPORTED_ANTHROPIC_MODEL_IDS = frozenset({DEFAULT_ANTHROPIC_MODEL_ID})

# The environment variable the Anthropic SDK itself documents. Named here
# (not embedded in the adapter) so a deployment can point the adapter at a
# differently-named variable without the key ever becoming a config value.
DEFAULT_API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"

# Effort levels current models accept (``output_config.effort``).
VALID_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

# Thinking modes this adapter supports. "adaptive" is the model default on
# Claude Opus 5; "disabled" is accepted by the API only at effort ``high`` or
# below, which ``AnthropicProviderConfig`` validates locally rather than
# discovering as an HTTP 400 mid-batch.
VALID_THINKING_MODES = ("adaptive", "disabled")
_EFFORT_LEVELS_REJECTING_DISABLED_THINKING = ("xhigh", "max")

# Versions the scaffolding this adapter applies to a ProviderRequest. Bump
# this string -- never edit the joining rule silently -- if the mapping from
# (task, payload) to the provider request ever changes: results produced
# under two different scaffolding rules are not comparable, and
# docs/experimental-design.md requires prompt scaffolding held identical
# across the treatments being compared.
PROMPT_SCAFFOLDING_VERSION = "t22-task-then-blank-line-then-payload-v1"

DEFAULT_MAX_OUTPUT_TOKENS = 16000
DEFAULT_EFFORT = "high"
DEFAULT_THINKING_MODE = "adaptive"

# Native transport timeout, in seconds, configured on the SDK client itself
# -- deliberately *in addition* to providers.invoke_provider's caller-side
# wall-clock deadline, which does not and cannot cancel an in-flight HTTP
# request (it abandons the worker thread). Both layers are required by
# issue #30.
DEFAULT_ANTHROPIC_TIMEOUT_SECONDS = 60.0


class ProviderConfigurationError(ValueError):
    """Raised when provider configuration is internally inconsistent.

    A plain ``ValueError`` subclass, not a ``ProviderError``: this is a
    misconfiguration detected before any call exists, not a failed provider
    call. It must surface loudly at construction time rather than becoming
    an HTTP 400 discovered part-way through a batch.
    """


@dataclass(frozen=True)
class AnthropicProviderConfig:
    """Everything the Anthropic adapter needs, and nothing else.

    Deliberately narrow -- no governance context, no policy version, no
    corpus identity, and above all no credential. ``api_key_env_var`` names
    the environment variable the key is read from at client-construction
    time; the key itself never becomes an attribute of this object, so
    ``repr()``/``dataclasses.asdict()``/``json.dumps`` of a config are safe
    to write into a manifest or a log line.

    ``temperature``/``top_p``/``top_k`` are absent on purpose and must not
    be added: current models (Claude Opus 5, Sonnet 5, Opus 4.8/4.7 and the
    Fable family) removed the sampling parameters and return HTTP 400 if one
    is sent. See ``anthropic_api.py``'s module docstring for what that costs
    this experiment methodologically.
    """

    model_id: str = DEFAULT_ANTHROPIC_MODEL_ID
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    effort: str = DEFAULT_EFFORT
    thinking_mode: str = DEFAULT_THINKING_MODE
    timeout_seconds: float = DEFAULT_ANTHROPIC_TIMEOUT_SECONDS
    base_url: str | None = None
    api_key_env_var: str = DEFAULT_API_KEY_ENV_VAR

    def __post_init__(self) -> None:
        if self.model_id not in SUPPORTED_ANTHROPIC_MODEL_IDS:
            raise ProviderConfigurationError(
                "model_id is not in this adapter's validated allowlist "
                f"({sorted(SUPPORTED_ANTHROPIC_MODEL_IDS)!r}); only ids whose sampling, "
                "thinking, effort, max_tokens, response-shape and usage-metadata semantics "
                "have been independently verified for this adapter version are accepted"
            )
        if self.base_url is not None:
            # Two batches could both record base_url_overridden=true and
            # still have hit different backends -- insufficient provenance,
            # and a gateway/proxy introduces a new, unrecorded experimental
            # variable. Forbidden outright for this adapter rather than
            # attempting to record it faithfully. Never interpolate the
            # attempted value here: a URL can carry an embedded credential
            # (userinfo, query string, token path) and this message must
            # not become a new side channel for it.
            raise ProviderConfigurationError(
                "base_url override is not supported by this adapter; the official "
                "Anthropic endpoint is used unconditionally (see docs/provider-configuration.md)"
            )
        if self.effort not in VALID_EFFORT_LEVELS:
            raise ProviderConfigurationError(
                f"effort must be one of {VALID_EFFORT_LEVELS!r}, not {self.effort!r}"
            )
        if self.thinking_mode not in VALID_THINKING_MODES:
            raise ProviderConfigurationError(
                f"thinking_mode must be one of {VALID_THINKING_MODES!r}, not {self.thinking_mode!r}"
            )
        if (
            self.thinking_mode == "disabled"
            and self.effort in _EFFORT_LEVELS_REJECTING_DISABLED_THINKING
        ):
            raise ProviderConfigurationError(
                "disabled thinking is rejected by the API at effort "
                f"{self.effort!r}; use effort 'high' or below, or adaptive thinking"
            )
        if self.max_output_tokens <= 0:
            raise ProviderConfigurationError("max_output_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ProviderConfigurationError("timeout_seconds must be positive")


def provider_name() -> str:
    """``ADG_PROVIDER``, normalized (lowercased and stripped), defaulting to
    ``"fake"`` when unset, empty or whitespace-only.

    This performs no validation that the normalized value actually names a
    known provider -- an unrecognized non-empty value is returned verbatim.
    ``build_provider_from_env`` is what fails closed on that case
    (``ProviderConfigurationError``); it must never be silently coerced to
    ``"fake"`` here, or a batch planned for the real provider could execute
    on FakeProvider without anyone noticing (post-pilot-protocol-v1 section
    9.4's no-silent-fallback rule).
    """
    value = (os.getenv("ADG_PROVIDER") or "").strip().lower()
    return value or DEFAULT_PROVIDER_NAME


def real_provider_enabled() -> bool:
    """True only when ``ADG_PROVIDER`` explicitly names the real adapter."""
    return provider_name() == ANTHROPIC_PROVIDER_NAME


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        raise ProviderConfigurationError(f"{name} must be a number of seconds") from None


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ProviderConfigurationError(f"{name} must be an integer") from None


def anthropic_config_from_env() -> AnthropicProviderConfig:
    """Build an ``AnthropicProviderConfig`` from ``ADG_ANTHROPIC_*``
    environment variables, each with the module default above.

    Never reads the API key: only ``ADG_ANTHROPIC_API_KEY_ENV_VAR``, the
    *name* of the variable holding it.
    """
    return AnthropicProviderConfig(
        model_id=os.getenv("ADG_ANTHROPIC_MODEL_ID") or DEFAULT_ANTHROPIC_MODEL_ID,
        max_output_tokens=_int_env("ADG_ANTHROPIC_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS),
        effort=os.getenv("ADG_ANTHROPIC_EFFORT") or DEFAULT_EFFORT,
        thinking_mode=os.getenv("ADG_ANTHROPIC_THINKING") or DEFAULT_THINKING_MODE,
        timeout_seconds=_float_env(
            "ADG_ANTHROPIC_TIMEOUT_SECONDS", DEFAULT_ANTHROPIC_TIMEOUT_SECONDS
        ),
        base_url=os.getenv("ADG_ANTHROPIC_BASE_URL") or None,
        api_key_env_var=os.getenv("ADG_ANTHROPIC_API_KEY_ENV_VAR") or DEFAULT_API_KEY_ENV_VAR,
    )


def build_provider_from_env():
    """The provider an adapter/script should use, per ``ADG_PROVIDER``.

    Returns a ``FakeProvider`` when ``ADG_PROVIDER`` is unset, empty,
    whitespace-only, or explicitly ``"fake"``; returns the real adapter only
    when it explicitly names ``"anthropic"``. Any other non-empty value --
    in particular a typo such as ``"anthrpic"`` -- raises
    ``ProviderConfigurationError`` rather than silently falling back to
    ``FakeProvider``. That fallback used to happen for *any* unrecognized
    value, which could make a run planned as real-provider silently execute
    on FakeProvider instead: exactly the silent substitution
    post-pilot-protocol-v1 section 9.4 forbids. This function never guesses
    or autocorrects a misspelled name and never substitutes a different
    provider on its own judgment -- an unrecognized value is a
    configuration error, full stop.

    Selecting the real provider with no credential configured separately
    fails closed at the first call (``build_anthropic_client``), never by
    degrading to ``FakeProvider``.
    """
    # Imported here rather than at module scope: anthropic_api imports this
    # module for its configuration type, so a top-level import would cycle.
    from .anthropic_api import AnthropicProvider
    from .fake import FakeProvider

    name = provider_name()
    if name == DEFAULT_PROVIDER_NAME:
        return FakeProvider()
    if name == ANTHROPIC_PROVIDER_NAME:
        return AnthropicProvider(anthropic_config_from_env())
    raise ProviderConfigurationError(
        "ADG_PROVIDER names a provider this codebase does not recognize; only "
        f"{DEFAULT_PROVIDER_NAME!r} and {ANTHROPIC_PROVIDER_NAME!r} are supported. An "
        "unrecognized value is rejected rather than silently defaulting to FakeProvider "
        "(post-pilot-protocol-v1 section 9.4's no-silent-fallback rule) -- it is never "
        "autocorrected or mapped to another provider."
    )
