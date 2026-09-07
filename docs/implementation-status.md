# Implementation status

Last updated: 2026-09-07 (T06 / PR #22 under validation; T17 / Issue #24 and the T13 / Issue #16 fail-closed-GENERALIZE blocker are now resolved on PR #22; T16 / Issue #23 remains the only open item before T06 / Issue #3 can close)

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

The core is useful and reviewable, but **T06 / Issue #3 must remain open after PR #22**. Independent review found two missing parts of the B2 boundary:

1. **T16 / Issue #23 — real pseudonym-scope lifecycles (still open).** REQUEST, DOCUMENT and SESSION currently derive their partition key from requester identity/role because `GovernanceContext` has no `request_id`, `document_id` or `session_id`. The scope label is isolated, but its intended lifetime is not enforced. Missing identifiers for the resolved scope must fail closed rather than falling back to requester identity.
2. **T17 / Issue #24 — guessing-resistant pseudonyms (resolved on this PR).** `InMemoryVault` no longer derives the pseudonym from the original value or from any public/predictable context at all: `pseudonymize()` generates an opaque random token (via a CSPRNG `token_factory`, `secrets.token_hex(16)` by default — 128 bits) and stores the mapping; there is nothing left to invert offline. Stability within a partition still comes from the forward-map lookup, not from the generator being deterministic. The `token_factory` is injectable so experiments can use a deterministic generator; the production default is explicitly *not* required to be reproducible across independent vault instances (`tests/test_vault.py` pins both directions). Collision handling is unchanged in shape and still verified against a degenerate (constant-output) token factory. The `PSEUDO-{category}-` prefix is kept for audit readability only — with a random token the category no longer helps an attacker guess anything.

T06 is complete only after T16 is resolved and merged.

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
3. Merge PR #22 now that both review blockers are resolved. It closes Issue #16 / T13 and Issue #24 / T17, but **must not close Issue #3 / T06**.
4. T16 / Issue #23 — add real REQUEST / DOCUMENT / SESSION lifecycle identifiers and fail closed when the resolved scope lacks its required identifier.
5. Complete T06 / Issue #3 after T16 is merged.
6. T11 / Issue #12 — common provider boundary + deterministic `FakeProvider`.
7. Complete the shared B0 — Direct / B1 — Static Sanitization / B2 — Reversible Pseudonymization HR end-to-end flow and structural audit trail.
8. Only then move to B3 — Task-aware and B4 — Policy-governed on top of the corrected B2 vault boundary.
9. Experiment runner / Issue #8 produces authoritative utility/exposure numbers only after the above prerequisites are frozen.

## Not started / incomplete in Milestone 1

- real REQUEST / DOCUMENT / SESSION lifecycle semantics (T16 / Issue #23);
- `SQLiteVault` or another persistent/shared vault backend;
- a detection rule emitting `birth_date` (its `GENERALIZATION_STRATEGIES` entry exists but is currently unreachable);
- pseudonym property tests with Hypothesis;
- deterministic `FakeProvider` implementation;
- complete structural audit trail;
- end-to-end B0/B1/B2 runner over the same HR cases.

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
- pseudonyms are stable for the **real authorized lifecycle** of the resolved scope;
- external pseudonyms are not guessable from a public unkeyed digest construction (resolved: opaque random tokens, Issue #24 / T17);
- vault originals and secrets never reach the provider or telemetry;
- the response round-trip reconstructs authorized pseudonyms correctly;
- audit data captures the relevant stages without logging sensitive text by default;
- the common deterministic `FakeProvider` path works for B0/B1/B2;
- CI is green.

PR #22 implements a substantial part of these criteria, but **Milestone 1 is not complete on the branch or on master** while T16, `FakeProvider` and the end-to-end/audit path remain pending.

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
- Provider adapter/FakeProvider: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/12
