"""Optional live integration pin for the real Anthropic provider adapter
(T22 / issue #30).

Skipped by default, twice over, mirroring
``tests/test_application_ingestion_docling.py``'s pattern for the optional
Docling extra:

- ``pytest.importorskip("anthropic")`` -- the SDK lives behind an optional
  extra, so the baseline dev/test environment must not require it;
- ``ADG_RUN_ANTHROPIC_INTEGRATION=1`` -- an explicit, deliberate opt-in, so
  a checkout that happens to have both the extra installed *and* a
  credential exported still never spends money or reaches the network
  during an ordinary ``pytest`` run or in CI.

The call this makes is a single synthetic one carrying no personal or
confidential data. It asserts only the reproducibility metadata the runner
schema needs -- it is not a utility/quality check, and it must never be
pointed at the HR or Contracts corpora: doing so would produce
real-provider results outside a frozen, recorded batch configuration, which
``docs/research/post-pilot-protocol-v1.md`` §9.3 forbids.
"""

from __future__ import annotations

import os

import pytest

from adaptive_disclosure_gateway.providers import (
    MODEL_SNAPSHOT_UNAVAILABLE,
    AnthropicProvider,
    ProviderRequest,
    anthropic_config_from_env,
    caller_timeout_for_provider,
    invoke_provider,
)

pytest.importorskip("anthropic")

pytestmark = pytest.mark.skipif(
    os.environ.get("ADG_RUN_ANTHROPIC_INTEGRATION") != "1"
    or not os.environ.get("ANTHROPIC_API_KEY"),
    reason=(
        "a live provider call costs money and requires network access; set "
        "ADG_RUN_ANTHROPIC_INTEGRATION=1 with ANTHROPIC_API_KEY exported to run it"
    ),
)

# Deliberately synthetic and non-sensitive: no person, no document, no
# corpus case, nothing a treatment ever transformed.
SYNTHETIC_TASK = "Answer with a single short sentence."
SYNTHETIC_PAYLOAD = "The internal reference code for this connectivity check is ADG-SMOKE-1."


def test_one_live_synthetic_call_returns_a_response_with_usable_metadata():
    provider = AnthropicProvider(anthropic_config_from_env())

    response = invoke_provider(
        provider,
        ProviderRequest(payload=SYNTHETIC_PAYLOAD, task=SYNTHETIC_TASK),
        expected_provider_class=provider.provider_class,
        # Derived the same way the scientific/runner path now derives it
        # (T22 / issue #30, review blocker 2) rather than by a manual
        # "+10s" workaround maintained independently here -- see
        # caller_timeout_for_provider's docstring.
        timeout=caller_timeout_for_provider(provider),
    )

    assert response.text.strip()
    assert response.model_id == provider.config.model_id
    # Either a genuine snapshot the API reported, or the explicit sentinel --
    # never an invented one.
    assert response.model_snapshot
    assert (
        response.model_snapshot == MODEL_SNAPSHOT_UNAVAILABLE
        or response.model_snapshot != provider.config.model_id
    )
    # Real usage accounting, which FakeProvider can never supply.
    assert isinstance(response.input_tokens, int) and response.input_tokens > 0
    assert isinstance(response.output_tokens, int) and response.output_tokens > 0
    assert response.transmitted_bytes == len(SYNTHETIC_PAYLOAD.encode("utf-8"))


def test_the_live_configuration_record_is_freezable_and_names_the_installed_sdk():
    provider = AnthropicProvider(anthropic_config_from_env())

    record = provider.configuration_record()

    assert record["sdk_version"] != "not_installed"
    assert record["retry_policy"].startswith("none")
    assert record["fallback_policy"].startswith("none")
