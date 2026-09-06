# Implementation status

Last updated: 2026-09-06

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

## Immediate follow-ups from B1 review

### Security blocker before B2

Issue #17 — `Fail closed on malformed or missing SensitiveSpan offsets`

Review of the merged B1 implementation found that `SensitiveSpan.start` / `end` are optional in the domain model while the transformation boundary currently normalizes missing offsets to zero. A malformed externally supplied span can therefore reach a nominal `REMOVE` decision while leaving the original value in an allowed payload.

Before extending the transformation boundary into B2/vault work, malformed spans must fail closed. Coverage must include missing, negative, inverted, out-of-range and value/offset-mismatch cases.

### Experimental correctness follow-up

Issue #16 — `Implement semantic GENERALIZE distinct from redaction`

B1 currently implements `GENERALIZE` as a fixed `[REDACTED:<category>]` placeholder. This is safe for disclosure but semantically equivalent to removal, so it cannot yet support a fair utility comparison where generalization is expected to preserve partial information. A category-specific deterministic generalization strategy is required before the experiment runner produces comparative utility numbers.

This does **not** invalidate the completed B1 engineering slice, but it must be corrected before Issue #8 produces scientific measurements.

## Recommended next execution order

1. Issue #17 — harden `SensitiveSpan` validation / fail-closed transformation behavior.
2. Issue #3 — B2 reversible pseudonym vault and authorized reconstruction.
3. Issue #12 — deterministic `FakeProvider` through the common provider adapter boundary, as required to complete Milestone 1 end-to-end.
4. Complete B0/B1/B2 shared HR execution path and structural audit trail.
5. Issue #16 before utility/metric collection becomes authoritative.

Issue #16 can be implemented before or alongside B2 if convenient, but it is a hard prerequisite for meaningful task-utility results in Issue #8, not for the basic B2 pseudonym round-trip itself.

## Not started / incomplete in Milestone 1

- hardened malformed-span validation (Issue #17);
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
- Completed policy-engine issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/2
- Completed detector/B1 issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/5
- Security hardening follow-up: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/17
- Semantic generalization follow-up: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/16
- B2/vault issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/3
- Provider adapter/FakeProvider issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/12
