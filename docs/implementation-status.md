# Implementation status

Last updated: 2026-09-06 (T14 and T15 merged; T06 / T13 / PR #22 under validation)

This file tracks **what is implemented now**. Architectural decisions belong in ADRs; research-proposal versions remain separate documents.

## Current milestone

Milestone 1 is the first functional vertical slice:

- direct HR text input;
- B0 — Direct disclosure;
- B1 — Static Sanitization;
- B2 — Reversible Pseudonymization;
- deterministic `FakeProvider`;
- local vault and authorized reconstruction;
- auditable end-to-end execution without requiring a real external LLM.

## Completed

- Architecture decisions for Milestone 1 frozen in ADR 0001.
- `DisclosureAction`: `PRESERVE`, `PSEUDONYMIZE`, `GENERALIZE`, `REMOVE`, `BLOCK_REQUEST`, `TASK_DEPENDENT`.
- `GovernanceContext` with domain, purpose, requester role/user, provider class, policy version and requested pseudonym scope.
- Pseudonym scopes: `request`, `document`, `session`, `organization`.
- Versioned YAML policy loading and deterministic evaluation.
- Fail-closed behavior for missing/invalid/ambiguous policy resolution.
- Organizational policy precedence over task-awareness.
- Explicit allowed-action space for `TASK_DEPENDENT`.
- Role/user ceiling for pseudonym persistence scope; task/purpose can only narrow it.
- Simplified HR policy for the first slice.
- OpenTelemetry SDK + OTLP foundation.
- Local Jaeger service through Docker Compose.
- GitHub Actions CI with Ruff and pytest on CPython 3.13.13.
- PR #10 merged into `master`; Issue #2 closed.
- Experimental design B0–B4 formalized in PR #13; Issue #1 closed.
- Project-scoped Trello MCP configuration versioned in PR #14.

### Detector + B1 — Static Sanitization

GitHub Issue: #5 — `Implement sensitive-data detector and B1 static sanitizer`

Merged PR: #15 — `Implement sensitive-data detector and B1 static sanitizer`

- `Detector` (`src/adaptive_disclosure_gateway/detection/`): deterministic regex rules for structured Brazilian identifiers (CPF, CNPJ, e-mail, phone, canonical punctuated format) plus a deliberately simple labeled-line detector (`Label: value`) for the controlled HR fixture's `employee_name`, `salary`, `department` and `medical_data` categories.
- The detector is intentionally **not** a general NER component and depends on no NER library.
- Deterministic overlap resolution: longest match wins; equal-length overlaps are broken by fixed category precedence, then leftmost start, category name and value.
- The Static Sanitization treatment uses a fixed task- and policy-independent category → action mapping, with static-analysis tests preventing dependency on policy, task-awareness or vault code.
- `REMOVE`, `PRESERVE`, `GENERALIZE` and `BLOCK_REQUEST` paths are covered by tests; an unmapped category blocks rather than silently disclosing.
- OpenTelemetry detector/static-sanitization spans are metadata-only; tests assert that raw text, detected values and external payloads do not appear in span attributes.
- Controlled synthetic HR fixture covers all five frozen categories and both allowed and blocking flows.
- PR #15 CI passed with 39 tests; Issue #5 closed.

Known limitations retained deliberately at this stage:

- CPF/CNPJ detection is format-only; check digits are not validated yet.
- Labeled HR extraction is controlled-fixture parsing, not free-text NER.
- Precision/recall measurement waits for the ground-truth corpus.

### T14 / Issue #17 — fail-closed span offset validation

Merged PR: #19 — `Fail closed on malformed or missing SensitiveSpan offsets`

The review of B1 found that malformed `SensitiveSpan` offsets could previously be normalized to zero and reach a nominal removal while the original value remained in an allowed payload. PR #19 fixed that boundary before B2 work.

- `SensitiveSpan.start` / `end` are required `int` fields; normal construction rejects missing, negative, inverted and zero-length offsets.
- Shared validation in `transformations/span_validation.py` checks source-text bounds and `text[start:end] == span.value` before payload slicing.
- Invalid spans fail the whole request closed with `status="blocked"` and an empty external payload.
- `resolve_overlaps` no longer normalizes malformed offsets to `(0, 0)` and fails explicitly without placing `span.value` in the exception.
- The validator is shared so B2/B3/B4 can reuse the same transformation boundary.
- Tests cover missing, negative, inverted, zero-length, out-of-bounds, mismatch and model-validation bypass cases.
- PR #19 merged as commit `0c2ce858cbac9fd6b2a9f107c3f56aad06b8977a`; Issue #17 closed; Trello T14 is completed.

The security dependency that blocked B2 is therefore resolved.

### T15 / Issue #20 — semantic treatment names

Merged PR: #21 — `T15: Adopt semantic names for B0-B4 treatments`

The project now uses semantic names for humans while retaining B0–B4 / `b0`–`b4` as frozen experimental identifiers:

- B0 — Direct;
- B1 — Static Sanitization;
- B2 — Reversible Pseudonymization;
- B3 — Task-aware;
- B4 — Policy-governed.

PR #21 introduces a `Treatment` `StrEnum` with semantic members and frozen values, renames the B1 module/class to `static_sanitization.py` / `StaticSanitizer`, renames the treatment-specific tests, changes OTel namespaces from `b1.*` to `static_sanitization.*`, and keeps `treatment="b1"` as machine-readable experimental data. `CLAUDE.md` records the canonical sequence, TDD expectations and workflow-state rules.

Independent review found no change to the experimental meaning or the B1 isolation/security guarantees. PR #21 merged into `master`; Issue #20 closed.

## In validation

### T06 / Issue #3 — B2 — Reversible Pseudonymization

### T13 / Issue #16 — semantic GENERALIZE

GitHub PR: #22 — `T06 + T13: Reversible Pseudonymization (B2) vault/reconstruction and semantic GENERALIZE`

Implemented together on one branch (T06 first, then T13), since B2's static category → action mapping uses `GENERALIZE` for `salary` and needed *some* generalization behavior to exist before T13 replaced the placeholder.

**T06 — Reversible Pseudonymization (B2):**

- `vault/`: a `Vault` ABC plus `InMemoryVault`, an in-process, non-persistent implementation. Pseudonyms are stable per `(scope, scope_key, category, value)`; different scopes/scope_keys never share mappings. Collisions are disambiguated by mutating the emitted pseudonym string (an incrementing suffix), which terminates even under a digest function that returns the same output regardless of input.
- `transformations/reversible_pseudonymization.py` / `ReversiblePseudonymizer` (`Treatment.REVERSIBLE_PSEUDONYMIZATION`): the same static, task-independent category → action mapping as B1, except identifier categories (`employee_name`, `cpf`, `cnpj`, `email`, `phone`) are `PSEUDONYMIZE`-d instead of `REMOVE`-d. `salary`, `department` and `medical_data` are unchanged from B1.
- `PolicyRepository.is_reconstruction_authorized`: reuses the same fail-closed policy-resolution condition as `decide()` / `resolve_pseudonym_scope()`, so reconstruction of a provider response can be blocked by policy.
- `ReversiblePseudonymizer.reconstruct`: authorized local reconstruction of a provider response, replacing pseudonyms with their originals via the vault. Covered by a round-trip test and a multi-entity contract example (two parties, each with a repeated identifier, whose relationships survive reconstruction).
- `tests/test_treatment_isolation.py` now encodes a per-treatment isolation rule instead of one blanket rule: B1 keeps full isolation (no policy, vault or task-awareness); B2 may import policy/vault narrowly (pseudonym-scope resolution and reconstruction authorization only, never to choose a category's action — pinned by asserting `PolicyRepository.decide()` is never called from B2's source) but still may not import task-relevance/task-analysis, preserving the B2 → B3 isolation boundary from `docs/experimental-design.md`.
- Known simplification: `GovernanceContext` has no explicit per-request/session/document identifier yet, so the vault's scope key is derived from `(domain, requester_id/role)`. REQUEST and DOCUMENT scope are therefore, for now, as durable as SESSION scope; only ORGANIZATION scope (keyed on domain alone) is actually distinguishable. Scopes never share mappings regardless, since the scope name itself is folded into the key.
- Out of scope for this PR: a SQLite-backed `Vault` implementation (`InMemoryVault` only).

**T13 — semantic GENERALIZE:**

- `transformations/generalization.py`: a category-keyed generalization strategy registry (not hardcoded per call site), used by both B1 and B2 wherever they map a category to `GENERALIZE`.
- `NumericBandStrategy`: fixed-width, half-open `[lower, upper)` bands, e.g. `salary "R$ 8500.00"` → `"R$ 5000-10000"`. A documented minimum band width (`MIN_NUMERIC_BAND_WIDTH = 1000.0`) is enforced at construction so a band cannot be configured tight enough to re-identify the original value.
- `MonthYearDateStrategy`: date → `"YYYY-MM"`; day-of-month is never disclosed (a fixed, non-configurable minimum granularity).
- A category mapped to `GENERALIZE` with no registered strategy fails closed (`BLOCK_REQUEST`), resolved before any text is sliced, in both B1 and B2.
- Band boundaries are pinned at both edges (the likely off-by-one bug), along with determinism, non-leakage of the original value, and the fail-closed path for an unconfigured category.

Both under validation: 96 tests passing (up from 59 on `master`), `ruff check .` and `ruff format --check .` clean. PR #22 remains in `Validação` until merged and Issues #3/#16 close.

## Not started / incomplete in Milestone 1

- `SQLiteVault` (persistent/shared vault backend);
- a real per-request/session/document identifier in `GovernanceContext` (the vault scope key currently falls back to requester identity — see T06 above);
- pseudonym property tests with Hypothesis;
- deterministic `FakeProvider` implementation;
- complete structural audit trail;
- end-to-end B0/B1/B2 runner over the same HR cases.

## Recommended next execution order

1. T11 / Issue #12 — deterministic `FakeProvider` through the common provider adapter boundary.
2. Complete the shared B0/B1/B2 HR execution path and structural audit trail.
3. Experiment runner and metric collection (Issue #8), now that B1/B2 GENERALIZE produces comparable utility numbers.

## Post-Milestone 1

- B3 — Task-aware minimization without strong contextual organizational policy constraints;
- B4 — Policy-governed proposed disclosure approach;
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
- pseudonyms are stable within the authorized scope;
- vault originals never reach the provider;
- the response round-trip reconstructs authorized pseudonyms correctly;
- audit data captures the relevant stages without logging sensitive text by default;
- CI is green.

All of the above are implemented on the T06/T13 branch (PR #22, not yet merged); the exit criteria are pending that merge and are not yet claimed as `master`'s state until then.

## References

- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- Experimental design: `docs/experimental-design.md`
- Foundation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/10
- B0–B4 design PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/13
- Detector/B1 PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/15
- Span offset validation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/19
- Semantic naming PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/21
- B2 vault/reconstruction + semantic GENERALIZE PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/22
- Policy-engine issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/2
- Detector/B1 issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/5
- Span offset validation issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/17
- Semantic naming issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/20
- Semantic generalization follow-up: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/16
- B2/vault issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/3
- Provider adapter/FakeProvider issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/12
