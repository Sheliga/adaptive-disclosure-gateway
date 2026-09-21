# Milestone 3 — current execution plan

Last updated: 2026-09-21 (America/Sao_Paulo)

Normative methodology is in `docs/research/post-pilot-protocol-v1.md` (frozen, historical),
`docs/research/post-pilot-protocol-v2.md` (frozen, historical, superseded) and
`docs/research/post-pilot-protocol-v3.md` (current, `CURRENT_PROTOCOL_ID`). This document
records execution order only.

## Operational status: Gate 6 merged, Issue #85 in review (2026-09-21)

Milestone 3 remains scientifically open. The demo track that previously paused it is done: T20
demo integration, T21/T30 guided Next.js UI (T30 / Issue #82, merged to `master` in #83 at
`509c4bf`) and T25 deploy/publish are all complete, and a hosted advisor-facing demo URL exists.
M3 resumed at **gate 6**, which has since merged; the current dependency is Issue #85.

```text
T20 demo integration ✅
  ↓
T21/T30 / Issue #82 — guided Next.js UI ✅
  ↓
T25 / Issue #42 — containerize/deploy and publish advisor URL ✅
  ↓
Gate 6 / Issue #38 — date-aware GENERALIZE utility scoring (post-pilot-v2) ✅ MERGED (PR #86, d1583f6)
  ↓
Issue #85 — numeric-band GENERALIZE fidelity (post-pilot-v3) — IN REVIEW (current dependency)
  ↓
Issue #87 — structured oracle references (post-pilot-v4) — OWNER DECIDED, BEFORE GATE 7
  ↓
Issue #88 — NumericBandStrategy Brazilian-format amount parsing — MOVED BEFORE GATE 7 BY OWNER
  ↓
Gate 7 — newly authored confirmatory-eligible Contracts corpus, authored under post-pilot-v4
  ↓
Gate 8 — next authoritative B0–B4 batch
```

**Gate 6 is merged** (PR #86, merge commit `d1583f6`): the methodological finding below (item 1
in "Current scientific findings carried forward") is fixed by
`docs/research/post-pilot-protocol-v2.md`, following v1 §11's change procedure exactly —
`post-pilot-v1` is not edited, `CURRENT_PROTOCOL_ID` moved to `post-pilot-v2`. Gate 6 now counts
as complete (per CLAUDE.md's Workflow state section: merged into `develop`/`master` is not a
synonym for "PR open" — this PR is merged).

**Current operational dependency: Issue #85** (numeric-band GENERALIZE fidelity) — the related,
separate defect found during the Gate 6 audit and deliberately left open by that PR's scope
discipline. Fixed and frozen as `docs/research/post-pilot-protocol-v3.md`, in review in a PR to
`develop`. **Owner-decided resulting order: Gate 6 ✅ → Issue #85 (`post-pilot-v3`) → Issue #87
(`post-pilot-v4`, structured oracle references) → Issue #88 (decision/fix) → Gate 7 → Gate 8** —
see "Issue #87 (reviewer's 'Issue #1') — methodological ordering decision" below for the
analysis and the owner's decision on both issues.

## M3 state preserved

Completed closure gates:

1. T23 / Issue #36 — post-pilot methodology freeze ✅
2. T12 / Issue #9 — normalized structured ingestion ✅
3. Issue #56 — Contracts domain support freeze ✅
4. T24 / Issue #37 — Contracts v1 pilot corpus/oracle freeze ✅
5. T22 / Issue #30 — real Anthropic provider readiness ✅
6. Gate 6 / Issue #38 — date-aware GENERALIZE utility scoring, `post-pilot-v2` ✅ (merged via
   PR #86, `d1583f6`)

Current state: **6/8 closure gates complete**.

Remaining:

7. a newly authored confirmatory-eligible Contracts corpus, frozen only after the applicable
   methodology/scorer/provider configuration is frozen — **next gate after Issue #85, Issue #87
   and Issue #88**, authored under `post-pilot-v4` (once #87 is implemented) rather than
   `post-pilot-v3`. The owner decided both #87 (option 1: `post-pilot-v4`, structured
   category/operator/value oracle references) and #88 (Brazilian-format amount parsing) must be
   settled *before* Gate 7 authoring, not merely before Gate 8 — see below;
8. next B0–B4 launch readiness with provider/config/treatment/scoring provenance frozen in
   advance — depends on Gate 7 above, with #87/#88 already resolved ahead of it.

## Current scientific findings carried forward

T24 produced findings that remain intentionally unresolved during demo work:

1. ~~`score_utility` treats GENERALIZE as a numeric-band operation; month-year dates can
   therefore be scored optimistically.~~ **Resolved by Gate 6 / Issue #38, `post-pilot-v2`**
   (merged via PR #86). A related, separate defect in the same numeric-band rule — it never
   checked the band actually contains the original value — was found during this fix and filed
   as its own issue (#85) rather than folded into this one. ~~It remains open and must be
   resolved or explicitly accepted before Gate 8.~~ **Resolved by Issue #85, `post-pilot-v3`**
   (see the Operational status section above and `docs/research/post-pilot-protocol-v3.md`,
   in review). A further, separate reference-extraction/sufficiency-semantics issue (#87) and a
   separate treatment-behavior defect in the generator's own Brazilian-format amount parsing
   (#88) were found during that fix and filed as their own issues; the owner decided both must be
   resolved *before* Gate 7 authoring — see "Issue #87 (reviewer's 'Issue #1') — methodological
   ordering decision" below.
2. `contracts-v1` preserves deadlines unconditionally, so B4 can disclose a deadline even where the task marks it `NOT_REQUIRED`.
3. B2 pseudonymizes CNPJ/CPF where the Contracts policy/oracle require REMOVE; this remains a legitimate treatment difference.
4. Detector performance is near-perfect by construction on the labeled-line corpus and must not be generalized to natural contracts.
5. Contracts v1 is small (`N=12`) and uses one Contracts policy version; requester-role/provider-class effects are not identified by this corpus.

These remain pilot/development findings and do not block the advisor demo.

## Scientific guardrails remain unchanged

- `docs/research/post-pilot-protocol-v1.md` and `post-pilot-protocol-v2.md` remain immutable —
  Gate 6 created `post-pilot-v2` and Issue #85 created `post-pilot-v3` rather than editing an
  earlier document, per v1 §11's change procedure.
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

## Issue #87 (reviewer's "Issue #1") — methodological ordering decision

GitHub Issue #1 ("Define B0–B4 experimental treatments") is closed and unrelated; the reviewer's
"Issue #1" is #87. The classification uses a single structural test: could a future decision on
this issue change anything that Gate 7 freezes? The answer is yes.

Items (a) and (b) of #87 define the *sufficiency* half of the numeric-band utility rule.
`post-pilot-v3` leaves that half unchanged on purpose, while making "no stated reference" score
`indeterminate`.

- **(a) Lower-bound equality.** A reference equal to a band's lower bound always scores ambiguous
  (`ref < lower or ref >= upper`). Whether that is correct depends on a comparison operator
  ("above" vs "within") that exists only in the task prose. `CaseOracle` (`corpus/oracle.py`,
  `extra="forbid"`) has no field for it. Demonstrated on `hr_salary_analysis_001` ("falls within
  R$ 5000.00 to R$ 10000.00"): references `[5000.0, 10000.0]` against band `R$ 5000-10000` give
  `indeterminate`/`ambiguous`.
- **(b) Blind reference extraction.** `_reference_values` treats every number outside the oracle
  spans as a reference, for every category. Throwaway runs on a synthetic Gate-7-style contract
  text showed three failures:
  - a stray date (`2026-02-27` → `2026, -2, -27`), `clause 7.2` or `30 days` makes correct bands
    ambiguous;
  - one category's threshold contaminates another category's band;
  - a Brazilian-format threshold `R$ 900.000,00` is read as `[900.0, 0.0]` and yields a spurious
    `answerable`.

So whether an authored Gate 7 case is decidable or ambiguous depends on the #87 decision, and a
resolution may require a new oracle field. Both corpus SCHEMA documents forbid adjusting case
text, offsets or reference values after freeze, and this M3 plan's own guardrails forbid
authoring before the scorer semantics are frozen. **#87 must therefore be settled before Gate 7
authoring**, in one of two ways:

1. a versioned `post-pilot-v4` with oracle-declared numeric references and comparison operators,
   read by the scorer instead of regex-scanning the text;
2. a formally accepted, versioned limitation with authoring constraints enforced by a corpus
   test:
   - at most one numeric category in `answer_depends_on_categories` per case;
   - no numeric tokens outside oracle spans other than the intended references;
   - references in `R$ <digits>.<2 digits>`;
   - band-edge equality documented as scored ambiguous.

#87 is **separable from #85**: #85 concerns fidelity, #87 concerns sufficiency. It does not
belong in the #85 PR. Item (c), the missing minimum-width check, is scorer-only and on its own
could wait until before Gate 8, but it can ride along with the same decision.

### Owner decision (2026-09-21)

**#87 is resolved by option 1, before Gate 7: a new protocol version `post-pilot-v4` with
structured utility references declared explicitly in the oracle.** Each reference carries a
category, a comparison operator and a value (or a collection, when a case genuinely has several)
— for example `category: contract_value, operator: greater_than_or_equal, value: 500000`; the
exact schema follows the existing oracle-model architecture (`corpus/models.py`/`corpus/oracle.py`).

Rationale, in the owner's words: `_reference_values` infers ground truth from free text. It
cannot know which category a number belongs to or which operator applies (`>`, `>=`, within),
and it treats any number outside spans as a reference. That information is part of the task
specification and belongs in the oracle, not in scorer guesswork. **Option 2 (authoring
constraints) was rejected**: it would encode scorer limitations as fragile lexical rules in the
corpus and reduce the naturalness and external validity of a contracts corpus. Option 1 also
fixes the lower-bound case directly: for band `[500000, 550000)`, `value > 500000` stays
ambiguous, while `value >= 500000` is decidable — the operator, not a hardcoded comparison
direction, decides.

**Requirements on `post-pilot-v4`:**

- the oracle references exist **only** for evaluation and must never reach the treatment/provider
  payload or give the system under evaluation any extra information, with explicit no-leak tests
  (mirroring this ticket's own no-leak discipline);
- `corpus/hr/v1` and `corpus/contracts/v1` and their historical results stay intact — `v4` creates
  a clear boundary and must not retrofit structured references into the old corpora.

**#88 is no longer classified "B / accept as limitation" — the owner moved it before Gate 7.**
The structural test above (could a future decision change what Gate 7 freezes?) originally
classified #88 as B, because v3's strict oracle grammar (`^R\$ \d+\.\d{2}$`) already makes a
Brazilian-format numeric oracle value `unscorable_original`, so a v3-conformant corpus never
exercises the defect. The owner rejects that framing: #88 is a **treatment** defect
(`R$ 125.000,00` can become a materially wrong band), and freezing a Brazilian contracts corpus
in the `R$ 125000.00` dotted-decimal format only because the current parser needs it would let
the implementation dictate the corpus, not the other way around. #88 may be declared out of
scope only if there is an **independent** methodological justification for a canonical
dotted-decimal-only corpus — "the current parser only supports that" is not sufficient. Note that
`post-pilot-v3`'s own strict oracle grammar above is the *current* rule and is not changed by
this decision; resolving #88 may revisit the scorable oracle amount format in a later protocol
version, but that is out of scope for `post-pilot-v3` itself.

**Gate 7 prerequisite noted:** the new Gate 7 corpus directory must be added to the coherence
guard's registered-corpus list (`REGISTERED_CORPUS_DIRS` or equivalent in the corresponding test
file), so that the applicable format constraint is actually enforced on it.

**Owner-decided resulting order:** Gate 6 ✅ → #85 (`post-pilot-v3`) → #87 (`post-pilot-v4`,
structured oracle references) → #88 (decision/fix) → Gate 7 → Gate 8.

`Issue #1 (#87): A`
`Próximo passo após #85: #87 (post-pilot-v4)`

## Resume point

M3 resumed at gate 6, which has merged (see Operational status above). The current dependency is
Issue #85 (numeric-band GENERALIZE fidelity, `post-pilot-v3`), in review. Once that PR merges,
the next steps are **Issue #87** (`post-pilot-v4`, structured category/operator/value oracle
references — owner-decided, option 1) and **Issue #88** (Brazilian-format amount parsing,
moved before Gate 7 by the owner) — both must be settled before Gate 7 authoring starts. Only
after both are settled does **Gate 7** start: authoring and freezing a new confirmatory-eligible
Contracts corpus, without tuning, under `post-pilot-v4`.

Do not skip directly to a new confirmatory corpus or authoritative B0–B4 run — Gate 7 must be
frozen before its own results are inspected, per `post-pilot-v3`/`post-pilot-v4` §1 (inherited
from v2 and v1).

## Branch boundary

Feature/demo work targets `develop`. Promotion `develop → master` remains a separate integration/CI boundary and is not performed by feature/review PRs.
