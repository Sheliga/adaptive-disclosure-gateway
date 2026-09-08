# Implementation status

Last updated: 2026-09-08 — post-Milestone 2 synchronization.

This file tracks the current engineering/research state and execution order. Architectural decisions belong in ADRs; experimental definitions belong in `docs/experimental-design.md`; factual pilot results belong in `docs/milestone-2-pilot.md`; historical PR/Issue descriptions remain in GitHub.

## Current phase

**Milestone 1 and Milestone 2 are complete on `master`.**

The project has moved from building the research treatments to **post-pilot methodological freeze and confirmatory-readiness**.

The canonical sequence is implemented and executable:

**B0 — Direct → B1 — Static Sanitization → B2 — Reversible Pseudonymization → B3 — Task-aware → B4 — Policy-governed.**

Milestone 2 closed via PR #35 / merge `027a2baead4a3cee35db23cb8d4b79005a3a75d0` after the frozen HR corpus, B3, B4 and the experiment runner were completed.

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

Current provisional candidates remain:

- Daniel Fernando Pigatto;
- Michel Albonico;
- Luiz Celso Gomes Júnior.

T01 blocks only the final academic framing/line/advisor/submission, not M3 engineering.

## Parallel product/integration tracks

### T20 / Issue #28 — CLI + HTTP API + MCP

Status: **backlog / non-blocking for M3**.

M2 now provides stable safe result concepts (`t10-experiment-runner-v2`) that adapters may expose. All adapters must remain thin and must not duplicate treatment/policy/scoring semantics.

### T21 / Issue #29 — Next.js UI

Status: **backlog / non-blocking for M3**.

Fixtures should now be derived from the safe M2 artifact schema rather than inventing frontend-only experiment semantics. Phase 2 still integrates through T20 HTTP API.

## Deferred unless evidence creates a need

- persistent/shared `SQLiteVault` or equivalent;
- second real provider for robustness;
- Accounting/Finance third domain;
- multi-turn disclosure-history study;
- additional detector categories not required by the next frozen domain;
- full product-grade visual audit platform.

## Execution order

### Critical research path

1. M2 / HR pilot ✅
2. **T23 / Issue #36 — freeze post-pilot protocol**
3. In parallel: **T22 real provider** + **T12 Docling/normalization**
4. **T24 / Issue #37 — Contracts v1 corpus/oracle**
5. Verify M3 closure / confirmatory-readiness
6. Launch next frozen B0–B4 validation batch
7. Only then analyze authoritative comparative results under the pre-frozen protocol

### Parallel

- T01 academic framing/advisor;
- T20 adapters when integration becomes useful;
- T21 UI when presentation/inspection becomes useful.

## References

- Experimental design: `docs/experimental-design.md`
- M2 pilot record: `docs/milestone-2-pilot.md`
- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- M2 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/32
- T23 methodology freeze: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/36
- T22 real provider: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/30
- T12 Docling: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/9
- T24 Contracts corpus: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/37
- M3 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/38
- T20 CLI/API/MCP: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/28
- T21 Next.js UI: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/29
