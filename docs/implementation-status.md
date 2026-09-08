# Implementation status

Last updated: 2026-09-08 — post-Milestone 2 synchronization + advisor-demo planning.

This file tracks the current engineering/research state and execution order. Architectural decisions belong in ADRs; experimental definitions belong in `docs/experimental-design.md`; factual pilot results belong in `docs/milestone-2-pilot.md`; the parallel advisor-facing application plan belongs in `docs/advisor-demo.md`; historical PR/Issue descriptions remain in GitHub.

## Current phase

**Milestone 1 and Milestone 2 are complete on `master`.**

The project has moved from building the research treatments to **post-pilot methodological freeze and confirmatory-readiness**.

The canonical sequence is implemented and executable:

**B0 — Direct → B1 — Static Sanitization → B2 — Reversible Pseudonymization → B3 — Task-aware → B4 — Policy-governed.**

Milestone 2 closed via PR #35 / merge `027a2baead4a3cee35db23cb8d4b79005a3a75d0` after the frozen HR corpus, B3, B4 and the experiment runner were completed.

In parallel, the same Python implementation is now explicitly planned as the **reference application core for an advisor-facing interactive demo**. This application track does not change Milestone 3 gates.

## Milestone 2 — completed

Required scope:

- T09 / Issue #4 — frozen HR minicorpus + oracle ✅
- T07 / Issue #6 — B3 Task-aware ✅
- T08 / Issue #7 — B4 Policy-governed + contextual HR matrix ✅
- T10 / Issue #8 — reproducible runner + first B0–B4 HR pilot ✅

Milestone tracker: Issue #32.

### Frozen implementation / evaluation state

- `corpus/hr/v1/`: 13 controlled HR cases; frozen/versioned.
- B3 frozen implementation commit: `31bce08b7ea6a5c905f7a20bbb4bb99a05682bab`.
- B4 frozen implementation commit: `5abea8514fa10ac64b9bc3714bbfd3f18682f713`.
- B4 retains B3's task-aware baseline and adds contextual policy constraints.
- HR contextual matrix: `hr-v2` / `hr-v3`; original corpus cases remain on frozen `hr-v1`.
- experiment schema: `t10-experiment-runner-v2`.
- artifact bundle schema: `t10-pilot-artifact-bundle-v2`.
- final M2 pilot artifact: `artifacts/experiments/hr/v1/13198a3b95bd49b88a62f591f3da1224/`.

### Runner capabilities delivered

The experiment runner now provides, without sending ground truth into treatments:

- B0–B4 execution over the same case set;
- conformance/policy scoring;
- exposure representation levels;
- binary unnecessary-disclosure scoring;
- detector TP/FP/FN + precision/recall/F1 from the detector spans actually used by execution;
- utility information-sufficiency proxy for FakeProvider runs;
- reconstruction scoring;
- policy-restricted / impossible-under-policy / hard-block outcomes;
- stage-aware latency;
- provider/payload/request byte volume;
- process CPU time and peak Python traced memory;
- B3/B4 implementation provenance;
- B4 policy version/matrix-cell provenance;
- shared `experiment_run_id` plus per-execution ids;
- cross-process deterministic comparison without weakening audit HMAC security;
- safe machine-readable summaries and pairwise comparisons.

The final T10 branch reported 462 passing tests and clean Ruff checks before merge.

## M2 pilot classification

The HR result is **pilot/development evidence**, not held-out confirmatory evidence.

Reasons:

- `corpus/hr/v1` was used during B3/B4 development;
- FakeProvider does not produce real LLM task output, token usage or external API cost;
- the pilot is used to identify methodological decisions that must be frozen before authoritative analysis.

Do not describe M2 as proof that B4 outperforms other treatments.

## Post-pilot findings that now drive planning

Three methodological findings must be carried forward without retroactively changing M2:

1. **Binary unnecessary disclosure penalizes pseudonymization.** The current primary binary rate counts `PSEUDONYMIZE` as transmitted. That is valid as a binary transmission fact, but can make B2 appear worse than B1 despite a lower representation exposure. Ordered exposure levels are already retained and the primary/secondary metric interpretation must be frozen before authoritative analysis.
2. **The main HR B3→B4 pairwise uses `hr-v1`.** Contextual governance effects from `purpose`, `requester_role`, `provider_class` and `policy_version` are identified in targeted `hr-v2/hr-v3` matrix comparisons rather than the main frozen-corpus pairwise run.
3. **FakeProvider is not evidence about a real provider.** It remains appropriate for deterministic TDD/pilot reproducibility but cannot support authoritative utility/token/cost or genuine provider-class behavior claims.

The known B3 case `hr_salary_analysis_003/salary` remains intentionally visible: B3 selects `GENERALIZE` while the oracle accepts only `PRESERVE`. It is not tuned away.

## Milestone 3 — active

Tracker: Issue #38 — **Post-pilot protocol freeze and confirmatory-readiness**.

### Required research path

#### T23 / Issue #36 — freeze post-pilot methodology

Status: **next methodological gate**.

Freeze before confirmatory analysis:

- primary/secondary exposure and unnecessary-disclosure metrics;
- interpretation of `PSEUDONYMIZE` relative to representation exposure;
- utility-loss and performance/overhead interpretation thresholds;
- primary B3→B4 contextual comparison procedure;
- `hr-v1` pilot vs `hr-v2/hr-v3` reporting relationship;
- provider/model/configuration requirements;
- development vs held-out/confirmatory labeling;
- statistical/descriptive analysis plan.

T23 must not tune B3/B4, frozen HR policies, the frozen corpus or M2 artifacts to improve pilot numbers.

#### T22 / Issue #30 — real provider

Status: **promoted after M2; may proceed in parallel with T23**.

Implement at least one real provider behind the existing narrow `Provider` protocol. Required before authoritative claims about:

- actual LLM task utility;
- provider tokens;
- external API cost;
- genuine provider/provider-class behavior.

Provider/model/scaffolding/decoding configuration must be frozen under the T23 protocol before confirmatory comparison.

T22 is also consumed by the advisor-facing demo when available. FakeProvider remains sufficient to build/test the demo shell, but a real-provider mode is preferred before sharing the demo broadly with prospective advisors.

#### T12 / Issue #9 — Docling ingestion

Status: **gate released after M2; may proceed in parallel**.

Docling is ingestion infrastructure only. Keep a normalized internal document representation independent from Docling APIs and keep parser behavior constant across B0–B4.

Direct normalized text remains the canonical parser-independent control path.

#### T24 / Issue #37 — Contracts v1 validation corpus

Status: **new second-domain evaluation task; depends methodologically on T23**.

T24 is deliberately separate from T12:

- T12 = document ingestion/normalization infrastructure;
- T24 = frozen Contracts corpus/oracle and evaluation evidence.

If Contracts requires new categories/policies/generalization strategies, those extensions must be frozen before a held-out corpus is inspected at treatment-result level, or the resulting run must remain development evidence.

### Milestone 3 closure criterion

M3 closes when:

1. post-pilot metrics/thresholds/comparison/provider rules are frozen;
2. a real provider is available behind the shared boundary;
3. structured Contracts ingestion is available without becoming a treatment variable;
4. Contracts v1 corpus/oracle is frozen with its run classification decided before result inspection;
5. the next B0–B4 batch can start without post-result treatment/policy/metric tuning.

## Parallel academic track

### T01 — PPGCA line/advisor reevaluation

T01 remains independent from engineering gates.

The completed M2 materially changes the academic discussion: the project can now be presented as an executable research prototype with all B0–B4 treatments, a reproducible pilot, machine-readable metrics and explicit methodological limitations—not only as an architecture proposal.

The advisor-facing demo track is intended to make that prototype directly testable by prospective advisors through a hosted URL, but demo completion is not a prerequisite for T01 conversations.

Current provisional candidates remain:

- Daniel Fernando Pigatto;
- Michel Albonico;
- Luiz Celso Gomes Júnior.

T01 blocks only the final academic framing/line/advisor/submission, not M3 engineering.

## Parallel advisor-facing demo/application track

Tracker: **Issue #41 — Advisor-facing interactive research application**.

Purpose: turn the current Python research implementation into the application used to demonstrate the concept to prospective advisors. The demo exposes the actual implemented core rather than recreating anonymization/policy logic in Next.js.

Target path:

```text
browser -> Next.js -> HTTP API -> Python application/core -> B0–B4 -> provider -> local reconstruction
```

### First-demo rules

- no agentic anonymization/orchestration;
- detector/B3 analyzer/B4 policy logic remain the implemented deterministic mechanisms;
- prepared HR examples are synthetic/controlled;
- free-form input, if enabled, must preserve safe logging/error semantics;
- provider credentials remain server-side;
- UI never becomes a source of treatment/policy/scoring semantics.

### T20 / Issue #28 — application boundary + CLI/HTTP/MCP

Status: **backlog globally / first implementation step inside the demo track / non-blocking for M3**.

For the advisor demo, HTTP API is the first required adapter. CLI and MCP should share the same application service but do not need to block the first hosted URL.

The HTTP surface should execute controlled text + task + GovernanceContext + treatment/provider through the real Python core and return safe transformation/policy/provider/reconstruction/result metadata.

### T21 / Issue #29 — Next.js advisor-facing UI

Status: **backlog globally / follows T20 inside the demo track / non-blocking for M3**.

The UI should let a reviewer select a prepared HR example or controlled text, choose/compare B0–B4, see what crosses the trust boundary, inspect actions/policy reasons, provider response, local reconstructed response and selected metrics.

Phase 1 can use safe T10 artifact/schema-driven fixtures. Phase 2 uses T20's real HTTP API.

### T25 / Issue #42 — containerized demo/deploy infrastructure

Status: **backlog / follows functional API+UI integration / non-blocking for M3**.

The current root `compose.yaml` is a development/test harness rather than deploy infrastructure: it mounts the repository and runs tests. T25 owns a distinct deployment-oriented topology.

Required demo infrastructure includes:

- Python API image on the supported Python 3.13 runtime;
- Next.js image;
- demo/deploy compose/profile distinct from test compose;
- service networking;
- health/readiness checks;
- explicit CORS/API-origin handling;
- server-side-only provider secrets;
- one-command local startup;
- documented simple hosted container deployment suitable for sharing a URL;
- core/application version provenance.

The target is a small research-demo deployment, not desktop distribution, installers, multi-tenant SaaS or production-scale orchestration.

### Demo completion criterion

The first demo track is complete when a prospective advisor can receive a URL and execute at least the controlled HR B0–B4 concept through the actual Python core without local setup.

T22/real provider improves this substantially and should be enabled when available, but FakeProvider remains valid for deterministic demonstration of the gateway mechanics.

## Deferred unless evidence creates a need

- persistent/shared `SQLiteVault` or equivalent;
- second real provider for robustness;
- Accounting/Finance third domain;
- multi-turn disclosure-history study;
- additional detector categories not required by the next frozen domain;
- full product-grade visual audit platform;
- agentic anonymization as an unversioned replacement for the deterministic B0–B4 path.

## Execution order

### Critical research path

1. M2 / HR pilot ✅
2. **T23 / Issue #36 — freeze post-pilot protocol**
3. In parallel: **T22 real provider** + **T12 Docling/normalization**
4. **T24 / Issue #37 — Contracts v1 corpus/oracle**
5. Verify M3 closure / confirmatory-readiness
6. Launch next frozen B0–B4 validation batch
7. Only then analyze authoritative comparative results under the pre-frozen protocol

### Parallel academic path

- T01 advisor/line framing.

### Parallel demo/application path

1. **T20 HTTP/application boundary**;
2. **T21 Next.js interactive demo**;
3. **T25 containerized deploy**;
4. consume **T22 real provider** when available.

This ordering is internal to the demo track and does not reorder the scientific critical path.

## References

- Experimental design: `docs/experimental-design.md`
- M2 pilot record: `docs/milestone-2-pilot.md`
- Advisor demo plan: `docs/advisor-demo.md`
- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- M2 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/32
- T23 methodology freeze: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/36
- T22 real provider: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/30
- T12 Docling: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/9
- T24 Contracts corpus: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/37
- M3 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/38
- Demo tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/41
- T20 CLI/API/MCP: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/28
- T21 Next.js UI: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/29
- T25 demo containers/deploy: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/42