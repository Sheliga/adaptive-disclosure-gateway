# Milestone 3 — current execution plan

Last updated: 2026-09-11 (America/Sao_Paulo)

This document records the current execution order and working schedule for Milestone 3 after T12 completed. It is an operational planning document; normative methodology remains in `docs/research/post-pilot-protocol-v1.md`.

## Current state

Completed gates:

- T23 / Issue #36 — post-pilot methodology freeze ✅
  - PR #53 merged into `develop` as `15696a131d6bc16c19e810fa811767684b15ed51`.
  - `post-pilot-v1` is the frozen methodological baseline.
- T12 / Issue #9 — Docling-backed normalized ingestion ✅
  - PR #55 merged into `develop` as `776e683a49818db35021bb62315dfc1ed7fb00ab`.
  - Exact feature head validated before merge: `3c93f3297515c99c6fccd4c5e705f1e77cfada78`.
  - Real Docling 2.126.0 validation passed for PDF, DOCX and XLSX.
  - Full Python suite at validation time: 690 passed, 3 skipped, 0 failed.
  - Ruff and all web gates were green.

Active gate:

- Issue #56 — Contracts domain extensions.

Next gates:

- T24 / Issue #37 — Contracts v1 corpus + frozen oracle.
- next B0–B4 batch after the domain support and corpus/oracle are frozen.

Parallel gate:

- T22 / Issue #30 — real provider adapter. It does not block Contracts corpus construction, but it does block authoritative real-provider utility/token/cost claims.

## Scientific order

The current order is:

```text
T23 ✅
  ↓
T12 ✅
  ↓
Issue #56 — Contracts domain extensions / freeze
  ↓
T24 — Contracts v1 + oracle freeze
  ↓
next B0–B4 batch
```

T22 runs in parallel.

Issue #56 makes explicit work that was already implicit in the earlier "Contracts support" planning window. It is not a new confirmatory-analysis phase and should not be treated as additional scope beyond preparing the second domain safely.

## Effect of the T12 delivery

T12 completed before its original 14–17 September planning window. This changes the schedule in three useful ways:

1. the parser/normalization boundary is no longer on the critical path;
2. Contracts work can start without risking later fixture/offset/schema rework from a moving ingestion representation;
3. the recovered time becomes schedule buffer for domain-semantic uncertainty in #56 and T24.

The main risk has therefore moved from document ingestion to Contracts semantics: categories, relations, policy vocabulary, generalization behavior and the freeze boundary between development fixtures and held-out/confirmatory evidence.

## Revised working schedule

These are planning windows, not protocol constraints.

| Stage | Working window | Status / rationale |
| --- | --- | --- |
| T23 methodology freeze | 10–11 Sep | ✅ complete |
| T12 normalized ingestion | completed 11 Sep local time | ✅ complete ahead of the original 14–17 Sep window |
| Issue #56 Contracts domain extensions | 12–16 Sep | active; use synthetic/development-only fixtures and freeze support before T24 |
| T24 Contracts v1 + oracle | 17–21 Sep | start only after #56 is frozen |
| T22 real provider | parallel; target readiness by 22–24 Sep | required before authoritative provider utility/token/cost claims |
| integration + frozen config + next B0–B4 readiness | 22–29 Sep | combines corpus/provider readiness and final no-tuning checks |
| M3 aggressive target | 25 Sep | still possible, now more credible, but depends on #56/T24 staying narrow |
| M3 safe target | 30 Sep | remains the planning commitment and now has more buffer |

The project should not consume the entire T12 time gain by pulling every downstream date forward. The safer use of the gain is to absorb unforeseen Contracts-domain gaps while keeping 30 September protected.

## Schedule guardrails

- If #56 freezes by 16 September, the project is ahead of the original critical path.
- If #56 slips to 17–18 September, the safe 30 September target remains viable but most of the recovered T12 buffer is consumed.
- If #56 is still changing treatment/policy semantics after 19 September, T24 should not be rushed into a held-out/confirmatory label; preserve methodology and accept schedule movement instead.
- T24 must not become the place where categories/policies/generalization are tuned after seeing held-out treatment results.
- T22 can proceed in parallel and should be ready before the authoritative real-provider batch; it does not justify blocking #56 or T24 corpus construction.

## Issue #56 boundary

Issue #56 owns development-time Contracts support:

- parties and roles;
- obligations;
- deadlines;
- penalties;
- monetary amounts;
- relationship-preserving task requirements;
- any required detector category, policy vocabulary or generalization support.

Examples used here are development fixtures only.

The task is complete when the minimum reusable Contracts support is versioned/frozen and T24 can build its corpus/oracle without changing treatment semantics in response to held-out results.

## T24 boundary

T24 owns evaluation evidence, not domain-feature development:

- versioned Contracts v1 corpus;
- oracle and task-necessity labels;
- expected actions / verifiable utility properties;
- classification as development or held-out/confirmatory before comparative results are inspected;
- oracle isolation and no-leak checks;
- B0–B4 execution only after the domain support needed by those cases is frozen.

## Milestone 3 closure

M3 remains open until all of the following are true:

1. T23 protocol freeze is complete ✅;
2. T12 structured ingestion is complete ✅;
3. Contracts-specific domain support is frozen (#56);
4. a real provider is available with reproducibility/safe-failure metadata (T22);
5. Contracts v1 + oracle are frozen with classification decided before result inspection (T24);
6. the next B0–B4 batch can launch without treatment/policy/metric tuning driven by its outcomes.

## Master/develop boundary

Current M3 work remains on `develop`. `master` is intentionally not advanced by the T12 merge. Promotion to `master` remains a separate explicit integration decision.