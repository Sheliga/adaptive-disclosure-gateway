# Implementation status

Last updated: 2026-09-07 — post-Milestone 1 planning synchronization after the research-decision review, updated for T09 Phase A completion (PR #31 review round 2). **Milestone 1 remains complete on `master`.**

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

## T09 / Issue #4 — controlled HR minicorpus and ground truth

**Phase A is complete. `corpus/hr/v1/` is frozen per `README.md`'s freeze
rule: any future change to the schema, an existing case's text/offsets/
labels, or the set of cases creates `corpus/hr/v2/` rather than editing
`v1` in place.**

`corpus/hr/v1/` (schema `SCHEMA.md`, freeze/versioning rule `README.md`, 13
case files under `cases/`) and `src/adaptive_disclosure_gateway/corpus/`
(`CorpusCaseInput`, `CaseOracle`, `ExpectedSpan`, `ReconstructionExpectation`,
`TaskNecessity`, `TaskFamily`, the fail-closed YAML loader) cover:

- the case schema, structurally separating `input` (what a treatment may
  see) from `oracle` (scoring only — `CorpusCaseInput` is the only type
  with a method that builds a `DisclosureRequest`; `CaseOracle` has no path
  into the pipeline, pinned by an AST-based isolation test alongside
  `tests/test_treatment_isolation.py`'s treatment-isolation checks);
- 13 HR pilot cases (3 per required task family, plus a fourth
  `team_summary_without_salary` case, `hr_team_summary_004`, where
  `employee_name` is genuinely task-required rather than suppressed by
  default -- pinned by `tests/test_corpus_necessity_discrimination.py` so
  no non-exempt category is always `NOT_REQUIRED` across the corpus — near
  the approved range's lower bound);
- expected sensitive spans/categories, each with offsets validated against
  their own case's text by reusing `transformations/span_validation.py`;
- governance context + `policy_version` (all cases use `hr-v1`);
- acceptable action set per information unit (`expected_actions`);
- `REQUIRED` / `NOT_REQUIRED` task-necessity labels as the sole primary
  oracle, with `HELPFUL` representable only via a separate, auxiliary
  `ExpectedSpan.helpful` flag never mixed into the primary label;
- expected answer / objectively verifiable property, required exactly when
  a case does not expect `BLOCK_REQUEST` and forbidden when it does, and
  checkable purely from `input.text` — never from a compensation band,
  department policy or wage floor known only to a scoring model or to
  `transformations/generalization.py`'s bucket configuration
  (`tests/test_corpus_answer_grounded_in_input.py`); a case whose task
  requires comparing against such a reference states that reference
  explicitly inside `input.text`;
- `oracle.answer_depends_on_categories`, naming every category
  `expected_answer` actually depends on: a span can only be annotated
  `task_necessity: required` when the case's own answer depends on that
  category, checked exactly by
  `tests/test_corpus_task_necessity_coherence.py`;
- expected `BLOCK_REQUEST` behavior, including a case whose only
  task-required information unit is the one hr-v1 unconditionally forbids
  (`hr_medical_block_002`) — a worked example of the "correctly blocked,
  impossible under policy" outcome docs/experimental-design.md's metrics
  distinguish from an ordinary utility failure;
- pseudonym/reconstruction expectations where applicable;
- a corpus case file's base name is validated to equal its own
  `input.sample_id` (`CorpusLoadError` on a mismatch).

Minimum HR task families, all present:

1. authorized salary analysis (`authorized_salary_analysis`);
2. team summary/description without salary necessity
   (`team_summary_without_salary`);
3. department aggregation without individual identity
   (`department_aggregation_without_identity`);
4. medical/prohibited-data case that must block
   (`medical_or_prohibited_block`).

**Gate:** the B3 gate is released — schema, cases and annotations are
versioned and frozen, satisfying T09 Phase A's exit criterion. T07 / Issue
#6 (B3 — Task-aware) is the next critical-path step.

## Next research implementation

### T07 / Issue #6 — B3 — Task-aware

Status: **ready to start — the T09 gate is released.**

B3 introduces deterministic task-awareness while retaining B2 pseudonymization, vault, reconstruction and provider behavior. Its generic action space must be independent of `domain`, `purpose`, `requester_role`, `provider_class` and contextual `policy_version`, so B2→B3 isolates task-awareness.

T01 line/advisor selection does not block B3.

### T08 / Issue #7 — B4 — Policy-governed

Status: **depends on B3 (T07) + the frozen T09 ground truth, which is now available**.

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

1. **T09 / Issue #4 — freeze HR pilot corpus + ground truth.** Phase A is
   complete: `corpus/hr/v1/` is finalized and frozen.
2. **T07 / Issue #6 — implement B3.** Next critical-path step.
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
