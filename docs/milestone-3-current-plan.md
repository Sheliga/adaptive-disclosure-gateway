# Milestone 3 — current execution plan

Last updated: 2026-09-12 (America/Sao_Paulo)

This document records the current execution order and working schedule for Milestone 3. Normative methodology remains in `docs/research/post-pilot-protocol-v1.md`.

## Current state

Completed gates:

- T23 / Issue #36 — post-pilot methodology freeze ✅
  - PR #53 merged into `develop`.
  - `post-pilot-v1` remains the frozen methodological baseline.
- T12 / Issue #9 — Docling-backed normalized ingestion ✅
  - PR #55 merged into `develop` as `776e683a49818db35021bb62315dfc1ed7fb00ab`.
- Issue #56 — Contracts domain extensions ✅
  - PR #59 merged into `develop` as `5a67c30daab68d06bbd16d1cf06433de97245910`.
  - Contracts categories, detector behavior, policy, generalization strategies and relation semantics are frozen.
- T24 / Issue #37 — Contracts v1 corpus + frozen oracle ✅
  - PR #60 merged into `develop` as `cfa9969f31c6792a2e7456c3ae42564d711a1cc9`.
  - `corpus/contracts/v1` contains 12 synthetic cases across six task families.
  - Run classification is permanently `pilot_development` because the corpus was executed and inspected under B0–B4.
  - The corpus remains useful for development, regression, documentation and pilot evidence, but cannot later become `held_out_confirmatory`.

Active gate:

- T22 / Issue #30 — real provider adapter — **implemented; in validation in an open PR to
  `develop`**. Anthropic Messages API adapter behind the unchanged `Provider` boundary, opt-in
  via `ADG_PROVIDER=anthropic`, `FakeProvider` still the default everywhere. See
  [`docs/provider-configuration.md`](provider-configuration.md) and the T22 section of
  [`docs/implementation-status.md`](implementation-status.md). Two findings for the freeze
  step: sampling parameters no longer exist on current models, so bit-exact decoding
  determinism is not configurable and is recorded as such; and no cost/pricing accounting is
  provided, so a real batch reports token usage and *cost unavailable*.

Methodological follow-up before a real held-out confirmatory Contracts round:

- Finding from T24: the frozen `score_utility` GENERALIZE decidability rule is numeric-band-specific and misreads month-coarsened dates as numeric bands.
- Do not alter `post-pilot-v1` in place.
- A future protocol revision (for example `post-pilot-v2`) should define utility decidability by generalization type, including date-aware handling.
- After that revision is frozen, a newly authored independent Contracts corpus is required for `held_out_confirmatory`; `contracts/v1` is permanently ineligible.

## Scientific order

Current sequence:

```text
T23 ✅
  ↓
T12 ✅
  ↓
Issue #56 Contracts domain freeze ✅
  ↓
T24 Contracts v1 pilot corpus/oracle ✅
  ↓
T22 real provider + methodological follow-up
  ↓
new confirmatory-eligible Contracts corpus
  ↓
next authoritative B0–B4 batch
```

The provider and methodological follow-up can proceed in parallel until both are ready for the next confirmatory freeze.

## Current findings carried forward

T24 produced five findings that were intentionally not retuned away:

1. `score_utility` treats GENERALIZE as a numeric-band operation; month-year dates can therefore be scored optimistically. This requires a later protocol/scorer version before confirmatory evidence.
2. `contracts-v1` preserves deadlines unconditionally, so B4 can disclose a deadline even where the task marks it `NOT_REQUIRED`.
3. B2 pseudonymizes CNPJ/CPF where the Contracts policy/oracle require REMOVE; this remains a legitimate treatment difference.
4. Detector performance is near-perfect by construction on the labeled-line corpus and must not be generalized to natural contracts.
5. Contracts v1 is small (`N=12`) and uses one Contracts policy version; requester-role/provider-class effects are not identified by this corpus.

These findings remain pilot evidence and do not invalidate the T24 freeze.

## Revised working schedule

Planning windows only; methodological integrity takes precedence over dates.

| Stage | Working window | Status |
| --- | --- | --- |
| T23 methodology freeze | 10–11 Sep | ✅ complete |
| T12 normalized ingestion | 11 Sep | ✅ complete |
| Issue #56 Contracts domain extensions | 12 Sep | ✅ complete ahead of target |
| T24 Contracts v1 + oracle | 12 Sep | ✅ complete ahead of original 17–21 Sep window |
| T22 real provider | 12–24 Sep | implementation complete; **in validation** |
| protocol/scorer follow-up for date-aware utility | 13–24 Sep | next methodological gate; may run parallel to T22 |
| new confirmatory-eligible Contracts corpus freeze | 22–27 Sep | only after revised methodology is frozen |
| integration + frozen provider/config + next B0–B4 readiness | 25–29 Sep | future |
| M3 aggressive target | 25 Sep | possible only if T22 and methodological follow-up remain narrow |
| M3 safe target | 30 Sep | protected target |

## Schedule guardrails

- Do not relabel `contracts/v1` as confirmatory; its inspection history permanently prevents that classification.
- Do not edit `post-pilot-v1` to fix the date-generalization utility issue; create a new protocol version if the metric/scorer definition changes.
- Do not author or inspect a future confirmatory Contracts corpus until the applicable protocol, scorer semantics, provider/model/config and treatment implementations are frozen.
- T22 must provide real provider metadata and safe failure behavior before authoritative real-LLM utility/token/cost claims.
- If the revised methodology or T22 slips, move the confirmatory corpus/run rather than weakening the freeze discipline.

## Milestone 3 closure

M3 remains open until all of the following are true:

1. T23 protocol freeze is complete ✅;
2. T12 structured ingestion is complete ✅;
3. Contracts-specific domain support is frozen ✅;
4. Contracts v1 pilot corpus/oracle is frozen and historically classified ✅;
5. a real provider is available with reproducibility/safe-failure metadata (T22);
6. the T24 utility-scoring finding is resolved through an explicit methodological version before confirmatory use;
7. a new confirmatory-eligible Contracts corpus can be frozen without using its own treatment outcomes to tune treatments/policies/metrics;
8. the next B0–B4 batch can launch with provider/config/treatment/scoring provenance frozen in advance.

## Master/develop boundary

Current M3 work remains on `develop`. Promotion `develop → master` remains a separate integration/CI boundary and is not performed by feature/review PRs.
