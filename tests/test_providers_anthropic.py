"""Offline tests for the real Anthropic provider adapter (T22 / issue #30).

No test in this module touches the network: every one of them either injects
a fake SDK client object (``messages.create``) or a fake SDK module into the
adapter's two documented seams. The live, opt-in integration test lives in
``tests/test_providers_anthropic_integration.py`` and is skipped unless a
credential and an explicit environment flag are both present.

What these tests exist to catch -- each is a real defect the adapter could
plausibly have:

- silently sending a sampling parameter (``temperature``/``top_p``/``top_k``)
  that current models reject, or recording one in ``decoding_config`` that
  was never sent (a fabricated reproducibility record is worse than a
  missing one);
- leaving the SDK's default ``max_retries=2`` in place, which would violate
  ``providers/base.py``'s explicit no-retry contract invisibly -- the request
  would still succeed, so no behavioral test would notice;
- reading ``content[0].text``, which breaks the moment a thinking block is
  returned first;
- inventing a model snapshot when the API exposes none;
- letting an API key, a payload, a task or a third-party exception message
  escape through a repr, an error message, a chained ``__cause__`` or a span
  attribute (CLAUDE.md's no-leak invariant);
- falling back to ``FakeProvider`` or to B0 -- Direct on failure.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest

from adaptive_disclosure_gateway.providers import (
    MODEL_SNAPSHOT_UNAVAILABLE,
    AnthropicProvider,
    AnthropicProviderConfig,
    Provider,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequest,
    ProviderTimeoutError,
    build_anthropic_client,
    count_transmitted_bytes,
)

MARKER_API_KEY = "sk-ant-marker-DO-NOT-LEAK-9f3b2a1c"


# --- Fake SDK doubles -------------------------------------------------------
#
# These mirror only the attributes the adapter actually reads, so a change in
# what it reads shows up as an AttributeError here rather than as a silently
# different request on the wire.


class _Block:
    def __init__(self, type: str, text: str | None = None, thinking: str | None = None) -> None:
        self.type = type
        if text is not None:
            self.text = text
        if thinking is not None:
            self.thinking = thinking


class _Usage:
    def __init__(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation_input_tokens: int | None = None,
        cache_read_input_tokens: int | None = None,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _Message:
    def __init__(
        self,
        content: list[_Block],
        model: str,
        stop_reason: str = "end_turn",
        usage: _Usage | None = None,
    ) -> None:
        self.content = content
        self.model = model
        self.stop_reason = stop_reason
        self.usage = usage
        self.stop_details = None


class _FakeMessages:
    def __init__(self, response: _Message | None, error: Exception | None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Message:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class _FakeClient:
    def __init__(self, response: _Message | None = None, error: Exception | None = None) -> None:
        self.messages = _FakeMessages(response, error)


class _RecordingAnthropic:
    """Stands in for ``anthropic.Anthropic``, recording its constructor kwargs."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _FakeSdkModule:
    Anthropic = _RecordingAnthropic


def _text_response(text: str = "an answer", model: str = "claude-opus-5") -> _Message:
    return _Message(
        content=[_Block("text", text=text)],
        model=model,
        usage=_Usage(input_tokens=11, output_tokens=7),
    )


def _provider(client: _FakeClient, **config_kwargs: Any) -> AnthropicProvider:
    return AnthropicProvider(AnthropicProviderConfig(**config_kwargs), client=client)


# --- Protocol conformance ---------------------------------------------------


def test_anthropic_provider_satisfies_the_same_provider_protocol_as_fake_provider():
    # The whole point of the shared boundary: a real adapter must be usable
    # anywhere FakeProvider is, with no per-provider branch at the call site.
    provider = _provider(_FakeClient(_text_response()))

    assert isinstance(provider, Provider)
    assert provider.provider_class == "external_llm"


# --- Request mapping --------------------------------------------------------


def test_generate_sends_the_task_and_payload_as_one_user_message():
    client = _FakeClient(_text_response())
    provider = _provider(client, model_id="claude-opus-5", max_output_tokens=1234)

    provider.generate(ProviderRequest(payload="PAYLOAD-BODY", task="TASK-INSTRUCTION"))

    assert len(client.messages.calls) == 1
    sent = client.messages.calls[0]
    assert sent["model"] == "claude-opus-5"
    assert sent["max_tokens"] == 1234
    assert sent["messages"] == [{"role": "user", "content": "TASK-INSTRUCTION\n\nPAYLOAD-BODY"}]


def test_generate_never_sends_a_sampling_parameter_current_models_reject():
    # temperature/top_p/top_k were removed on Opus 5, Sonnet 5, Opus 4.8/4.7
    # and the Fable family: sending one is an HTTP 400, so an adapter that
    # "helpfully" pins temperature=0 for determinism would fail every call.
    client = _FakeClient(_text_response())

    _provider(client).generate(ProviderRequest(payload="p", task="t"))

    sent = client.messages.calls[0]
    for forbidden in ("temperature", "top_p", "top_k"):
        assert forbidden not in sent


def test_generate_sends_exactly_one_api_call_and_never_retries_itself():
    # providers/base.py's Provider protocol: "Implementations must not
    # perform their own retries".
    client = _FakeClient(error=RuntimeError("transport exploded"))

    with pytest.raises(ProviderError):
        _provider(client).generate(ProviderRequest(payload="p", task="t"))

    assert len(client.messages.calls) == 1


# --- Client construction ----------------------------------------------------


def test_client_is_constructed_with_sdk_retries_disabled(monkeypatch):
    # The SDK retries twice BY DEFAULT (408/409/429/5xx/connection errors).
    # Left at its default, a "single" provider call could re-send the
    # disclosure-controlled payload three times with nothing in this
    # codebase revealing it. This pins the override, not the documentation.
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)

    client = build_anthropic_client(AnthropicProviderConfig(), sdk=_FakeSdkModule())

    assert client.kwargs["max_retries"] == 0


def test_client_is_constructed_with_the_native_transport_timeout(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)

    client = build_anthropic_client(
        AnthropicProviderConfig(timeout_seconds=12.5), sdk=_FakeSdkModule()
    )

    assert client.kwargs["timeout"] == 12.5


def test_missing_credential_fails_closed_without_constructing_a_client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ProviderError):
        build_anthropic_client(AnthropicProviderConfig(), sdk=_FakeSdkModule())


# --- Response mapping -------------------------------------------------------


def test_generate_joins_only_text_blocks_and_never_assumes_the_first_block_is_text():
    # Thinking is on by default on Opus 5, so response.content[0] is
    # routinely a thinking block. content[0].text would raise (or, worse,
    # return reasoning text) on every real call.
    client = _FakeClient(
        _Message(
            content=[
                _Block("thinking", thinking="internal reasoning that is not the answer"),
                _Block("text", text="first half"),
                _Block("text", text="second half"),
            ],
            model="claude-opus-5",
            usage=_Usage(input_tokens=3, output_tokens=4),
        )
    )

    response = _provider(client).generate(ProviderRequest(payload="p", task="t"))

    assert response.text == "first half\nsecond half"
    assert "internal reasoning" not in response.text


def test_generate_maps_the_api_usage_numbers_without_estimating_them():
    client = _FakeClient(
        _Message(
            content=[_Block("text", text="ok")],
            model="claude-opus-5",
            usage=_Usage(
                input_tokens=101,
                output_tokens=202,
                cache_creation_input_tokens=303,
                cache_read_input_tokens=404,
            ),
        )
    )

    response = _provider(client).generate(ProviderRequest(payload="p", task="t"))

    assert response.input_tokens == 101
    assert response.output_tokens == 202
    assert response.cache_creation_input_tokens == 303
    assert response.cache_read_input_tokens == 404


def test_usage_is_reported_as_unavailable_rather_than_guessed_when_the_api_omits_it():
    client = _FakeClient(
        _Message(content=[_Block("text", text="ok")], model="claude-opus-5", usage=None)
    )

    response = _provider(client).generate(ProviderRequest(payload="p", task="t"))

    assert response.input_tokens is None
    assert response.output_tokens is None


def test_model_snapshot_is_the_serving_model_when_it_differs_from_the_requested_id():
    client = _FakeClient(
        _Message(
            content=[_Block("text", text="ok")],
            model="claude-opus-5-some-served-snapshot",
            usage=None,
        )
    )

    response = _provider(client, model_id="claude-opus-5").generate(
        ProviderRequest(payload="p", task="t")
    )

    assert response.model_id == "claude-opus-5"
    assert response.model_snapshot == "claude-opus-5-some-served-snapshot"


def test_model_snapshot_is_recorded_unavailable_rather_than_invented():
    # When the API returns exactly the id that was requested there is no
    # distinct snapshot. Synthesizing one (a date, a hash, the model id
    # again) would put a fabricated value into reproducibility provenance.
    client = _FakeClient(
        _Message(content=[_Block("text", text="ok")], model="claude-opus-5", usage=None)
    )

    response = _provider(client, model_id="claude-opus-5").generate(
        ProviderRequest(payload="p", task="t")
    )

    assert response.model_snapshot == MODEL_SNAPSHOT_UNAVAILABLE


def test_transmitted_bytes_reuses_the_shared_payload_only_counting_rule():
    client = _FakeClient(_text_response())
    provider = _provider(client)

    short_task = provider.generate(ProviderRequest(payload="same payload", task="a"))

    assert short_task.transmitted_bytes == count_transmitted_bytes("same payload")


def test_decoding_config_records_only_parameters_that_were_actually_sent():
    client = _FakeClient(_text_response())

    response = _provider(
        client, max_output_tokens=777, effort="medium", thinking_mode="adaptive"
    ).generate(ProviderRequest(payload="p", task="t"))

    config = dict(response.decoding_config)
    assert config["max_tokens"] == 777
    assert config["effort"] == "medium"
    assert config["thinking"] == "adaptive"
    # The field exists (post-pilot-protocol-v1 §9.3 requires the same shape
    # FakeProvider exposes) but must say "not sent", never fake a 0.0.
    assert config["temperature"] is None
    assert config["sampling_parameters_supported"] is False


# --- Non-answer stop reasons fail closed ------------------------------------


def test_a_refusal_stop_reason_fails_closed_instead_of_being_scored_as_an_answer():
    # HTTP 200 with stop_reason "refusal" is a real Opus 5 outcome. Treating
    # it as a successful (short) response would feed a refusal into utility
    # scoring as if the model had answered the task.
    client = _FakeClient(
        _Message(
            content=[_Block("text", text="I cannot help with that.")],
            model="claude-opus-5",
            stop_reason="refusal",
        )
    )

    with pytest.raises(ProviderError):
        _provider(client).generate(ProviderRequest(payload="p", task="t"))


def test_a_truncated_response_fails_closed_instead_of_being_scored_as_complete():
    client = _FakeClient(
        _Message(
            content=[_Block("text", text="half an ans")],
            model="claude-opus-5",
            stop_reason="max_tokens",
        )
    )

    with pytest.raises(ProviderError):
        _provider(client).generate(ProviderRequest(payload="p", task="t"))


def test_a_response_with_no_text_block_fails_closed():
    client = _FakeClient(
        _Message(
            content=[_Block("thinking", thinking="only reasoning, no answer")],
            model="claude-opus-5",
        )
    )

    with pytest.raises(ProviderError):
        _provider(client).generate(ProviderRequest(payload="p", task="t"))


# --- Error normalization ----------------------------------------------------


class _SdkApiError(Exception):
    pass


class _SdkApiStatusError(_SdkApiError):
    pass


class _SdkApiConnectionError(_SdkApiError):
    pass


def _sdk_exception(name: str, base: type[Exception], message: str) -> Exception:
    """An exception shaped like the SDK's: the right *type name*, over the
    right base, carrying a message the adapter must never re-expose.
    """
    return type(name, (base,), {})(message)


SDK_LEAKY_MESSAGE = "400 Bad Request while sending LEAKY-REQUEST-BODY-ECHO"


@pytest.mark.parametrize(
    "name,base",
    [
        ("AuthenticationError", _SdkApiStatusError),
        ("PermissionDeniedError", _SdkApiStatusError),
        ("BadRequestError", _SdkApiStatusError),
        ("NotFoundError", _SdkApiStatusError),
        ("RateLimitError", _SdkApiStatusError),
        ("APIStatusError", _SdkApiError),
        ("APIConnectionError", _SdkApiError),
    ],
)
def test_every_sdk_failure_type_is_normalized_to_provider_error(name, base):
    client = _FakeClient(error=_sdk_exception(name, base, SDK_LEAKY_MESSAGE))

    with pytest.raises(ProviderError) as excinfo:
        _provider(client).generate(ProviderRequest(payload="p", task="t"))

    # Not a ProviderTimeoutError: only a genuine timeout may claim that,
    # because a caller distinguishing the two acts differently on them.
    assert not isinstance(excinfo.value, ProviderTimeoutError)


def test_an_sdk_timeout_is_normalized_to_provider_timeout_error():
    # APITimeoutError subclasses APIConnectionError in the SDK, so a
    # classifier that checked connection errors first would silently
    # mislabel every timeout.
    client = _FakeClient(
        error=_sdk_exception("APITimeoutError", _SdkApiConnectionError, "timed out")
    )

    with pytest.raises(ProviderTimeoutError):
        _provider(client).generate(ProviderRequest(payload="p", task="t"))


def test_a_subclassed_failure_is_classified_by_the_subclass_not_its_base():
    client = _FakeClient(error=_sdk_exception("RateLimitError", _SdkApiStatusError, "429"))

    with pytest.raises(ProviderError) as excinfo:
        _provider(client).generate(ProviderRequest(payload="p", task="t"))

    assert "rate_limited" in str(excinfo.value)


def test_a_normalized_error_never_carries_the_sdk_message_or_chains_the_cause():
    # The concrete side channel this closes: an HTTP client quoting the
    # request body it failed to send would otherwise put the
    # disclosure-controlled payload into a traceback via __cause__.
    client = _FakeClient(
        error=_sdk_exception("BadRequestError", _SdkApiStatusError, SDK_LEAKY_MESSAGE)
    )

    with pytest.raises(ProviderError) as excinfo:
        _provider(client).generate(
            ProviderRequest(payload="SENSITIVE-PAYLOAD-BODY", task="SENSITIVE-TASK")
        )

    raised = excinfo.value
    assert raised.__cause__ is None
    assert raised.__suppress_context__ is True
    rendered = repr(raised) + str(raised)
    assert "LEAKY-REQUEST-BODY-ECHO" not in rendered
    assert "SENSITIVE-PAYLOAD-BODY" not in rendered
    assert "SENSITIVE-TASK" not in rendered


def test_an_unrecognized_third_party_failure_still_fails_closed():
    client = _FakeClient(error=RuntimeError("something entirely unexpected"))

    with pytest.raises(ProviderError) as excinfo:
        _provider(client).generate(ProviderRequest(payload="p", task="t"))

    assert "something entirely unexpected" not in str(excinfo.value)


# --- No-leak: the credential ------------------------------------------------


def test_the_api_key_never_appears_in_the_provider_its_config_or_any_failure(monkeypatch):
    """Adversarial: place a marker credential in the environment and ask
    whether it can get out by any path this adapter owns.

    Checks the repr, the str, the configuration object's own serialization,
    the freezable configuration record, and an error raised from every
    normalized failure path -- not just the happy path.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    config = AnthropicProviderConfig()

    # The config never holds the key at all -- by construction, not by
    # remembering to strip it.
    assert MARKER_API_KEY not in json.dumps(dataclasses.asdict(config))
    assert MARKER_API_KEY not in repr(config)

    provider = AnthropicProvider(config, client=_FakeClient(_text_response()))
    assert MARKER_API_KEY not in repr(provider)
    assert MARKER_API_KEY not in str(provider)
    assert MARKER_API_KEY not in json.dumps(provider.configuration_record(), default=str)

    failures = [
        _sdk_exception("AuthenticationError", _SdkApiStatusError, f"invalid key {MARKER_API_KEY}"),
        _sdk_exception("APITimeoutError", _SdkApiConnectionError, f"x-api-key {MARKER_API_KEY}"),
        _sdk_exception("BadRequestError", _SdkApiStatusError, MARKER_API_KEY),
        RuntimeError(MARKER_API_KEY),
    ]
    for failure in failures:
        failing = AnthropicProvider(config, client=_FakeClient(error=failure))
        with pytest.raises(ProviderError) as excinfo:
            failing.generate(ProviderRequest(payload="p", task="t"))
        rendered = repr(excinfo.value) + str(excinfo.value) + repr(excinfo.value.__cause__)
        assert MARKER_API_KEY not in rendered

    # The client the adapter builds does receive the key (it must), but the
    # adapter itself still never renders it.
    built = build_anthropic_client(config, sdk=_FakeSdkModule())
    assert built.kwargs["api_key"] == MARKER_API_KEY
    assert MARKER_API_KEY not in repr(AnthropicProvider(config, client=built))


def test_the_freezable_configuration_record_carries_no_payload_task_or_credential(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARKER_API_KEY)
    provider = _provider(_FakeClient(_text_response()))

    provider.generate(ProviderRequest(payload="SENSITIVE-PAYLOAD", task="SENSITIVE-TASK"))
    rendered = json.dumps(provider.configuration_record(), default=str)

    assert "SENSITIVE-PAYLOAD" not in rendered
    assert "SENSITIVE-TASK" not in rendered
    assert MARKER_API_KEY not in rendered


def test_the_configuration_record_covers_every_protocol_freeze_field():
    # post-pilot-protocol-v1 section 9.3 lists exactly what must be
    # freezable per batch before a run counts as authoritative. A missing
    # key here means a batch cannot be frozen -- a research-blocking defect,
    # not a cosmetic one.
    record = _provider(_FakeClient(_text_response())).configuration_record()

    for required in (
        "provider",
        "provider_class",
        "model_id",
        "model_snapshot_source",
        "sdk_name",
        "sdk_version",
        "transport_timeout_seconds",
        "retry_policy",
        "fallback_policy",
        "decoding_config",
        "prompt_scaffolding_version",
        "cost_accounting",
    ):
        assert required in record, f"freeze record is missing {required!r}"

    assert record["decoding_config"]["max_tokens"] > 0
    assert "none" in record["retry_policy"]
    assert "none" in record["fallback_policy"]


# --- No fallback ------------------------------------------------------------


def test_the_adapter_module_never_imports_or_names_the_fake_provider_in_code():
    # Structural, not behavioral: a fallback to FakeProvider would be a
    # silent substitution that no response-shape assertion could detect,
    # and post-pilot-protocol-v1 section 9.4 forbids it outright. Checked
    # over the AST rather than the raw source so the module may still
    # *document* that FakeProvider remains the default -- prose is not a
    # code path.
    import ast
    import inspect

    from adaptive_disclosure_gateway.providers import anthropic_api

    tree = ast.parse(inspect.getsource(anthropic_api))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "fake" not in alias.name.lower()
        elif isinstance(node, ast.ImportFrom):
            assert "fake" not in (node.module or "").lower()
            for alias in node.names:
                assert "fake" not in alias.name.lower()
        elif isinstance(node, ast.Name):
            assert "fake" not in node.id.lower()
        elif isinstance(node, ast.Attribute):
            assert "fake" not in node.attr.lower()


def test_a_failure_is_never_retried_or_answered_by_a_second_call():
    client = _FakeClient(error=_sdk_exception("RateLimitError", _SdkApiStatusError, "429"))
    provider = _provider(client)

    for _ in range(3):
        with pytest.raises(ProviderError):
            provider.generate(ProviderRequest(payload="p", task="t"))

    # Three explicit caller-driven attempts produced exactly three API
    # calls: no hidden retry multiplied them.
    assert len(client.messages.calls) == 3


# --- Configuration validation -----------------------------------------------


def test_disabled_thinking_at_an_effort_the_api_rejects_fails_at_construction():
    with pytest.raises(ProviderConfigurationError):
        AnthropicProviderConfig(thinking_mode="disabled", effort="max")


def test_an_unknown_effort_level_fails_at_construction():
    with pytest.raises(ProviderConfigurationError):
        AnthropicProviderConfig(effort="turbo")


# --- Model allowlist: capability provenance must not be claimed for an
# unvalidated model (T22 / issue #30, review blocker 3) ---------------------


def test_the_default_model_id_is_accepted():
    # claude-opus-5 is the default and the one model this adapter version
    # has actually verified end-to-end (sampling params, thinking, effort,
    # max_tokens, response shape, usage metadata). Must not raise.
    AnthropicProviderConfig()


def test_an_unvalidated_model_id_is_rejected_at_construction():
    # An older or unvalidated model id would make this adapter's recorded
    # decoding_config/sampling provenance a false claim -- it was verified
    # only for the allowlisted models, not universally. Must fail at
    # configuration time, never discovered later as an HTTP error or,
    # worse, silently accepted with an unverified capability record.
    with pytest.raises(ProviderConfigurationError):
        AnthropicProviderConfig(model_id="claude-3-opus-20240229")


def test_an_empty_model_id_is_rejected_at_construction():
    with pytest.raises(ProviderConfigurationError):
        AnthropicProviderConfig(model_id="")


def test_no_supported_model_can_declare_sampling_parameters_supported():
    # Structural guarantee, not a spot check: every model_id this adapter
    # can be constructed with is in the validated allowlist, and for every
    # one of them decoding_config must say sampling_parameters_supported is
    # False -- there is no way to build a config that both passes
    # construction and claims sampling support for an unvalidated model.
    from adaptive_disclosure_gateway.providers.settings import SUPPORTED_ANTHROPIC_MODEL_IDS

    assert SUPPORTED_ANTHROPIC_MODEL_IDS  # non-empty: the allowlist exists
    for model_id in SUPPORTED_ANTHROPIC_MODEL_IDS:
        provider = _provider(_FakeClient(_text_response()), model_id=model_id)
        response = provider.generate(ProviderRequest(payload="p", task="t"))
        assert response.decoding_config["sampling_parameters_supported"] is False
        assert response.decoding_config["temperature"] is None


# --- base_url override: forbidden for reproducibility (T22 / issue #30,
# review blocker 4) -----------------------------------------------------------


def test_a_base_url_override_is_rejected_at_construction():
    # Two batches both recording base_url_overridden=true could still have
    # hit different backends -- insufficient provenance. The narrow fix is
    # to forbid the override outright for this adapter rather than try to
    # record it faithfully.
    with pytest.raises(ProviderConfigurationError):
        AnthropicProviderConfig(base_url="https://compatible-gateway.example.com")


MARKER_SECRET_IN_URL = "sk-ant-url-embedded-marker-DO-NOT-LEAK"


def test_a_base_url_with_an_embedded_secret_never_reaches_an_error_message():
    # Adversarial: even though the override is rejected, the rejection
    # itself must not become a new side channel for whatever was embedded in
    # the attempted URL (e.g. a credential in the userinfo component).
    secret_url = f"https://user:{MARKER_SECRET_IN_URL}@evil-gateway.example.com/v1"

    with pytest.raises(ProviderConfigurationError) as excinfo:
        AnthropicProviderConfig(base_url=secret_url)

    rendered = repr(excinfo.value) + str(excinfo.value)
    assert MARKER_SECRET_IN_URL not in rendered
    assert secret_url not in rendered


def test_the_configuration_record_states_the_base_url_policy_not_a_boolean_flag():
    # base_url_overridden: true/false was insufficient provenance (two
    # batches could both say true and still have hit different backends).
    # Since the override is now forbidden outright, the record states the
    # fixed policy in words rather than a flag that could vary silently.
    record = _provider(_FakeClient(_text_response())).configuration_record()

    assert "base_url_overridden" not in record
    assert "base_url_policy" in record
    assert isinstance(record["base_url_policy"], str) and record["base_url_policy"]


def test_a_base_url_with_an_embedded_secret_never_reaches_env_driven_configuration(monkeypatch):
    from adaptive_disclosure_gateway.providers.settings import anthropic_config_from_env

    secret_url = f"https://user:{MARKER_SECRET_IN_URL}@evil-gateway.example.com/v1"
    monkeypatch.setenv("ADG_ANTHROPIC_BASE_URL", secret_url)

    with pytest.raises(ProviderConfigurationError) as excinfo:
        anthropic_config_from_env()

    rendered = repr(excinfo.value) + str(excinfo.value)
    assert MARKER_SECRET_IN_URL not in rendered
    assert secret_url not in rendered


# --- Provider selection stays fake by default -------------------------------


def test_the_default_provider_stays_fake_when_nothing_is_configured(monkeypatch):
    from adaptive_disclosure_gateway.providers import FakeProvider, build_provider_from_env

    monkeypatch.delenv("ADG_PROVIDER", raising=False)

    assert isinstance(build_provider_from_env(), FakeProvider)


def test_an_empty_or_whitespace_only_provider_name_stays_fake(monkeypatch):
    from adaptive_disclosure_gateway.providers import FakeProvider, build_provider_from_env

    monkeypatch.setenv("ADG_PROVIDER", "   ")

    assert isinstance(build_provider_from_env(), FakeProvider)


def test_the_provider_name_fake_is_explicit_and_stays_fake(monkeypatch):
    from adaptive_disclosure_gateway.providers import FakeProvider, build_provider_from_env

    monkeypatch.setenv("ADG_PROVIDER", "fake")

    assert isinstance(build_provider_from_env(), FakeProvider)


def test_an_unrecognized_provider_name_fails_closed_rather_than_silently_using_fake(monkeypatch):
    # Review blocker 1: post-pilot-protocol-v1 section 9.4 forbids a silent
    # fallback. A typo in ADG_PROVIDER (e.g. "anthrpic" instead of
    # "anthropic") must never quietly execute the batch on FakeProvider --
    # that would produce FakeProvider results that get read as real-provider
    # evidence. It must fail loudly at configuration time instead.
    from adaptive_disclosure_gateway.providers import (
        ProviderConfigurationError,
        build_provider_from_env,
    )

    monkeypatch.setenv("ADG_PROVIDER", "anthrpic")

    with pytest.raises(ProviderConfigurationError):
        build_provider_from_env()


def test_the_real_provider_is_selected_only_by_an_explicit_opt_in(monkeypatch):
    from adaptive_disclosure_gateway.providers import build_provider_from_env

    monkeypatch.setenv("ADG_PROVIDER", "anthropic")
    monkeypatch.setenv("ADG_ANTHROPIC_MODEL_ID", "claude-opus-5")

    provider = build_provider_from_env()

    assert isinstance(provider, AnthropicProvider)
    assert provider.provider_class == "external_llm"
    assert provider.config.model_id == "claude-opus-5"


# --- Drift against the real, installed SDK (still offline, no credential) ----


def test_every_classified_exception_name_still_exists_in_the_installed_sdk():
    """Guards the one real weakness of name-based classification.

    ``_failure_reason`` matches SDK exceptions by type name so the offline
    suite can run without the optional extra. The cost of that choice is
    that a rename in the SDK would silently downgrade a recognized failure
    to ``unclassified_provider_failure`` -- no test would fail, and a batch's
    error records would quietly lose meaning. This test closes that gap
    whenever the extra happens to be installed, without any network call or
    credential.
    """
    anthropic = pytest.importorskip("anthropic")

    from adaptive_disclosure_gateway.providers.anthropic_api import (
        _NORMALIZED_FAILURE_REASONS,
        _TIMEOUT_EXCEPTION_NAMES,
    )

    for name in (*_TIMEOUT_EXCEPTION_NAMES, *_NORMALIZED_FAILURE_REASONS):
        assert hasattr(anthropic, name), f"the installed anthropic SDK no longer exports {name!r}"


def test_the_installed_sdk_still_accepts_the_client_options_this_adapter_pins():
    import inspect

    anthropic = pytest.importorskip("anthropic")

    parameters = inspect.signature(anthropic.Anthropic.__init__).parameters
    for required in ("api_key", "timeout", "max_retries", "base_url"):
        assert required in parameters, f"anthropic.Anthropic no longer accepts {required!r}"


def test_the_installed_sdk_confirms_sampling_parameters_are_gone():
    # Independent confirmation of the methodological limitation this adapter
    # documents: if a future SDK reintroduces `temperature` on
    # messages.create, the decoding-determinism note in
    # providers/anthropic_api.py must be revisited rather than left stale.
    import inspect

    anthropic = pytest.importorskip("anthropic")

    parameters = inspect.signature(anthropic.resources.messages.Messages.create).parameters
    for gone in ("temperature", "top_p", "top_k"):
        assert gone not in parameters
    for still_there in ("model", "max_tokens", "messages", "output_config", "thinking"):
        assert still_there in parameters
