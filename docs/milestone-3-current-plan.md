# Milestone 3 — current execution plan

Last updated: 2026-09-21 (America/Sao_Paulo)

Normative methodology is in `docs/research/post-pilot-protocol-v1.md` (frozen, historical) and,
since Gate 6, `docs/research/post-pilot-protocol-v2.md` (current, `CURRENT_PROTOCOL_ID`). This
document records execution order only.

## Operational status: RESUMED at gate 6 (2026-09-21)

Milestone 3 remains scientifically open. The demo track that previously paused it is done: T20
demo integration, T21/T30 guided Next.js UI (T30 / Issue #82, merged to `master` in #83 at
`509c4bf`) and T25 deploy/publish are all complete, and a hosted advisor-facing demo URL exists.
M3 therefore resumes at **gate 6**.

```text
T20 demo integration ✅
  ↓
T21/T30 / Issue #82 — guided Next.js UI ✅
  ↓
T25 / Issue #42 — containerize/deploy and publish advisor URL ✅
  ↓
Gate 6 / Issue #38 — date-aware GENERALIZE utility scoring (post-pilot-v2) — IN REVIEW
  ↓
Gate 7 — newly authored confirmatory-eligible Contracts corpus
```

**Gate 6 is in review** (PR against `master`, see the PR linked from Issue #38): the
methodological finding below (item 1 in "Current scientific findings carried forward") is fixed
by `docs/research/post-pilot-protocol-v2.md`, following v1 §11's change procedure exactly —
`post-pilot-v1` is not edited, `CURRENT_PROTOCOL_ID` moves to `post-pilot-v2`. Gate 6 counts as
complete only once that PR is merged (per CLAUDE.md's Workflow state section: merged into
`develop`/`master` is not a synonym for "PR open").

## M3 state preserved

Completed closure gates:

1. T23 / Issue #36 — post-pilot methodology freeze ✅
2. T12 / Issue #9 — normalized structured ingestion ✅
3. Issue #56 — Contracts domain support freeze ✅
4. T24 / Issue #37 — Contracts v1 pilot corpus/oracle freeze ✅
5. T22 / Issue #30 — real Anthropic provider readiness ✅

Current state: **5/8 closure gates complete** (gate 6 in review, not yet merged — counted only
after merge, per CLAUDE.md's Workflow state section).

Remaining:

6. Gate 6 / Issue #38 — explicit methodological resolution of the T24 date/generalization
   utility-scoring finding — **in review**, `post-pilot-v2`;
7. a newly authored confirmatory-eligible Contracts corpus, frozen only after the applicable
   methodology/scorer/provider configuration is frozen — **next gate**;
8. next B0–B4 launch readiness with provider/config/treatment/scoring provenance frozen in
   advance — also depends on resolving the numeric-band GENERALIZE issue filed alongside Gate 6
   (see the linked issue) before an authoritative batch.

## Current scientific findings carried forward

T24 produced findings that remain intentionally unresolved during demo work:

1. ~~`score_utility` treats GENERALIZE as a numeric-band operation; month-year dates can
   therefore be scored optimistically.~~ **Resolved by Gate 6 / Issue #38, `post-pilot-v2`**
   (see the Operational status section above and
   `docs/research/post-pilot-protocol-v2.md`). A related, separate defect in the same numeric-
   band rule — it never checks the band actually contains the original value — was found during
   this fix and filed as its own issue rather than folded into this one; it remains open and
   must be resolved or explicitly accepted before Gate 8.
2. `contracts-v1` preserves deadlines unconditionally, so B4 can disclose a deadline even where the task marks it `NOT_REQUIRED`.
3. B2 pseudonymizes CNPJ/CPF where the Contracts policy/oracle require REMOVE; this remains a legitimate treatment difference.
4. Detector performance is near-perfect by construction on the labeled-line corpus and must not be generalized to natural contracts.
5. Contracts v1 is small (`N=12`) and uses one Contracts policy version; requester-role/provider-class effects are not identified by this corpus.

These remain pilot/development findings and do not block the advisor demo.

## Scientific guardrails remain unchanged

- `docs/research/post-pilot-protocol-v1.md` remains immutable — Gate 6 created
  `post-pilot-v2` rather than editing it, per v1 §11's change procedure.
- `corpus/contracts/v1` remains permanently `pilot_development` because its treatment outcomes were inspected.
- Do not relabel `contracts/v1` as confirmatory.
- Do not author or inspect a future confirmatory Contracts corpus until the applicable protocol, scorer semantics, provider/model/config and treatment implementations are frozen.
- Demo work must not tune B0–B4, policies, scorer, oracle or scientific outcomes for presentation purposes.

## Why the pause did not block the demo

The advisor demo consumed capabilities already completed by the research track:

- T12 structured ingestion;
- Contracts domain and `contracts-v1` governance;
- T22 real-provider support;
- the shared B0–B4 implementation and application boundary.

The M3 items resolved at Gate 6, and the ones still open (gates 7-8), concern defensible
confirmatory scientific claims, not whether the mechanism can be demonstrated safely to
prospective advisors.

## Resume point

M3 has resumed at gate 6 (see Operational status above). Once Gate 6's PR merges, the next gate
is **Gate 7**: authoring and freezing a new confirmatory-eligible Contracts corpus, without
tuning, under `post-pilot-v2`.

Do not skip directly to a new confirmatory corpus or authoritative B0–B4 run — Gate 7 must be
frozen before its own results are inspected, per `post-pilot-v2` §1 (inherited from v1).

## Branch boundary

Feature/demo work targets `develop`. Promotion `develop → master` remains a separate integration/CI boundary and is not performed by feature/review PRs.
