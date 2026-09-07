# Implementation status

Last updated: 2026-09-07 (T18 / Issue #25 — B0 — Direct — implemented on branch `feat/t16-pseudonym-scope-lifecycles`, in validation, alongside T16 / Issue #23 and T11 / Issue #12; with T16, T06 / Issue #3 is complete apart from anything else still listed below as not started)

This file tracks **what is implemented now**. Architectural decisions belong in ADRs; research-proposal versions remain separate documents.

## Current milestone

Milestone 1 is the first functional vertical slice:

- direct HR text input;
- B0 — Direct;
- B1 — Static Sanitization;
- B2 — Reversible Pseudonymization;
- deterministic `FakeProvider`;
- local vault and authorized reconstruction;
- auditable end-to-end execution without requiring a real external LLM.

## Completed on master

- Milestone 1 architecture frozen in ADR 0001.
- `DisclosureAction`: `PRESERVE`, `PSEUDONYMIZE`, `GENERALIZE`, `REMOVE`, `BLOCK_REQUEST`, `TASK_DEPENDENT`.
- `GovernanceContext`, pseudonym-scope policy model and versioned YAML policy engine.
- Fail-closed policy resolution and policy precedence over task-awareness.
- Role/user pseudonym-scope ceilings.
- OpenTelemetry + OTLP foundation and local Jaeger.
- GitHub Actions CI on CPython 3.13.13.
- B0–B4 experimental design, now named semantically as Direct → Static Sanitization → Reversible Pseudonymization → Task-aware → Policy-governed.
- deterministic detector and B1 — Static Sanitization.
- fail-closed `SensitiveSpan` validation shared at the transformation boundary.
- T15 semantic treatment naming (`Treatment` enum, semantic module/class/OTel names).
- Intermittent `tests/test_telemetry_privacy.py` failure fixed: the root cause (reproduced over 60 full-suite runs, 2 failures) was `duration_ms` span attributes carrying raw `time.perf_counter()` deltas with ~17 significant digits of floating-point noise, which could — purely by coincidence — contain the same digit sequence as an unrelated forbidden value (e.g. a measured duration of `0.0850000069476664` ms contains the substring `"8500"`, matching the fixture's salary amount). Fixed at the source via a new `observability.elapsed_ms_since()` helper that rounds to 3 decimal places, which bounds the digit run on either side of the decimal point below any 4-digit forbidden substring for realistic (sub-second) durations. `tests/conftest.py`'s `recorded_spans` fixture was also hardened from a session-wide shared exporter/provider to a function-scoped one installed only for the requesting test's duration, so a test's assertions can never observe another test's spans regardless of run order. Verified with 0 failures across 60 full-suite runs after the fix.

Relevant merged work: PR #10 / Issue #2, PR #13 / Issue #1, PR #15 / Issue #5, PR #19 / Issue #17 and PR #21 / Issue #20.

## In validation

### T06 / Issue #3 — B2 — Reversible Pseudonymization core

PR #22 implements the core B2 mechanism:

- `Vault` abstraction + `InMemoryVault`;
- `ReversiblePseudonymizer` with `Treatment.REVERSIBLE_PSEUDONYMIZATION`;
- a static, task-independent category → action mapping, preserving the B2→B3 isolation boundary;
- shared malformed-span validation from T14;
- stable mappings inside the currently supplied vault partition;
- collision handling;
- authorized local reconstruction;
- multi-entity round-trip coverage;
- metadata-only OTel instrumentation.

Independent review found two missing parts of the B2 boundary, both now resolved:

1. **T16 / Issue #23 — real pseudonym-scope lifecycles (implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge).** `GovernanceContext` now carries optional `request_id`, `document_id` and `session_id`. `_scope_key` (`transformations/reversible_pseudonymization.py`) keys REQUEST on `request_id`, DOCUMENT on `document_id`, SESSION on `session_id`, and ORGANIZATION on the domain alone, unchanged — with no fallback to requester identity/role for the first three. When the resolved scope's required identifier is absent, `sanitize()` fails closed (`status="blocked"`, empty payload) and `reconstruct()` returns the response unchanged, rather than resolving some other partition. `PolicyRepository.resolve_pseudonym_scope`'s fail-closed default for an unresolvable policy (REQUEST) is kept as-is, with a comment recording that it now compounds with the new requirement (an unresolvable policy plus a missing `request_id` blocks), covered by a dedicated test. `configs/policies/hr-v1.yaml`'s `hr_viewer` REQUEST ceiling is pinned to actually change cross-request linkability (different pseudonyms across two requests), contrasted with a SESSION-permitted role staying stable across the same two requests.
2. **T17 / Issue #24 — guessing-resistant pseudonyms (resolved on PR #22).** `InMemoryVault` no longer derives the pseudonym from the original value or from any public/predictable context at all: `pseudonymize()` generates an opaque random token (via a CSPRNG `token_factory`, `secrets.token_hex(16)` by default — 128 bits) and stores the mapping; there is nothing left to invert offline. Stability within a partition still comes from the forward-map lookup, not from the generator being deterministic. The `token_factory` is injectable so experiments can use a deterministic generator; the production default is explicitly *not* required to be reproducible across independent vault instances (`tests/test_vault.py` pins both directions). Collision handling is unchanged in shape and still verified against a degenerate (constant-output) token factory. The `PSEUDO-{category}-` prefix is kept for audit readability only — with a random token the category no longer helps an attacker guess anything.

With T16 implemented, **T06 / Issue #3 is complete apart from anything else still listed in this file as not started** (see "Not started / incomplete in Milestone 1" below) — it remains open only pending T16's own review/merge.

### T11 / Issue #12 — external provider adapter interface (implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge)

A new `src/adaptive_disclosure_gateway/providers/` package implements the single adapter boundary shared by every treatment:

- `Provider` (`providers/base.py`): a `Protocol` with one method, `generate(request: ProviderRequest) -> ProviderResponse`, plus a `provider_class` class attribute (mirroring the `treatment` class-attribute convention). `ProviderRequest` carries exactly two fields — `payload` (the text a treatment already decided to disclose, e.g. `DisclosureResult.external_payload`) and `task` (the non-sensitive prompt/task instruction). No `GovernanceContext`, raw document, detected span or policy/vault object is reachable from a provider; `tests/test_provider_isolation.py` pins both the exact `ProviderRequest` field set and, at the AST level, that `providers/` imports none of policy, vault or detection.
- `invoke_provider` (`providers/base.py`): the single entrypoint every treatment must call a provider through. It checks `provider.provider_class` against a caller-supplied `expected_provider_class` (normally `GovernanceContext.provider_class`, already consulted by `PolicyRule`/`PolicyOverride`) and raises `ProviderClassMismatchError` *before* invoking the provider on a mismatch — the mismatched provider is never called. It enforces a hard wall-clock `timeout` itself (via a one-shot `ThreadPoolExecutor`, not merely trusting the provider), makes exactly one call with no retry, and turns any provider exception — including a timeout — into `ProviderError`/`ProviderTimeoutError` without chaining the original exception's message (`from None`), so a third-party provider client's own error text cannot leak request content through the exception chain. A caller must treat any `ProviderError` as the whole request blocked; nothing in this module ever falls back to B0 — Direct.
- `count_transmitted_bytes` (`providers/base.py`): the documented transmitted-volume counting rule for issue #8's metric — UTF-8 encoded byte length of `payload` only, deliberately excluding `task` (held constant across treatments per docs/experimental-design.md, so it must not move a metric meant to isolate what differs between treatments).
- `FakeProvider` (`providers/fake.py`): deterministic and offline — `generate` is a pure function of `(task, payload)` (SHA-256 digest, no randomness/clock/state), used as the default provider across B0–B2 so comparisons are never confounded by model variance. Fixed class-attribute reproducibility metadata (`model_id`, `model_snapshot`, `decoding_config`) is identical across independently constructed instances.

Covered in `tests/test_providers.py` and `tests/test_provider_isolation.py`: FakeProvider determinism and non-constant output, reproducibility metadata stability, the transmitted-bytes counting rule (multi-byte UTF-8, task-length independence), `provider_class` mismatch detection (provider never invoked on mismatch) and the matching success path, fail-closed behavior on both a raising stub and a timing-out stub (single attempt, no retry, bounded wall-clock latency on timeout), and a runtime isolation check that runs the HR fixture through `StaticSanitizer` and asserts a recording stub provider never receives the sensitive originals in any field of what it was given.

Not yet built (explicitly out of scope for this issue, tracked for later work): a real external/Ollama provider adapter (Post-Milestone 1 per this file), and the end-to-end runner wiring that would call `invoke_provider` from within B0–B4 themselves (Issue #26).

### T18 / Issue #25 — B0 — Direct (implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge)

`transformations/direct_disclosure.py` adds `DirectDiscloser`, the control treatment B0→B1 is measured against, which did not exist before this ticket:

- `treatment = Treatment.DIRECT`; shares the exact same `sanitize(request, spans) -> DisclosureResult` contract as `StaticSanitizer`/`ReversiblePseudonymizer`, so one call site can drive all three — `spans` is accepted for that reason only and is never read;
- the external payload equals `request.text` exactly; no detection, policy or transformation logic participates in producing it — `spans` is discarded (`del spans`) rather than inspected;
- still auditable: `DisclosureResult.decisions`/`transformations` are never empty — each carries one entry (sentinel category `"direct_disclosure"`, action `PRESERVE`) recording that the full text was disclosed unchanged, rather than leaving an empty audit trail that would make the audit stage itself a confound between treatments;
- the OTel span (`direct_disclosure.sanitize`) carries `treatment`, a `blocked` flag and timing only — never the payload or the raw text, which for B0 are the same string; pinned by a new `tests/test_telemetry_privacy.py::test_b0_span_attributes_never_contain_the_raw_text_even_though_it_is_the_payload`;
- isolation is stricter than B1: `tests/test_treatment_isolation.py` now also pins that `direct_disclosure.py` imports none of policy, vault, detection or task-awareness code (B1 still imports `detection.overlap` to resolve overlapping spans before slicing; B0 never slices the text at all, so it needs no detection dependency either).

Covered in the new `tests/test_direct_disclosure.py` (unchanged-disclosure and audit-trail assertions) plus the isolation and telemetry extensions above. Full suite: 137 tests.

Not yet built (out of scope for this issue, tracked under Issue #26): the end-to-end runner/audit-path wiring that would actually call `DirectDiscloser` (and `invoke_provider`) as part of a B0/B1/B2 comparison over the same case.

### T13 / Issue #16 — semantic GENERALIZE

PR #22 replaces the previous redaction-equivalent placeholder with a central category strategy registry:

- salary → deterministic fixed-width numeric band;
- date strategy → year/month;
- `GENERALIZE` remains distinguishable from `REMOVE`;
- minimum numeric granularity is enforced;
- an unconfigured GENERALIZE category becomes `BLOCK_REQUEST`;
- B1 and B2 share the same generalization implementation.

Independent review found one merge blocker, now resolved on this PR:

- **Fail-closed on configured-but-unparseable values.** Both `static_sanitization.py` and `reversible_pseudonymization.py` now resolve every span's action *and* attempt any GENERALIZE span's generalization in one pre-pass, before any text slicing starts (`_resolve_actions_and_generalized_values`). A value a configured strategy cannot parse (e.g. a free-text `Salary:` field) downgrades just that span to `BLOCK_REQUEST`, exactly like an unconfigured category — the request returns `status="blocked"` with an empty payload instead of raising `GeneralizationError` mid-slice. Covered for both treatments in `tests/test_static_sanitization.py` / `tests/test_reversible_pseudonymization.py`, plus telemetry coverage in `tests/test_telemetry_privacy.py`.
- **Non-leaking error messages.** The four `raise GeneralizationError(...)` sites in `generalization.py` no longer interpolate the raw value; they name the category and failure kind only. `MonthYearDateStrategy.generalize` suppresses `datetime.strptime`'s own `ValueError` with `raise ... from None` so its value-bearing message cannot resurface through a formatted traceback. Pinned in `tests/test_generalization.py`, and generalized into a codebase-wide AST-based invariant test, `tests/test_no_sensitive_value_in_raises.py` (see CLAUDE.md's "No-leak invariant").

PR #22's last reviewed CI run was green with 96 tests; the fixes above bring the suite to 109.

**Known scope note, not fixed here:** `GENERALIZATION_STRATEGIES` configures a `birth_date` strategy, but no detection rule currently emits a `birth_date` category, so that strategy is unreachable in practice. Left as a follow-up (adding a `birth_date` detection rule is out of scope for this PR).

## Planning after PR #22 review

Recommended execution order:

1. ~~Fix the T13 configured-but-unparseable `GENERALIZE` fail-closed/non-leaking path on PR #22 and rerun full CI.~~ Done on PR #22.
2. ~~T17 / Issue #24 — replace public deterministic digest pseudonyms with opaque/keyed pseudonyms while keeping deterministic test configuration available.~~ Done on PR #22 (opaque random tokens).
3. ~~Merge PR #22 now that both review blockers are resolved. It closes Issue #16 / T13 and Issue #24 / T17, but must not close Issue #3 / T06.~~ Done.
4. ~~T16 / Issue #23 — add real REQUEST / DOCUMENT / SESSION lifecycle identifiers and fail closed when the resolved scope lacks its required identifier.~~ Implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge.
5. Complete T06 / Issue #3 after T16 is merged.
6. ~~T11 / Issue #12 — common provider boundary + deterministic `FakeProvider`.~~ Implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge.
7. ~~T18 / Issue #25 — B0 — Direct control treatment.~~ Implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge.
8. Complete the shared B0 — Direct / B1 — Static Sanitization / B2 — Reversible Pseudonymization HR end-to-end flow and structural audit trail, wiring `invoke_provider` into that flow (Issue #26; not yet done: `providers/` and now all three treatment classes exist as standalone units, but no runner calls them together over the same case yet).
9. Only then move to B3 — Task-aware and B4 — Policy-governed on top of the corrected B2 vault boundary.
10. Experiment runner / Issue #8 produces authoritative utility/exposure numbers only after the above prerequisites are frozen.

## Not started / incomplete in Milestone 1

- `SQLiteVault` or another persistent/shared vault backend;
- a detection rule emitting `birth_date` (its `GENERALIZATION_STRATEGIES` entry exists but is currently unreachable);
- pseudonym property tests with Hypothesis;
- complete structural audit trail (each treatment now records its own audit entries in isolation — see T18 / Issue #25 above for B0 — but nothing yet assembles a shared, end-to-end audit record across a runner);
- end-to-end B0/B1/B2 runner over the same HR cases, calling `providers.invoke_provider` (the provider adapter and all three treatment classes are implemented — see T11 / Issue #12 and T18 / Issue #25 above — but nothing yet drives them together from a runner; tracked under Issue #26).

`SQLiteVault` is not required for the current in-process experiment slice unless a later execution design requires persistence across processes.

## Post-Milestone 1

- B3 — Task-aware minimization, retaining B2's reversible mechanism;
- B4 — Policy-governed disclosure, retaining B3's reversible mechanism and adding the explicit contextual policy action-space constraint;
- Docling ingestion adapter for PDF/DOCX/XLSX/images;
- richer contract-oriented corpus and semantic-relation tests;
- real external/Ollama provider adapters;
- visual audit/comparison UI;
- experiment runner and full metric collection.

## Milestone 1 exit criteria

Milestone 1 is complete when the same controlled HR case can run through B0 — Direct, B1 — Static Sanitization and B2 — Reversible Pseudonymization and tests demonstrate that:

- malformed/invalid span metadata fails closed rather than leaking values;
- `REMOVE` content does not appear in the external payload;
- `BLOCK_REQUEST` stops the entire external request;
- pseudonyms are stable for the **real authorized lifecycle** of the resolved scope (resolved: T16 / Issue #23, real `request_id`/`document_id`/`session_id` identifiers with fail-closed enforcement when the resolved scope's identifier is missing);
- external pseudonyms are not guessable from a public unkeyed digest construction (resolved: opaque random tokens, Issue #24 / T17);
- vault originals and secrets never reach the provider or telemetry (partially resolved: `providers/` itself enforces this at the adapter boundary and is covered by a runtime isolation test — T11 / Issue #12 — but no treatment or runner calls it yet, so this is not yet demonstrated end-to-end);
- the response round-trip reconstructs authorized pseudonyms correctly;
- audit data captures the relevant stages without logging sensitive text by default;
- the common deterministic `FakeProvider` path works for B0/B1/B2 (resolved as a standalone adapter: T11 / Issue #12 delivers `Provider`/`invoke_provider`/`FakeProvider`; still pending is B0/B1/B2 actually calling it, tracked under "Complete the shared ... end-to-end flow" above);
- CI is green.

B0 — Direct itself now exists (T18 / Issue #25), so all three treatment classes needed for the B0→B1→B2 comparison are implemented; what remains for Milestone 1 exit is exclusively the end-to-end runner/audit-path wiring under Issue #26 (step 4 of this branch's plan), not any missing treatment.

PR #22 plus T16, T11 and T18 (this branch) implement a substantial part of these criteria, but **Milestone 1 is not complete on the branch or on master** while the end-to-end/audit path wiring `providers.invoke_provider` into B0/B1/B2 remains pending.

## References

- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- Experimental design: `docs/experimental-design.md`
- Foundation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/10
- B0–B4 design PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/13
- Detector/B1 PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/15
- Span offset validation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/19
- Semantic naming PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/21
- B2 core + semantic GENERALIZE PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/22
- B2 core issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/3
- Semantic GENERALIZE: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/16
- Pseudonym lifecycle follow-up: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/23
- Pseudonym guessing-resistance (resolved on PR #22): https://github.com/Sheliga/adaptive-disclosure-gateway/issues/24
- Provider adapter/FakeProvider (implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge): https://github.com/Sheliga/adaptive-disclosure-gateway/issues/12
- B0 — Direct (implemented on `feat/t16-pseudonym-scope-lifecycles`, pending review/merge): https://github.com/Sheliga/adaptive-disclosure-gateway/issues/25
- End-to-end path + audit trail (next on this branch): https://github.com/Sheliga/adaptive-disclosure-gateway/issues/26
