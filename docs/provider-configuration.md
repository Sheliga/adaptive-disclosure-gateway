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
| `AnthropicProvider` (`providers/anthropic_api.py`) | `external_llm` (fixed, not configurable) | no — opt-in | Anthropic Messages API | `ANTHROPIC_API_KEY` | authoritative runs needing real task output, real token usage and real provider behaviour |

`FakeProvider` remains the default everywhere. Selecting the real provider is always an
explicit act; nothing in this repository escalates to it automatically.

### `provider_class` is a fixed fact about `AnthropicProvider`, not configuration

`AnthropicProvider.provider_class` is invariably `"external_llm"` — a plain class attribute,
never derived from `AnthropicProviderConfig` or from the environment. `provider_class` is not
arbitrary metadata: it feeds policy (see `docs/hr-policy-matrix.md`, where `employee_name` is
treated more restrictively under an external provider precisely because the data crosses the
organizational boundary). A prior revision let `AnthropicProviderConfig.provider_class` be set
from `ADG_PROVIDER_CLASS`, so `ADG_PROVIDER_CLASS=internal_llm` made this adapter declare
`internal_llm` while still calling the genuine external Anthropic endpoint — letting policy
apply the more permissive internal rule to a call that was, in fact, external. That
configurability has been removed outright: `AnthropicProviderConfig` no longer accepts a
`provider_class` argument at all, and `ADG_PROVIDER_CLASS` is no longer read anywhere in this
adapter's configuration path.

`invoke_provider`'s pre-flight check (`provider.provider_class == request.context.provider_class`)
still runs unchanged. With `AnthropicProvider` fixed at `external_llm`, a case whose
`GovernanceContext.provider_class` is `internal_llm` fails that check with
`ProviderClassMismatchError` *before* any call is made — the call is refused, not silently
permitted or reclassified.

This does not change what the B4 contextual matrix's `provider_class` dimension studies
(`experiments/contextual_matrix.py`'s `provider_class_employee_name` comparison, over
`GovernanceContext.provider_class`, which stays `internal_llm` vs `external_llm` as
documented in `docs/hr-policy-matrix.md`): that dimension is a property of the *request*
policy evaluates, not of which real provider answers it. `FakeProvider` keeps its existing
experimental flexibility — the runner sets its `provider_class` attribute per case
(`experiments/execution.py`) so it can stand in for whichever class a comparison is studying,
including `internal_llm`. That flexibility is intentionally not extended to
`AnthropicProvider`: `FakeProvider` is an experimental stand-in with no real transport behind
it, so representing a class it does not call is harmless, whereas `AnthropicProvider` is a
concrete external boundary and must never claim to be a boundary it is not. A genuine
evaluation of the `internal_llm` condition against a *real* provider requires a provider that
actually runs inside the organizational trust boundary — no such provider exists in this
codebase yet, and this fix does not add one.

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

`ADG_PROVIDER` unset, empty, whitespace-only, or explicitly `fake` yields `FakeProvider`.
`anthropic` selects the real adapter. **Any other non-empty value — including a typo such as
`anthrpic` — raises `ProviderConfigurationError` at configuration time.** This changed under
review (T22 / PR #62): an unrecognized value previously fell back to `FakeProvider` silently,
which could make a batch planned as real-provider execute on `FakeProvider` without anyone
noticing — exactly the silent substitution protocol §9.4 forbids. `ADG_PROVIDER` is never
autocorrected and never mapped to another provider on its own judgment; an unrecognized value
is a configuration error, full stop.

### What reads `ADG_PROVIDER`

`application/settings.build_default_service` — the default service both `api/app.create_app()`
and `cli.main()` build when no service is injected — constructs its provider through
`providers.build_provider_from_env`, and derives the default `GovernanceContext.provider_class`
from whatever that returns. So a deployment enables the real provider by setting
`ADG_PROVIDER=anthropic` and nothing else; no custom service has to be injected, and there is
no environment variable that can make the governance context disagree with the wired provider.

That agreement is load-bearing rather than cosmetic: `invoke_provider` compares
`context.provider_class` against the provider's own and refuses the call on a mismatch, and
policy itself reads `provider_class` (see `docs/hr-policy-matrix.md`, where `employee_name` is
treated more restrictively for `external_llm`). A context left at `fake` over a real adapter
would block every request in the deployed demo; a context claiming `external_llm` over
`FakeProvider` would apply the external rules to a call that never leaves the process.

Selecting the real adapter builds no SDK client and reads no credential at construction time —
the client is created lazily at the first call — so an API with `ADG_PROVIDER=anthropic` and no
key still starts and still serves `/health`, and fails closed only when a call is attempted.

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
| `ADG_ANTHROPIC_MODEL_ID` | `claude-opus-5` | exact model id, never date-suffixed — must be in the validated allowlist |
| `ADG_ANTHROPIC_MAX_OUTPUT_TOKENS` | `16000` | `max_tokens` for one call |
| `ADG_ANTHROPIC_EFFORT` | `high` | `low` / `medium` / `high` / `xhigh` / `max` |
| `ADG_ANTHROPIC_THINKING` | `adaptive` | `adaptive` or `disabled` |
| `ADG_ANTHROPIC_TIMEOUT_SECONDS` | `60` | native transport timeout on the SDK client |
| `ADG_ANTHROPIC_BASE_URL` | — | **forbidden** — setting this raises `ProviderConfigurationError` (see below) |
| `ADG_ANTHROPIC_API_KEY_ENV_VAR` | `ANTHROPIC_API_KEY` | the *name* of the credential variable |

`provider_class` is deliberately absent from this table: it is fixed to `external_llm` on
`AnthropicProvider` and is not configuration — see "`provider_class` is a fixed fact about
`AnthropicProvider`, not configuration" above.

`thinking_mode=disabled` combined with effort `xhigh`/`max` is rejected by the API; the
configuration object refuses that combination at construction rather than letting it become
an HTTP 400 part-way through a batch.

## Model allowlist

`AnthropicProviderConfig.model_id` only accepts a model id from
`settings.SUPPORTED_ANTHROPIC_MODEL_IDS` — currently just the default, `claude-opus-5`. This
exists for reproducibility and methodology, not because the shared `Provider` protocol
architecturally limits which models could be called: the properties this adapter records as
universal (no sampling parameters; the response/usage shape it reads) were verified against
that specific model, not against every model id the Anthropic API happens to accept. An older
or unvalidated model id could differ on any of those properties, which would make
`decoding_config`'s `sampling_parameters_supported: false` a false provenance claim rather
than a verified one.

`ADG_ANTHROPIC_MODEL_ID` set to anything outside the allowlist raises
`ProviderConfigurationError` at configuration time — never accepted on the theory that "the
API will validate it later". Extending the allowlist requires independently verifying a new
id's sampling, thinking, effort, `max_tokens`, response-shape and usage-metadata semantics
first.

## base_url override — forbidden

Earlier revisions of this adapter accepted `ADG_ANTHROPIC_BASE_URL` for a proxy or
compatible-gateway override and recorded only a boolean `base_url_overridden` flag in
`configuration_record()`. Under review that was found to be insufficient provenance: two
batches could both record `base_url_overridden: true` and still have used different backends,
and a gateway/proxy would introduce a new, unrecorded experimental variable. **The override is
now forbidden outright**: any non-`None` `base_url` — including via `ADG_ANTHROPIC_BASE_URL`
— raises `ProviderConfigurationError` at `AnthropicProviderConfig` construction. The adapter
always uses the SDK's official endpoint. `configuration_record()` states this fixed policy as
`base_url_policy`, a string, rather than a flag that could vary silently.

The rejection message never echoes the attempted URL: a URL can carry an embedded credential
(userinfo, query string, a token in the path), and construction failing must not become a new
side channel for it.

See [`.env.example`](../.env.example) for a copyable, placeholder-only version.

## Timeout and cancellation

Two layers, both required, and now **deterministically related** rather than two independent
settings that can silently diverge:

- **Native transport timeout** — configured on the SDK client itself
  (`ADG_ANTHROPIC_TIMEOUT_SECONDS`, default 60s). This is the only one that can actually stop
  an in-flight HTTP request.
- **Caller-side wall-clock deadline** — enforced by `invoke_provider` itself. It guarantees
  the caller returns even if a provider hangs, by abandoning the worker thread — but it does
  **not** stop the underlying request, so if it is shorter than the native timeout the caller
  gives up while the request is still guaranteed to be alive underneath it.

**Fixed under review (T22 / PR #62, blocker 2):** the default caller-side deadline
(`providers.DEFAULT_TIMEOUT_SECONDS`, 30s) was *shorter* than the default native transport
timeout (60s) for every code path except the live integration test, which worked around it
manually with `provider timeout + 10s`. The scientific/runner path
(`experiments.execution.execute_case`, and therefore `run_pilot`/`run_case_for_treatment`) did
not have that workaround and used the plain 30s default even when a real, 60s-configured
provider was injected.

The fix: `providers.caller_timeout_for_provider(provider)` derives the caller-side deadline
from the provider's own native timeout whenever it exposes one
(`provider.native_timeout_seconds` — `AnthropicProvider` does), as
`native timeout + providers.CALLER_TIMEOUT_GRACE_SECONDS` (a fixed, documented, versionable
10s grace — the same buffer the live integration test used manually). This guarantees
`caller deadline > native timeout` by construction, for exactly one call site to get right,
rather than trusting every caller to compute a compatible pair of numbers independently. A
provider with no `native_timeout_seconds` attribute (`FakeProvider`, and every provider
written before this helper existed) is unaffected: `caller_timeout_for_provider` returns the
unchanged 30s default. `execute_case` calls this helper itself, so `run_pilot(provider=...)`
gets the correct deadline automatically — no caller needs to compute it by hand, and the live
integration test now calls the same helper instead of maintaining its own `+10s` arithmetic.

A timeout surfaces as `ProviderTimeoutError` (a `ProviderError`), is recorded in the audit
record as a provider failure, and is never retried — exactly one call is attempted regardless
of which deadline was used, and a timeout never falls back to a second call or a different
provider.

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
version, the fixed `base_url_policy` statement, and the cost-accounting statement. It is
shaped to drop straight into `artifacts.write_pilot_artifacts(reproducibility=...)`.

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
