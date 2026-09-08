# Milestone 2 pilot record — Controlled HR B0–B4

Date: 2026-09-08

Status: **completed development pilot**.

Classification: **`pilot_development` — not held-out confirmatory evidence**.

This document records the factual output and methodological limitations of Milestone 2. It is intentionally descriptive. It does not claim that B4 is superior to the other treatments and does not redefine metrics after seeing the pilot results.

## Frozen components

- HR corpus: `corpus/hr/v1/` — 13 controlled cases.
- B3 implementation: `31bce08b7ea6a5c905f7a20bbb4bb99a05682bab`.
- B4 implementation: `5abea8514fa10ac64b9bc3714bbfd3f18682f713`.
- T10 / M2 merge: `027a2baead4a3cee35db23cb8d4b79005a3a75d0`.
- experiment schema: `t10-experiment-runner-v2`.
- artifact bundle schema: `t10-pilot-artifact-bundle-v2`.
- experiment run id: `13198a3b95bd49b88a62f591f3da1224`.
- artifact path: `artifacts/experiments/hr/v1/13198a3b95bd49b88a62f591f3da1224/`.

The frozen `corpus/hr/v1`, `hr-v1`, `hr-v2`, `hr-v3`, B3 analyzer/action spaces and B4 policy-governed semantics were not changed to improve pilot results.

## Executed treatments

The same 13 HR cases were executed under:

1. B0 — Direct
2. B1 — Static Sanitization
3. B2 — Reversible Pseudonymization
4. B3 — Task-aware
5. B4 — Policy-governed

FakeProvider was used for deterministic development/integration measurement.

## Runner outputs

The final M2 runner produces machine-readable per-case and aggregate data for:

- conformance / acceptable action matching;
- ordered exposure representation;
- binary unnecessary disclosure;
- detector TP/FP/FN, precision, recall and F1;
- utility information-sufficiency proxy;
- reconstruction;
- policy-restricted / impossible-under-policy / hard-block outcomes;
- treatment, provider and total-pipeline timing;
- process CPU time;
- peak Python traced allocation;
- disclosure-controlled payload bytes;
- total provider-request bytes;
- treatment/policy/matrix/provider provenance;
- experiment and case-execution identities.

Ground truth is used after execution for scoring and is not treatment/provider input.

## Factual pilot summary

| Treatment | Blocked | Conformant rate | Binary unnecessary disclosure | Utility proxy answerable | Reconstruction correct | Mean payload bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 0/13 | 22.5% | 100% | 100% (10/10) | n/a | 153.2 |
| B1 | 3/13 | 95.8% | 11.4% | 30% (3/10) | n/a | 116.6 |
| B2 | 3/13 | 77.5% | 72.7% | 40% (4/10) | 10/10 | 251.0 |
| B3 | 3/13 | 98.6% | 0% | 40% (4/10) | 1/1 scored | 115.9 |
| B4 (`hr-v1` main run) | 3/13 | 97.2% | 31.8% | 40% (4/10) | 10/10 | 185.5 |

These values are pilot observations only.

## Detector result

Against the frozen HR oracle:

- true positives: 71
- false positives: 0
- false negatives: 0
- micro precision: 1.0
- micro recall: 1.0
- micro F1: 1.0

The detector is upstream of the treatment and therefore the same detection result is consumed by B0–B4 evaluation for the same case input.

## B3 → B4 under the frozen HR corpus

The main HR corpus uses `policy_version: hr-v1`.

In the main B3→B4 summary:

- policy-restricted cases: 0
- impossible-under-policy cases: 0
- hard medical blocks: 3 on both sides
- B4 is more exposing than B3 in 9/13 cases
- 1 case has the same comparable exposure profile
- 3 blocked cases are incomparable on the ordinary exposure ladder

This result is specific to `hr-v1`. In `hr-v1`, `employee_name` and `department` include hard policy actions that can override B3's task-aware minimization.

The contextual `hr-v2/hr-v3` matrix is exercised separately through targeted comparisons that vary one contextual dimension at a time. Those comparisons demonstrate identifiable policy effects but are not the same thing as the main `hr-v1` pairwise summary.

## Known B3 divergence retained

`hr_salary_analysis_003/salary` remains a deliberate visible divergence:

- B3 actual action: `GENERALIZE`
- oracle acceptable action: `PRESERVE` only
- conformance: nonconformant
- utility proxy: indeterminate because the generalized band crosses the case's stated reference threshold

The case is not special-cased and the analyzer is not tuned to the corpus oracle after the fact.

## Methodological finding 1 — binary unnecessary disclosure

The binary unnecessary-disclosure metric asks whether a `NOT_REQUIRED` sensitive unit was transmitted in any representation.

Under that definition, `PSEUDONYMIZE` counts as transmitted. This is factually consistent with the metric but makes B2 score worse than B1 when B1 removes a unit and B2 transmits an opaque pseudonym.

The runner also records ordered representation exposure:

`REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE`

Milestone 2 does not retroactively change the metric. T23 / Issue #36 must freeze whether binary unnecessary disclosure remains primary, becomes secondary, or is paired with a level-sensitive primary metric before confirmatory results are inspected.

## Methodological finding 2 — governance matrix vs main pairwise

The frozen HR corpus uses `hr-v1`, while the explicit contextual governance matrix is versioned as `hr-v2/hr-v3`.

Therefore:

- the main B3→B4 pairwise describes B4 behavior under `hr-v1`;
- targeted contextual comparisons describe the isolated policy effects of purpose, requester role, provider class and policy version under `hr-v2/hr-v3`.

T23 must freeze which comparison is primary for later governance claims and how the `hr-v1` pilot is reported relative to contextual-matrix evidence.

## Methodological finding 3 — FakeProvider boundary

FakeProvider was sufficient for:

- deterministic end-to-end execution;
- scoring-boundary validation;
- exposure/conformance measurement;
- timing/resource/volume instrumentation;
- provider-contract and no-leak integration.

It is not sufficient for authoritative claims about:

- real LLM answer correctness;
- provider token usage;
- external API cost;
- genuine provider/provider-class behavior.

T22 / Issue #30 adds a real provider. T23 freezes the provider/model/configuration used for confirmatory analysis.

## Performance/resource scope

M2 records:

- stage-aware treatment/provider/total timing;
- process CPU-time delta;
- peak Python-traced allocation;
- payload and total-request byte volume.

CPU/memory numbers are lightweight pilot proxies, not OS-level profiling/RSS claims. No post-pilot threshold is inferred from the numbers in this document.

## Reproducibility and safety

The final artifact bundle records:

- shared `experiment_run_id`;
- distinct case-execution ids;
- B3/B4 implementation versions;
- B4 underlying B3 baseline;
- policy versions and contextual matrix version/specs;
- provider/model/snapshot/decoding configuration;
- treatment chain and corpus version.

Cross-process deterministic comparison removes intentionally process-volatile audit HMAC values from the comparison key while leaving the secure HMAC behavior of the actual audit record unchanged.

Safe/default artifacts do not persist raw sensitive span values, requester identifiers or vault mappings.

## What M2 establishes

Milestone 2 establishes that the project can execute B0–B4 reproducibly over one frozen controlled domain and generate comparable machine-readable outcomes while preserving the ground-truth and no-leak boundaries.

## What M2 does not establish

Milestone 2 does not establish:

- independent generalization beyond the development HR corpus;
- superiority of B4;
- real-provider utility/token/cost performance;
- a final primary exposure metric;
- final utility/overhead acceptance thresholds;
- confirmatory statistical significance.

Those are explicitly moved to Milestone 3 readiness work and later frozen validation.

## Follow-up

- T23 / Issue #36 — freeze post-pilot methodology and confirmatory protocol.
- T22 / Issue #30 — real provider.
- T12 / Issue #9 — normalized Docling ingestion infrastructure.
- T24 / Issue #37 — Contracts v1 second-domain corpus/oracle.
- Milestone 3 / Issue #38 — confirmatory-readiness tracker.
