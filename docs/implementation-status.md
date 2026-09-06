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

## In progress

### Detector + B1

GitHub Issue: #5 — `Implement sensitive-data detector and B1 static sanitizer`

Branch: `feat/m1-b1-detector`

At the 2026-09-06 status check, this branch had **0 commits ahead of `master`**. The work item is prepared but implementation has not started yet.

Planned first work:

1. TDD for deterministic spans and offsets;
2. deterministic overlap resolution;
3. structured-identifier rules/regex;
4. controlled simplified-HR fixtures;
5. B1 static sanitizer independent of contextual policy/task/vault;
6. metadata-only OpenTelemetry instrumentation.

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
