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
- GitHub Actions CI with Ruff and pytest.
- PR #10 merged into `master`; Issue #2 closed.

### Detector + B1

GitHub Issue: #5 — `Implement sensitive-data detector and B1 static sanitizer`

Branch: `feat/m1-b1-detector`

- `Detector` (`src/adaptive_disclosure_gateway/detection/`): deterministic
  regex rules for structured Brazilian identifiers (CPF, CNPJ, e-mail, phone,
  matched only in their canonical punctuated format) plus a deliberately
  simple labeled-line detector (`Label: value`) for the controlled HR
  fixture's `employee_name`, `salary`, `department` and `medical_data`
  categories. This is not a general NER component and depends on no NER
  library: a category without a rule is simply not detected.
- Deterministic overlap resolution (`detection/overlap.py`): longest match
  wins; equal-length overlaps are broken by a fixed category precedence,
  then leftmost start, then category name, then value. Total and
  reproducible regardless of input order.
- `B1StaticSanitizer` (`src/adaptive_disclosure_gateway/transformations/b1.py`):
  a fixed, hardcoded category -> action mapping applied to detected spans.
  It does not import or call `PolicyRepository`, task relevance, or a
  pseudonym vault (checked by a static-analysis test over the actual
  imports, not just by convention). Irreversible: `REMOVE` drops the value,
  `GENERALIZE` substitutes a fixed placeholder, `BLOCK_REQUEST` blocks the
  whole request; an unmapped category also fails closed to `BLOCK_REQUEST`.
  `PSEUDONYMIZE` is intentionally unused in B1 since it would require the
  vault B1 does not have.
- OpenTelemetry spans on both the detector and B1 carry only categories,
  counts, a block flag and timing; a dedicated test asserts detected values,
  raw text and the payload never appear in recorded span attributes.
- HR fixture covering all five frozen categories
  (`tests/test_hr_fixture.py`), exercised through both the non-blocking and
  the `medical_data`-blocking path.

Not yet implemented as part of this issue (tracked for later milestone
work): precision/recall measurement against a ground-truth corpus, and
CPF/CNPJ check-digit validation (rules are format-only).

## Not started in Milestone 1

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
- external/Ollama provider adapters;
- visual audit/comparison UI;
- experiment runner and full metric collection.

## Milestone 1 exit criteria

Milestone 1 is complete when the same controlled HR case can run through B0, B1 and B2 and tests demonstrate that:

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
- Merged foundation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/10
- Completed policy-engine issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/2
- Current detector/B1 issue: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/5
