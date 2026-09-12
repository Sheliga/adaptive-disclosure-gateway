"""Real external-LLM adapter: Anthropic's Messages API (T22 / issue #30).

Named ``anthropic_api`` rather than ``anthropic`` so that nothing in this
package -- or a reader of it -- can confuse this module with the third-party
``anthropic`` distribution it wraps.

This is the first non-fake implementation of ``providers.base.Provider``. It
changes nothing about that boundary: it receives a ``ProviderRequest`` and
nothing else, it is invoked only through ``invoke_provider``, it performs no
retry and no fallback, and it never imports policy, vault or detection code
(``tests/test_provider_isolation.py``). ``FakeProvider`` remains the default
everywhere; this adapter is opt-in (``providers/settings.py``).

Credential handling
-------------------
The API key is read from the environment at client-construction time and
handed directly to the SDK client. It is never stored on this object, never
part of ``AnthropicProviderConfig``, never interpolated into an exception
message, a span attribute, a log line or a configuration record, and
``__repr__`` below is explicit precisely so a default dataclass-ish repr can
never start including one.

Error handling
--------------
Every SDK failure is normalized into the existing ``ProviderError`` /
``ProviderTimeoutError`` hierarchy with a fixed, metadata-only reason token
from ``_NORMALIZED_FAILURE_REASONS``, and raised ``from None``. The
third-party exception's own message is never re-raised, wrapped, formatted
or chained: an HTTP client quoting the request body it failed to send would
otherwise put the disclosure-controlled payload into a traceback, which is
exactly the side channel CLAUDE.md's no-leak invariant exists to close.

Classification is by exception *type name* walked over the MRO rather than
by ``isinstance`` against imported SDK classes. That is deliberate: the
``anthropic`` package lives behind an optional extra, so the offline test
suite -- and any checkout that has not installed the extra -- must still be
able to exercise every normalized failure path. Subclass names are reached
before their bases by MRO order, so ``RateLimitError`` classifies as rate
limiting rather than as its ``APIStatusError`` base, and ``APITimeoutError``
as a timeout rather than as its ``APIConnectionError`` base.

Model allowlist
---------------
``AnthropicProviderConfig`` only accepts a ``model_id`` from
``settings.SUPPORTED_ANTHROPIC_MODEL_IDS`` -- currently just the default,
``claude-opus-5``. This exists for reproducibility and methodology, not
because the shared ``Provider`` protocol architecturally limits which
models could be called: the properties this module records as universal
(no sampling parameters, the response/usage shape read by
``_to_provider_response``) were verified against the specific models
listed above, not against every model id the Anthropic API happens to
accept. An older or unvalidated model id could differ on any of those
properties, which would make ``decoding_config``'s
``sampling_parameters_supported: False`` a false provenance claim rather
than a verified one. A model id outside the allowlist is refused at
``AnthropicProviderConfig`` construction, never accepted on the theory
that "the API will validate it later".

Methodological limitation: decoding determinism
-----------------------------------------------
``temperature``, ``top_p`` and ``top_k`` were removed on current models
(Claude Opus 5, Sonnet 5, Opus 4.8/4.7, the Fable family) and return HTTP
400 if sent. **Bit-exact decoding determinism is therefore not configurable
on these models**, and this adapter does not pretend otherwise: it sends no
sampling parameter, and ``decoding_config`` records ``temperature: None``
plus ``sampling_parameters_supported: False`` rather than a fabricated
``temperature: 0.0``. What *is* frozen and recorded is ``max_tokens``, the
thinking mode and ``output_config.effort``. Any comparison across treatments
using this adapter is therefore a comparison under a stochastic decoder held
at identical configuration -- not a byte-reproducible one, the way a
``FakeProvider`` comparison is. See ``docs/research/post-pilot-protocol-v1.md``
§9.3, whose decoding-configuration requirement this satisfies in shape while
recording honestly that one of its named parameters no longer exists.
"""

from __future__ import annotations

import os
from importlib import metadata
from typing import Any

from .base import (
    MODEL_SNAPSHOT_UNAVAILABLE,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    count_transmitted_bytes,
)
from .settings import (
    PROMPT_SCAFFOLDING_VERSION,
    AnthropicProviderConfig,
)

SDK_DISTRIBUTION_NAME = "anthropic"

# SDK exception type names that mean "the call did not complete in time".
# Checked before _NORMALIZED_FAILURE_REASONS because APITimeoutError
# subclasses APIConnectionError in the SDK.
_TIMEOUT_EXCEPTION_NAMES = ("APITimeoutError",)

# Fixed, metadata-only vocabulary. A reason token names a *kind* of failure
# and can never carry request content -- unlike the SDK's own message, which
# is deliberately discarded.
_NORMALIZED_FAILURE_REASONS: dict[str, str] = {
    "AuthenticationError": "authentication_rejected",
    "PermissionDeniedError": "permission_denied",
    "NotFoundError": "model_or_endpoint_not_found",
    "RateLimitError": "rate_limited",
    "BadRequestError": "request_rejected",
    "APIStatusError": "api_status_error",
    "APIConnectionError": "connection_failed",
}
_UNCLASSIFIED_FAILURE_REASON = "unclassified_provider_failure"

# stop_reason values that are not a normal, complete answer. Each fails the
# whole call closed rather than returning a partial or empty answer that
# downstream scoring would treat as a real response.
_REFUSAL_STOP_REASON = "refusal"
_TRUNCATION_STOP_REASON = "max_tokens"


def sdk_version() -> str:
    """The installed ``anthropic`` distribution version, or a sentinel.

    Part of the freezable configuration record: a provider run is not
    reproducible from model id and decoding parameters alone if the client
    library that built the request is unknown.
    """
    try:
        return metadata.version(SDK_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return "not_installed"


def _load_sdk() -> Any:
    try:
        # Imported lazily: the SDK lives behind an optional extra and the
        # package must import cleanly without it.
        import anthropic
    except ImportError:
        raise ProviderError(
            "the anthropic SDK is not installed; install the 'anthropic' optional extra "
            "before selecting the real provider"
        ) from None
    return anthropic


def build_anthropic_client(config: AnthropicProviderConfig, *, sdk: Any = None) -> Any:
    """Construct the SDK client this adapter calls through.

    ``sdk`` exists as an injection seam for the offline test suite (it is
    the ``anthropic`` module, or a double exposing ``Anthropic``); production
    callers leave it ``None`` and get the real, lazily-imported package.

    Two settings here are load-bearing, not defaults worth inheriting:

    ``max_retries=0`` -- the SDK retries **twice by default** on 408/409/429,
    5xx and connection errors. Left at that default, one logical provider
    call could re-transmit the disclosure-controlled payload three times,
    silently, while every behavioral test still passed. ``invoke_provider``'s
    documented contract is exactly one attempt, and the retry policy for this
    codebase lives there and nowhere else.

    ``timeout`` -- the native transport deadline issue #30 requires *in
    addition to* ``invoke_provider``'s caller-side wall-clock deadline. The
    caller-side deadline abandons a worker thread; only this one can stop an
    HTTP request from continuing to run.

    Fails closed when the credential is absent: no client is constructed, no
    call is attempted, and there is no fallback to ``FakeProvider`` or to any
    other provider.
    """
    active_sdk = sdk if sdk is not None else _load_sdk()

    api_key = os.getenv(config.api_key_env_var)
    if not api_key:
        raise ProviderError(
            "no API credential is available for the real provider: environment "
            f"variable {config.api_key_env_var!r} is unset or empty"
        )

    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": config.timeout_seconds,
        "max_retries": 0,
    }
    if config.base_url is not None:
        kwargs["base_url"] = config.base_url
    return active_sdk.Anthropic(**kwargs)


def _failure_reason(exc: BaseException) -> tuple[str, bool]:
    """``(reason token, is_timeout)`` for ``exc``, by type name over its MRO.

    Never inspects, formats or returns the exception's own message -- see
    the module docstring for why that message is treated as untrusted.
    """
    for klass in type(exc).__mro__:
        name = klass.__name__
        if name in _TIMEOUT_EXCEPTION_NAMES:
            return "transport_timeout", True
        reason = _NORMALIZED_FAILURE_REASONS.get(name)
        if reason is not None:
            return reason, False
    return _UNCLASSIFIED_FAILURE_REASON, False


class AnthropicProvider:
    """Anthropic Messages API implementation of ``providers.base.Provider``.

    ``provider_class`` is fixed to ``"external_llm"`` -- a class attribute,
    not something derived from configuration or the environment. This
    adapter calls Anthropic's real, official external endpoint; that is a
    fact about what the adapter *is*, not a label a caller or a deployment
    can pick. ``provider_class`` is not arbitrary metadata: it feeds policy
    (see ``docs/hr-policy-matrix.md``, where ``employee_name`` is treated
    more restrictively under an external provider precisely because the
    data crosses the organizational boundary). A configurable
    ``provider_class`` on this adapter previously let ``ADG_PROVIDER_CLASS``
    make it declare ``internal_llm`` while still transmitting to Anthropic,
    which would make policy apply the more permissive internal rule to a
    call that was, in fact, external -- a trust-boundary bug fixed here by
    removing the configurability outright rather than by validating it.

    This is deliberately unlike ``FakeProvider``, whose ``provider_class`` is
    genuinely swapped per case by ``experiments.execution.execute_case`` to
    stand in for whichever provider class an experimental comparison is
    studying (including the B4 contextual matrix's own
    ``external_llm``/``internal_llm`` comparison, see
    ``experiments/contextual_matrix.py``). ``FakeProvider`` is an
    experimental stand-in with no real transport behind it, so representing
    a class it does not actually call is harmless. ``AnthropicProvider`` is a
    concrete external boundary -- exercising a real, genuine evaluation of
    the ``internal_llm`` condition requires a provider that actually sits
    inside the organizational boundary, not this adapter relabeled.
    """

    provider_class = "external_llm"

    def __init__(
        self,
        config: AnthropicProviderConfig | None = None,
        *,
        client: Any = None,
    ) -> None:
        self._config = config if config is not None else AnthropicProviderConfig()
        self._client = client

    def __repr__(self) -> str:
        """Explicit, credential-free repr.

        Written by hand rather than inherited so that no attribute added to
        this class in future -- an SDK client holding a key, a cached
        response -- can start appearing in a log line or a test failure
        message by default.
        """
        return (
            f"AnthropicProvider(model_id={self._config.model_id!r}, "
            f"provider_class={self.provider_class!r})"
        )

    __str__ = __repr__

    @property
    def config(self) -> AnthropicProviderConfig:
        return self._config

    @property
    def native_timeout_seconds(self) -> float:
        """The native transport timeout configured on the SDK client
        (T22 / issue #30, review blocker 2).

        Read by ``providers.caller_timeout_for_provider`` to derive a
        caller-side wall-clock deadline that is guaranteed to exceed this
        value -- see that function's docstring for why the two must never be
        allowed to diverge independently.
        """
        return self._config.timeout_seconds

    def _active_client(self) -> Any:
        if self._client is None:
            self._client = build_anthropic_client(self._config)
        return self._client

    def _request_kwargs(self, request: ProviderRequest) -> dict[str, Any]:
        """The exact Messages API call this adapter makes.

        One user message carrying the task instruction, a blank line, then
        the disclosure-controlled payload -- the whole scaffolding rule,
        versioned as ``PROMPT_SCAFFOLDING_VERSION`` so a change to it is a
        recorded, comparability-breaking change rather than a silent one. No
        system prompt is sent: extra scaffolding the corpus did not author
        would differ from what ``FakeProvider`` runs see and would not be
        held constant across treatments by construction.

        No sampling parameter is sent -- see the module docstring.
        """
        kwargs: dict[str, Any] = {
            "model": self._config.model_id,
            "max_tokens": self._config.max_output_tokens,
            "messages": [{"role": "user", "content": f"{request.task}\n\n{request.payload}"}],
            "output_config": {"effort": self._config.effort},
        }
        if self._config.thinking_mode == "disabled":
            kwargs["thinking"] = {"type": "disabled"}
        else:
            kwargs["thinking"] = {"type": "adaptive"}
        return kwargs

    def decoding_config(self) -> dict[str, Any]:
        """The decoding configuration actually in force for a call.

        Mirrors ``FakeProvider.decoding_config``'s shape (the protocol's
        §9.3 requirement) while stating honestly that the sampling
        parameters it names no longer exist on current models: ``temperature``
        is ``None`` because none was sent, and ``sampling_parameters_supported``
        is ``False`` so a reader cannot mistake the ``None`` for "not
        recorded".
        """
        return {
            "max_tokens": self._config.max_output_tokens,
            "effort": self._config.effort,
            "thinking": self._config.thinking_mode,
            "temperature": None,
            "sampling_parameters_supported": False,
            "sampling": "provider_default",
        }

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        client = self._active_client()
        try:
            message = client.messages.create(**self._request_kwargs(request))
        except Exception as exc:  # noqa: BLE001 -- third-party client
            reason, is_timeout = _failure_reason(exc)
            error_class = ProviderTimeoutError if is_timeout else ProviderError
            raise error_class(
                f"anthropic provider call failed ({reason})", provider_invoked=True
            ) from None

        return self._to_provider_response(message, request)

    def _to_provider_response(self, message: Any, request: ProviderRequest) -> ProviderResponse:
        stop_reason = getattr(message, "stop_reason", None)
        if stop_reason == _REFUSAL_STOP_REASON:
            # HTTP 200, but not an answer. Fail closed: a refusal must never
            # be scored as a (very short) real response, and its
            # stop_details explanation is model-authored prose about the
            # request, so nothing from it is interpolated here.
            raise ProviderError(
                "anthropic provider declined the request (stop_reason refusal)",
                provider_invoked=True,
            )
        if stop_reason == _TRUNCATION_STOP_REASON:
            raise ProviderError(
                "anthropic provider response was truncated at the configured "
                "max output token limit (stop_reason max_tokens)",
                provider_invoked=True,
            )

        answer = self._extract_text(message)
        model_snapshot = self._extract_model_snapshot(message)
        usage = getattr(message, "usage", None)

        return ProviderResponse(
            text=answer,
            model_id=self._config.model_id,
            model_snapshot=model_snapshot,
            decoding_config=self.decoding_config(),
            transmitted_bytes=count_transmitted_bytes(request.payload),
            input_tokens=_usage_field(usage, "input_tokens"),
            output_tokens=_usage_field(usage, "output_tokens"),
            cache_creation_input_tokens=_usage_field(usage, "cache_creation_input_tokens"),
            cache_read_input_tokens=_usage_field(usage, "cache_read_input_tokens"),
        )

    @staticmethod
    def _extract_text(message: Any) -> str:
        """Join every ``text`` block, in order, and nothing else.

        Never ``content[0].text``: thinking is on by default on Claude
        Opus 5, so the first block is routinely a thinking block -- reading
        it blindly would either raise or, worse, put model reasoning where
        the answer belongs.
        """
        parts = [
            block.text
            for block in getattr(message, "content", []) or []
            if getattr(block, "type", None) == "text"
        ]
        if not parts:
            raise ProviderError(
                "anthropic provider returned no text block in its response content",
                provider_invoked=True,
            )
        return "\n".join(parts)

    def _extract_model_snapshot(self, message: Any) -> str:
        """``response.model`` when it names something other than the model
        that was requested; the explicit unavailable sentinel otherwise.

        The API reports which model actually served a request. When that is
        byte-identical to the configured id there is no distinct snapshot to
        record, and inventing one (a date, the id again) would be a false
        provenance claim -- see ``MODEL_SNAPSHOT_UNAVAILABLE``.
        """
        served = getattr(message, "model", None)
        if isinstance(served, str) and served and served != self._config.model_id:
            return served
        return MODEL_SNAPSHOT_UNAVAILABLE

    def configuration_record(self) -> dict[str, Any]:
        """A freezable, metadata-only provider configuration record.

        Covers ``docs/research/post-pilot-protocol-v1.md`` §9.3's per-batch
        freeze fields, in a shape suitable for
        ``experiments/artifacts.write_pilot_artifacts``' ``reproducibility``
        mapping. Contains no credential, no payload, no task text and no
        hash of content -- only identifiers, versions, numbers and flags.

        ``model_snapshot`` is deliberately absent: it is a per-call fact, not
        a configuration one, and is already recorded per execution as
        ``RunIdentity.provider_model_snapshot`` (protocol §13.1). Cost is
        likewise absent: this adapter records real token usage and no
        pricing, so a consumer reports cost as unavailable rather than
        computing one from a table that would silently go stale.

        ``base_url_policy`` states the fixed policy in words rather than a
        boolean flag (T22 / issue #30, review blocker 4): a prior
        ``base_url_overridden: true/false`` flag was insufficient
        provenance, since two batches could both say ``true`` and still have
        used different backends. ``AnthropicProviderConfig`` now forbids the
        override outright at construction, so this is always the same fixed
        statement -- never a value derived from (and therefore never able to
        leak) whatever a caller attempted to pass.
        """
        return {
            "provider": "anthropic",
            "provider_class": self.provider_class,
            "model_id": self._config.model_id,
            "model_snapshot_source": "RunIdentity.provider_model_snapshot (recorded per call)",
            "sdk_name": SDK_DISTRIBUTION_NAME,
            "sdk_version": sdk_version(),
            "transport_timeout_seconds": self._config.timeout_seconds,
            "retry_policy": "none (client max_retries=0; invoke_provider attempts exactly once)",
            "fallback_policy": "none (no model fallback, no provider fallback, no fallback to b0)",
            "decoding_config": self.decoding_config(),
            "prompt_scaffolding_version": PROMPT_SCAFFOLDING_VERSION,
            "base_url_policy": (
                "fixed to the official Anthropic endpoint; override forbidden for this adapter"
            ),
            "api_key_env_var": self._config.api_key_env_var,
            "cost_accounting": "unavailable (token usage recorded; no pricing table)",
        }


def _usage_field(usage: Any, name: str) -> int | None:
    """One integer usage counter, or ``None`` when the API did not report it.

    Never estimated: issue #30 requires the provider API's own numbers, and
    ``None`` means "this provider did not report it", which is a different
    claim from ``0``.
    """
    if usage is None:
        return None
    reported = getattr(usage, name, None)
    return reported if isinstance(reported, int) else None
