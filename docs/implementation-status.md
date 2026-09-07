# Implementation status

Last updated: 2026-09-06 (PR #19 / T14 under validation)

This file tracks **what is implemented now**. Architectural decisions belong in ADRs; research-proposal versions remain separate documents.

## Current milestone

Milestone 1 is the first functional vertical slice:

- direct HR text input;
- B0 direct disclosure;
- B1 static sanitization;
- B2 static reversible pseudonymization;
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

### Detector + B1

GitHub Issue: #5 — `Implement sensitive-data detector and B1 static sanitizer`

Merged PR: #15 — `Implement sensitive-data detector and B1 static sanitizer`

- `Detector` (`src/adaptive_disclosure_gateway/detection/`): deterministic regex rules for structured Brazilian identifiers (CPF, CNPJ, e-mail, phone, matched only in their canonical punctuated format) plus a deliberately simple labeled-line detector (`Label: value`) for the controlled HR fixture's `employee_name`, `salary`, `department` and `medical_data` categories.
- The detector is intentionally **not** a general NER component and depends on no NER library.
- Deterministic overlap resolution: longest match wins; equal-length overlaps are broken by fixed category precedence, then leftmost start, category name and value.
- `B1StaticSanitizer`: fixed task- and policy-independent category → action mapping, with static-analysis tests preventing dependency on policy, task-awareness or vault code.
- `REMOVE`, `PRESERVE`, `GENERALIZE` and `BLOCK_REQUEST` paths are covered by tests; an unmapped category blocks rather than silently disclosing.
- OpenTelemetry detector/B1 spans are metadata-only; tests assert that raw text, detected values and external payloads do not appear in span attributes.
- Controlled synthetic HR fixture covers all five frozen categories and both allowed and blocking flows.
- PR #15 CI passed with 39 tests; Issue #5 closed.

Known limitations retained deliberately at this stage:

- CPF/CNPJ detection is format-only; check digits are not validated yet.
- Labeled HR extraction is controlled-fixture parsing, not free-text NER.
- Precision/recall measurement waits for the ground-truth corpus.

## In validation

### T14 / Issue #17 — fail-closed span offset validation

GitHub PR: #19 — `Fail closed on malformed or missing SensitiveSpan offsets`

Review of the merged B1 implementation found that `SensitiveSpan.start` / `end` were optional in the domain model while the transformation boundary normalized missing offsets to zero (`span.start or 0`). A malformed span could therefore reach a nominal `REMOVE` decision while the original value remained in an `allowed` external payload. The same coercion in overlap resolution could silently turn malformed metadata into a harmless-looking zero-length `(0, 0)` interval.

PR #19 addresses the defect at two layers:

- **Domain model** (`domain.py`): `SensitiveSpan.start` / `end` are required `int` fields, and construction rejects negative, inverted and zero-length offsets.
- **Transformation boundary** (`transformations/span_validation.py`): shared validation checks `end <= len(text)` and `text[start:end] == span.value` before payload slicing. `B1StaticSanitizer.sanitize` fails the whole request closed (`status="blocked"`, empty payload) if any supplied span is invalid.
- `resolve_overlaps` no longer normalizes malformed offsets to zero and now raises an explicit `ValueError` whose message contains category/offset metadata but not `span.value`.
- The shared validator is deliberately outside `b1.py` so B2/B3/B4 can reuse the same boundary rather than reimplementing it.
- Tests cover missing, negative, inverted, zero-length, out-of-bounds and value/offset-mismatch cases, including model-validation bypass through `model_construct`.
- PR #19 CI is green with 58 tests.

Independent review found the implementation technically sound. The work remains **in validation**, not completed, until PR #19 is merged and Issue #17 closes. Trello card T14 must remain in `Validação` until that happens.

## Remaining follow-up from B1 review

### T13 / Issue #16 — semantic GENERALIZE

B1 currently implements `GENERALIZE` as a fixed `[REDACTED:<category>]` placeholder. This is safe for disclosure but semantically equivalent to removal, so it cannot yet support a fair utility comparison where generalization is expected to preserve partial information. A category-specific deterministic generalization strategy is required before the experiment runner produces comparative utility numbers.

This does **not** invalidate the completed B1 engineering slice, but it must be corrected before Issue #8 produces scientific measurements.

## Recommended next execution order

1. Validate and merge PR #19 / T14; Issue #17 must close before B2 starts.
2. T06 / Issue #3 — B2 reversible pseudonym vault and authorized reconstruction.
3. T11 / Issue #12 — deterministic `FakeProvider` through the common provider adapter boundary, as required to complete Milestone 1 end-to-end.
4. Complete the shared B0/B1/B2 HR execution path and structural audit trail.
5. T13 / Issue #16 before utility/metric collection becomes authoritative.

T06 has moved to `Próximas` because its blocker is implemented and under validation, but implementation must not start concurrently with PR #19 on the same `SensitiveSpan`/transformation boundary. T13 can be implemented before or alongside B2 if convenient; it blocks meaningful task-utility measurement, not the basic B2 pseudonym round-trip.

## Not started / incomplete in Milestone 1

- `InMemoryVault` / `SQLiteVault`;
- B2 reversible pseudonymization;
- pseudonym property tests with Hypothesis;
- deterministic `FakeProvider` implementation;
- authorized local reconstruction;
- complete structural audit trail;
- end-to-end B0/B1/B2 runner over the same HR cases.

## Post-Milestone 1

- B3 task-aware minimization without strong contextual organizational policy constraints;
- B4 proposed policy-governed disclosure approach;
- Docling ingestion adapter for PDF/DOCX/XLSX/images;
- richer contract-oriented corpus and semantic-relation tests;
- real external/Ollama provider adapters;
- visual audit/comparison UI;
- experiment runner and full metric collection.

## Milestone 1 exit criteria

Milestone 1 is complete when the same controlled HR case can run through B0, B1 and B2 and tests demonstrate that:

- malformed/invalid span metadata fails closed rather than leaking values;
- `REMOVE` content does not appear in the external payload;
- `BLOCK_REQUEST` stops the entire external request;
- pseudonyms are stable within the authorized scope;
- vault originals never reach the provider;
- the response round-trip reconstructs authorized pseudonyms correctly;
- audit data captures the relevant stages without logging sensitive text by default;
- CI is green.

## References

- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- Experimental design (B0–B4): `docs/experimental-design.md`
- Foundation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/10
- B0–B4 design PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/13
- Detector/B1 PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/15
- Span offset validation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/19
- Completed policy-engine issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/2
- Completed detector/B1 issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/5
- Span offset validation issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/17
- Semantic generalization follow-up: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/16
- B2/vault issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/3
- Provider adapter/FakeProvider issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/12
