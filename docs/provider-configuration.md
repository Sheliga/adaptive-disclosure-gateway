# Provider configuration

How the gateway talks to an external LLM, how to enable the real provider, and what it
records. Normative experimental rules stay in
[`docs/research/post-pilot-protocol-v1.md`](research/post-pilot-protocol-v1.md) §9; this
document is the operational reference for T22 / Issue #30.

## Two providers, one boundary

Every treatment — B0 — Direct through B4 — Policy-governed — reaches a provider through
exactly one path: `providers.invoke_provider`, handed a `ProviderRequest` whose only two
fields are `payload` and `task`. Nothing else crosses that boundary: no raw document, no
detected span, no policy set, no vault, no `GovernanceContext`.

| Provider | `provider_class` | Default? | Network | Credential | Use |
| --- | --- | --- | --- | --- | --- |
| `FakeProvider` (`providers/fake.py`) | `fake` (overridden per case by the runner) | **yes** | none | none | TDD, CI, offline development, deterministic regression, the pilot/development corpora |
| `AnthropicProvider` (`providers/anthropic_api.py`) | `external_llm` (configurable) | no — opt-in | Anthropic Messages API | `ANTHROPIC_API_KEY` | authoritative runs needing real task output, real token usage and real provider behaviour |

`FakeProvider` remains the default everywhere. Selecting the real provider is always an
explicit act; nothing in this repository escalates to it automatically.

## Enabling the real provider

1. Install the optional extra (it is deliberately not a base dependency):

   ```
   pip install -e ".[anthropic]"
   ```

2. Export a credential:

   ```
   export ANTHROPIC_API_KEY=...        # never committed; see .env.example
   ```

3. Opt in:

   ```
   export ADG_PROVIDER=anthropic
   ```

`ADG_PROVIDER` unset, empty, or holding any unrecognized value yields `FakeProvider`.

### Behaviour with no credential

Fail-closed, never silent substitution. With `ADG_PROVIDER=anthropic` and no credential, the
first call raises `ProviderError` and the whole disclosure request fails. There is no
fallback to `FakeProvider`, to a different model, or to B0 — Direct: protocol §9.4 requires a
batch to fail visibly rather than quietly produce FakeProvider results that would later be
read as real-provider evidence.

With the extra not installed, the same thing happens with a different message.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `ADG_PROVIDER` | `fake` | `fake` or `anthropic` |
| `ANTHROPIC_API_KEY` | — | the credential; read from the environment only |
| `ADG_ANTHROPIC_MODEL_ID` | `claude-opus-5` | exact model id, never date-suffixed |
| `ADG_ANTHROPIC_MAX_OUTPUT_TOKENS` | `16000` | `max_tokens` for one call |
| `ADG_ANTHROPIC_EFFORT` | `high` | `low` / `medium` / `high` / `xhigh` / `max` |
| `ADG_ANTHROPIC_THINKING` | `adaptive` | `adaptive` or `disabled` |
| `ADG_ANTHROPIC_TIMEOUT_SECONDS` | `60` | native transport timeout on the SDK client |
| `ADG_ANTHROPIC_BASE_URL` | — | proxy / compatible gateway override |
| `ADG_PROVIDER_CLASS` | `external_llm` | the class the adapter declares to policy |
| `ADG_ANTHROPIC_API_KEY_ENV_VAR` | `ANTHROPIC_API_KEY` | the *name* of the credential variable |

`thinking_mode=disabled` combined with effort `xhigh`/`max` is rejected by the API; the
configuration object refuses that combination at construction rather than letting it become
an HTTP 400 part-way through a batch.

See [`.env.example`](../.env.example) for a copyable, placeholder-only version.

## Timeout and cancellation

Two independent layers, both required:

- **Native transport timeout** — configured on the SDK client itself
  (`ADG_ANTHROPIC_TIMEOUT_SECONDS`). This is the only one that can actually stop an
  in-flight HTTP request.
- **Caller-side wall-clock deadline** — enforced by `invoke_provider` itself, unchanged from
  before T22. It guarantees the caller returns even if a provider hangs, by abandoning the
  worker thread.

A timeout surfaces as `ProviderTimeoutError` (a `ProviderError`), is recorded in the audit
record as a provider failure, and is never retried.

## No retry, no fallback

- `max_retries=0` is set explicitly on the SDK client. **The SDK retries twice by default**
  (408/409/429/5xx/connection errors); left at that default a single logical provider call
  could re-transmit the disclosure-controlled payload three times, invisibly. This is pinned
  by a test, not just documented.
- The adapter itself contains no retry loop — `providers/base.py`'s `Provider` protocol
  requires that, and `invoke_provider` is the single place retry policy lives (currently:
  none).
- The server-side `fallbacks` parameter is deliberately **not** enabled. A silent model
  switch mid-batch would break the frozen-configuration requirement that makes a batch
  comparable at all.
- A failure never degrades to B0 — Direct and never falls back to `FakeProvider`.

Non-answers fail closed as well: `stop_reason: "refusal"` (an HTTP 200 outcome on current
models) and `stop_reason: "max_tokens"` (truncation) each raise `ProviderError` instead of
being scored as a real answer.

## Metadata captured

Per call, on `ProviderResponse` and from there into `ProviderCallMetrics` and the runner
schema (`t10-experiment-runner-v3`):

- `model_id` — the model that was requested;
- `model_snapshot` — the model that actually served the request, when the API reports one
  distinct from the requested id; otherwise the explicit sentinel
  `model_snapshot_unavailable`. **Never synthesized** — a fabricated snapshot would be a false
  provenance claim;
- `decoding_config` — what was actually sent (see the limitation below);
- `transmitted_bytes` — the existing payload-only byte-volume rule, unchanged, so it stays
  comparable with FakeProvider runs;
- `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` —
  the API's own numbers, never estimated. `None` means "this provider reported no usage",
  which is a different claim from `0`, and is what `FakeProvider` always reports.

There is deliberately **no cost field and no pricing table**: the gateway records usage and
no prices, so a report says *cost unavailable* rather than deriving a number from a table
that would silently go stale.

`AnthropicProvider.configuration_record()` returns the freezable, metadata-only configuration
record protocol §9.3 requires — provider, provider class, model id, SDK name and version,
transport timeout, retry policy, fallback policy, decoding configuration, prompt-scaffolding
version, and the cost-accounting statement. It is shaped to drop straight into
`artifacts.write_pilot_artifacts(reproducibility=...)`.

## Limitation: decoding determinism is not configurable

`temperature`, `top_p` and `top_k` were **removed** on current models (Claude Opus 5,
Sonnet 5, Opus 4.8/4.7, the Fable family) and return HTTP 400 if sent. The adapter therefore
sends no sampling parameter at all.

Consequences that matter for the experiment:

- bit-exact decoding determinism cannot be configured on these models. A real-provider batch
  is a comparison under a stochastic decoder held at *identical configuration*, not a
  byte-reproducible one the way a `FakeProvider` comparison is;
- `decoding_config` records `temperature: null` and `sampling_parameters_supported: false`
  rather than a fabricated `temperature: 0.0`. Protocol §9.3 asks a real adapter to expose the
  same *shape* of decoding configuration as `FakeProvider`; it does, while stating honestly
  that one of the parameters that shape names no longer exists;
- what *is* frozen and recorded is `max_tokens`, the thinking mode, and
  `output_config.effort`.

A test pins that the installed SDK still lacks those parameters, so if a future SDK
reintroduces them this note is revisited rather than left stale.

## Prompt scaffolding

The adapter sends exactly one user message: the task instruction, a blank line, then the
disclosure-controlled payload. No system prompt is added — extra scaffolding the corpus did
not author would not be held constant across treatments by construction. The rule is
versioned as `PROMPT_SCAFFOLDING_VERSION` (`t22-task-then-blank-line-then-payload-v1`) and
recorded in the configuration record: changing the joining rule is a
comparability-breaking change and must bump that string.

## Running a controlled batch through the real provider

`runner.run_pilot(...)` and `runner.run_case_for_treatment(...)` accept an optional
`provider`. Left `None`, every case uses `FakeProvider` exactly as before. Passed an adapter,
that one provider answers every case of the batch, so a batch has exactly one provider
configuration.

The case contexts' `GovernanceContext.provider_class` must match what the adapter declares;
`invoke_provider` refuses a mismatch before `generate()` runs rather than silently proceeding.

Scientific scoring is unchanged. In particular, `FakeProvider`'s utility
information-sufficiency proxy and utility measured from a real answer are **not** the same
measurement (protocol §6.3/§9.2); this ticket delivers the real response plus its metadata
and does not redefine any metric.

## Running the live integration test

Skipped by default, twice over: the SDK is an optional extra, and an explicit flag is
required on top of a credential.

```
pip install -e ".[anthropic]"
export ANTHROPIC_API_KEY=...
ADG_RUN_ANTHROPIC_INTEGRATION=1 .venv/Scripts/python.exe -m pytest tests/test_providers_anthropic_integration.py
```

It makes exactly one synthetic call carrying no personal or confidential data and asserts only
the reproducibility metadata. Never point it at the HR or Contracts corpora: that would
produce real-provider results outside a frozen, recorded batch configuration.

Every other provider test runs offline against a fake SDK client and needs neither the extra
nor a credential.

## Credential handling

The key is read from the environment at client-construction time and handed straight to the
SDK client. It is never:

- stored on the provider object or in `AnthropicProviderConfig` (which carries only the
  *name* of the variable to read);
- interpolated into an exception message — every SDK failure is normalized to a fixed reason
  token and raised `from None`, so the third-party message is never chained onto a traceback;
- written to a span attribute, a log line, an audit record, an artifact or a manifest.

An adversarial test places a marker key in the environment and asserts it appears in none of
the provider's `repr`/`str`, the config's serialization, the configuration record, or an
error raised from every normalized failure path.
