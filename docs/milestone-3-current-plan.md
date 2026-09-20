# Milestone 3 — current execution plan

Last updated: 2026-09-12 (America/Sao_Paulo)

Normative methodology remains in `docs/research/post-pilot-protocol-v1.md`. This document records execution order only.

## Operational status: PAUSED while the advisor demo is priority 1

Milestone 3 remains scientifically open and its closure criteria are unchanged, but it is **not the current implementation path**.

Current project sequence:

```text
T20 demo integration ✅
  ↓
T21 / Issue #29 — contract-focused guided Next.js UI
  ↓
T25 / Issue #42 — containerize/deploy and publish advisor URL
  ↓
resume M3 at gate 6
```

T20's demo-critical integration is complete in PR #64, merged into `develop` as `c261297da132c6825d8a3f6e0a81d8663aae5df7`. The backend now supports structured contract upload through T12, explicit Contracts governance, preview confirmation bound to the exact disclosure decision, real-provider configuration through T22, server-side upload limits, and safe preview → confirmed execute semantics.

The next active gate is therefore **T21 / Issue #29**, followed by **T25 / Issue #42**. M3 resumes only after a hosted advisor-facing demo URL exists.

## M3 state preserved

Completed closure gates:

1. T23 / Issue #36 — post-pilot methodology freeze ✅
2. T12 / Issue #9 — normalized structured ingestion ✅
3. Issue #56 — Contracts domain support freeze ✅
4. T24 / Issue #37 — Contracts v1 pilot corpus/oracle freeze ✅
5. T22 / Issue #30 — real Anthropic provider readiness ✅

Current state: **5/8 closure gates complete**.

Deferred until after the demo URL exists:

6. explicit methodological resolution of the T24 date/generalization utility-scoring finding;
7. a newly authored confirmatory-eligible Contracts corpus, frozen only after the applicable methodology/scorer/provider configuration is frozen;
8. next B0–B4 launch readiness with provider/config/treatment/scoring provenance frozen in advance.

## Current scientific findings carried forward

T24 produced findings that remain intentionally unresolved during demo work:

1. `score_utility` treats GENERALIZE as a numeric-band operation; month-year dates can therefore be scored optimistically. This requires a later protocol/scorer version before confirmatory evidence.
2. `contracts-v1` preserves deadlines unconditionally, so B4 can disclose a deadline even where the task marks it `NOT_REQUIRED`.
3. B2 pseudonymizes CNPJ/CPF where the Contracts policy/oracle require REMOVE; this remains a legitimate treatment difference.
4. Detector performance is near-perfect by construction on the labeled-line corpus and must not be generalized to natural contracts.
5. Contracts v1 is small (`N=12`) and uses one Contracts policy version; requester-role/provider-class effects are not identified by this corpus.

These remain pilot/development findings and do not block the advisor demo.

## Scientific guardrails remain unchanged

- `docs/research/post-pilot-protocol-v1.md` remains immutable.
- `corpus/contracts/v1` remains permanently `pilot_development` because its treatment outcomes were inspected.
- Do not relabel `contracts/v1` as confirmatory.
- Do not edit `post-pilot-v1` in place to fix the date-generalization utility issue; create a new protocol/scorer version.
- Do not author or inspect a future confirmatory Contracts corpus until the applicable protocol, scorer semantics, provider/model/config and treatment implementations are frozen.
- Demo work must not tune B0–B4, policies, scorer, oracle or scientific outcomes for presentation purposes.

## Why the pause does not block the demo

The advisor demo consumes capabilities already completed by the research track:

- T12 structured ingestion;
- Contracts domain and `contracts-v1` governance;
- T22 real-provider support;
- the shared B0–B4 implementation and application boundary.

The unresolved M3 items concern defensible confirmatory scientific claims, not whether the mechanism can be demonstrated safely to prospective advisors.

## Resume point

After Issue #41 is deployable and a prospective advisor can use the hosted URL, resume M3 at gate 6: versioned date-aware/generalization-aware utility semantics.

Do not skip directly to a new confirmatory corpus or authoritative B0–B4 run.

## Branch boundary

Feature/demo work targets `develop`. Promotion `develop → master` remains a separate integration/CI boundary and is not performed by feature/review PRs.
