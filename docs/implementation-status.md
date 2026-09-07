# Implementation status

Last updated: 2026-09-07 — post-Milestone 1 planning synchronization after the research-decision review. **Milestone 1 remains complete on `master`.**

This file tracks the current engineering/research state and execution order. Architectural decisions belong in ADRs; experimental definitions belong in `docs/experimental-design.md`; historical PR/Issue descriptions remain in GitHub.

## Current phase

The project has moved from building the first functional vertical slice to preparing and implementing the adaptive research treatments and their evaluation.

Milestone 1 established the common execution/security boundary for:

- direct controlled HR text;
- B0 — Direct;
- B1 — Static Sanitization;
- B2 — Reversible Pseudonymization;
- deterministic `FakeProvider`;
- local vault + authorized reconstruction;
- REQUEST / DOCUMENT / SESSION / ORGANIZATION pseudonym lifecycles;
- opaque guessing-resistant pseudonyms;
- shared provider boundary;
- shared B0/B1/B2 pipeline;
- metadata-only structural audit by default;
- OpenTelemetry metadata-only observability;
- fail-closed/no-leak security invariants across payload, task/prompt, provider request, errors, logs, telemetry, audit and derived identifiers.

PR #27 completed Milestone 1 and was merged at `28fe292cf1e7cb1dfccb999c3f04aed1016f5d8e`; post-merge CI passed.

## Planning decisions frozen after Milestone 1

The research-decision review fixed the immediate experimental direction:

- HR is the pilot domain;
- the pilot corpus is approximately 12–20 controlled cases;
- Contracts is the second priority domain after the first B0–B4 HR pilot;
- Accounting/Finance is optional/third-domain scope if schedule permits;
- every experimental case must carry explicit ground truth;
- task necessity uses `REQUIRED` / `NOT_REQUIRED` as the primary oracle; `HELPFUL` may exist only as auxiliary annotation initially;
- B3 starts with a deterministic, replaceable task analyzer;
- B3 uses a generic fixed action space per category/type, independent of contextual organizational policy;
- B4 adds explicit contextual policy constraints using `domain`, `purpose`, `requester_role`, `provider_class` and `policy_version` in the primary matrix;
- requester-specific overrides remain supported but outside the initial primary matrix;
- ground truth is used for scoring only and must never be privileged treatment input;
- impossible-under-policy tasks must produce explicit block/non-executable outcomes rather than silently widening permission;
- utility/overhead interpretation thresholds are calibrated from the pilot and frozen before the main experiment, not chosen post hoc;
- `FakeProvider` remains the deterministic development provider, while at least one real provider/model is required before authoritative utility/token/cost claims;
- Docling enters only after the first controlled B0–B4 HR pilot;
- a simplified Next.js UI is allowed to start now from synthetic fixtures, but remains non-blocking and must not define scientific metrics/contracts;
- the Python project will expose CLI, HTTP API and MCP as thin adapters over the same application/core boundary.

## Current engineering gate

### T09 / Issue #4 — controlled HR minicorpus and ground truth

**Immediate next research task.**

Before T07/B3 starts, version and freeze:

- the case schema;
- approximately 12–20 HR pilot cases;
- expected sensitive spans/categories;
- governance context + policy version;
- acceptable action(s) per information unit;
- `REQUIRED` / `NOT_REQUIRED` task-necessity labels;
- expected answer or objectively verifiable property;
- expected `BLOCK_REQUEST` behavior;
- pseudonym/reconstruction expectations when applicable.

Minimum HR task families:

1. authorized salary analysis;
2. team summary/description without salary necessity;
3. department aggregation without individual identity;
4. medical/prohibited-data case that must block.

**Exit gate:** schema + cases + annotations are versioned/frozen. Only then is T07/B3 released for implementation.

## Next research implementation

### T07 / Issue #6 — B3 — Task-aware

Status: **blocked only by T09 Phase A**.

B3 introduces deterministic task-awareness while retaining B2 pseudonymization, vault, reconstruction and provider behavior. Its generic action space must be independent of `domain`, `purpose`, `requester_role`, `provider_class` and contextual `policy_version`, so B2→B3 isolates task-awareness.

T01 line/advisor selection does not block B3.

### T08 / Issue #7 — B4 — Policy-governed

Status: **depends on B3 + shared T09 ground truth**.

B4 keeps the same task analyzer/reversible mechanism and adds explicit contextual policy constraints. Policy resolves the allowed action space first; task-awareness can only minimize within that space. B3→B4 must isolate the effect of explicit policy governance.

### T10 / Issue #8 — experiment runner and metrics

Status: not started.

Authoritative pilot/result dependencies:

- T09 frozen ground truth;
- T07/B3;
- T08/B4;
- T22 real provider before authoritative utility/token/cost claims.

Metrics include:

- policy violations;
- unnecessary/sensitive disclosure;
- detector precision/recall/F1;
- task utility/success;
- reconstruction accuracy;
- latency;
- CPU/memory;
- transmitted data/tokens;
- estimated external API cost.

Measurement rules:

- detector/scoring overhead around B0 is not B0 treatment latency;
- record timings by stage;
- separate disclosure-controlled payload volume from task/prompt scaffolding and optionally record total request volume separately;
- correctly blocked impossible-under-policy cases are reported separately from normal task-utility failures;
- pilot observations are used to freeze interpretation thresholds before the main experiment;
- corpus version, policy version, model id/snapshot, decoding config, prompt scaffolding and run configuration must be recorded.

### T12 / Issue #9 — Docling ingestion

Status: deferred until after the first B0–B4 HR pilot.

Direct text remains the canonical controlled path. Contracts are the first document-oriented expansion; Finance remains optional if schedule permits. Docling is infrastructure, not a claimed research contribution.

## New non-blocking integration/product tasks

### T20 / Issue #28 — CLI + HTTP API + MCP adapters

Expose the Python core through three thin adapters over one shared application/use-case boundary.

Rules:

- no duplicate policy/task/pseudonym/reconstruction/scoring logic in adapters;
- safe/default responses do not expose vault contents, secrets, raw sensitive audit data or private policy state;
- CLI is for local/dev/controlled execution;
- HTTP API is for UI and external integrations;
- MCP exposes tools/resources over the same application contract.

This does **not** block T09/T07/T08.

### T21 / Issue #29 — simplified Next.js UI

Start now as a parallel UI track using versioned synthetic fixtures/mock JSON.

The initial UI may display safe run/audit metadata, treatment, decisions, provider state, reconstruction summary and timing/volume fields. It must not define scientific metrics or treatment semantics independently of the Python core.

Later, replace fixtures with the T20 HTTP API. No research-core task depends on the UI.

### T22 / Issue #30 — real provider adapter

Implement at least one real provider behind the existing `Provider` protocol before authoritative experiment claims about utility/tokens/API cost.

Requirements include native transport/client timeout or cancellation, reproducibility metadata, frozen comparable configuration across B0–B4, and preservation of the existing fail-closed/no-leak boundary.

This does **not** block T09/T07/T08, but it is required before the authoritative real-provider phase of T10.

## Academic track

### T01 — PPGCA line/advisor reevaluation

T01 runs in parallel and is **not an engineering gate**.

Current provisional candidates:

- Daniel Fernando Pigatto;
- Michel Albonico;
- Luiz Celso Gomes Júnior.

T01 must be resolved before the final submission framing/line/advisor is frozen, but implementation may continue independently.

## Execution order

### Critical research path

1. **T09 / Issue #4 — freeze HR pilot corpus + ground truth.**
2. **T07 / Issue #6 — implement B3.**
3. **T08 / Issue #7 — implement B4.**
4. **T10 / Issue #8 — run the controlled B0–B4 pilot and stabilize metrics/output.**
5. Freeze utility/overhead interpretation thresholds from the pilot.
6. **T12 / Issue #9 — add Docling + Contracts as second-domain validation.**
7. **T22 / Issue #30 — ensure a real provider is available before authoritative real-provider utility/token/cost claims.**
8. Execute the main experiment.

### Parallel tracks

- **T01** — line/advisor selection for the academic submission;
- **T21 / Issue #29** — simplified Next.js UI from synthetic fixtures;
- **T20 / Issue #28** — CLI/API/MCP adapters when useful for integration; T20 becomes the backend integration point for T21 later.

Parallel tracks must not become reverse dependencies of the research core.

## Deferred / non-blocking engineering

Still deferred unless the experiment creates a concrete need:

- `SQLiteVault` or other persistent/shared vault backend;
- detector rule emitting `birth_date`;
- additional Hypothesis-based pseudonym property tests;
- second real provider for robustness;
- multi-turn disclosure-history study;
- full visual audit/comparison product UI beyond the simplified T21 surface.

## References

- Experimental design: `docs/experimental-design.md`
- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- T09 corpus/ground truth: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/4
- T07 B3: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/6
- T08 B4: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/7
- T10 runner: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/8
- T12 Docling: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/9
- T20 CLI/API/MCP: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/28
- T21 Next.js UI: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/29
- T22 real provider: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/30
- Milestone 1 PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/27
