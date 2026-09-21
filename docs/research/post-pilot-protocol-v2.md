---
protocol_id: post-pilot-v2
status: FROZEN
frozen_date: 2026-09-21
supersedes: post-pilot-v1
ticket: Gate 6 / Issue #38
---

# Post-pilot confirmatory analysis protocol — v2

This document is a **delta** on `docs/research/post-pilot-protocol-v1.md`, not a rewrite. Every
section of v1 applies in full **except**:

- §6.1 (utility outcomes), which gains a new subsection, §6.1a below, for GENERALIZE on a
  date-shaped category;
- provenance (v1 §13), which gains `protocol_id` as a field this codebase actually emits, not
  merely a documented requirement for future execution.

v1 itself is never edited: its own front matter, `frozen_date: 2026-09-11`, and every
methodological rule it states remain exactly as frozen. Where this document is silent, v1
governs.

## 0. Versioning

This is the first exercise of v1 §1/§11's own change procedure: a defect was found in a frozen
metric's implementation (not a result anyone wanted to look better), so per §11 the fix is a new
protocol version, not an edit to v1. `protocol_id: post-pilot-v2` is registered in
`src/adaptive_disclosure_gateway/experiments/post_pilot_protocol.py`
(`FROZEN_PROTOCOL_IDS`, now containing both `post-pilot-v1` and `post-pilot-v2`;
`CURRENT_PROTOCOL_ID` now `post-pilot-v2`). `tests/test_post_pilot_protocol.py` pins that the two
can never silently drift apart, for both documents independently.

## 1. Rationale: a type error, not a calibration choice

`score_utility` (`src/adaptive_disclosure_gateway/experiments/scoring/utility.py`) scores every
`GENERALIZE` action through `_band_is_decidable`, which applies a numeric-band regex
(`_BAND_PATTERN = r"(-?\d+)\s*-\s*(-?\d+)\s*$"`) to whatever string the treatment produced. For a
numeric GENERALIZE (e.g. `"R$ 600000-650000"`) that is exactly the intended rule (v1 §6.1,
§12). For a **date** GENERALIZE, `MonthYearDateStrategy` (`transformations/generalization.py`)
produces a month-year string like `"2026-02"`. `_BAND_PATTERN` matches that too — as a "band"
from `2026` down to `2` — and `_band_is_decidable` then asks whether every reference number in
the case text falls strictly outside `[2, 2026)`. Every plausible reference figure in these
corpora (dates, monetary amounts, counts) is either far above 2026 or, if a genuine reference
number is even smaller, the check still degenerates: with no reference numbers at all,
`all([])` is vacuously `True`. The result: **every** month-year GENERALIZE output, including a
wrong month (`"2026-03"` against an actual deadline of `2026-02-27`), a wrong year
(`"1999-02"`), a day-precision string that was never actually generalized (`"2026-02-27"`), or
even a malformed one (`"2026-13"`), was scored `answerable`/`generalized_band_decidable`. This is
a type error: a rule authored for one representation (a numeric interval) silently accepted a
different representation (a coarsened calendar date) that happens to parse under the same regex,
and every one of the cases above should be `not_answerable` — the disclosure-controlled payload
either loses the date's actual value or affirmatively lies about it.

The following table demonstrates the outcome before this fix, for `deadline`, oracle value
`2026-02-27`, `required = "day"` (§2 below):

| Transformed value | Old outcome (v1) | New outcome (v2) |
| --- | --- | --- |
| `2026-02` (correct month-year GENERALIZE) | `answerable` / `generalized_band_decidable` | `not_answerable` / `generalized_date_insufficient_granularity` |
| `2026-03` (wrong month) | `answerable` / `generalized_band_decidable` | `not_answerable` / `generalized_date_wrong_value` |
| `1999-02` (wrong year) | `answerable` / `generalized_band_decidable` | `not_answerable` / `generalized_date_wrong_value` |
| `2026-02-27` (day kept — not actually generalized) | `answerable` / `generalized_band_decidable` | `not_answerable` / `generalized_date_excess_precision` |
| `2026-13` (invalid month) | `answerable` / `generalized_band_decidable` | `not_answerable` / `generalized_date_invalid` |

### Requirement provenance predates any Contracts result

The granularity this document requires for `deadline` (§2) is not selected in response to how
any treatment performed. `docs/contracts-policy-matrix.md`'s "`deadline` as a hard `preserve`"
section, written in commit `66e4677` (2026-09-12 02:23 −03, Issue #56), states: "a legal
deadline coarsened to a month is not a term of a contract: 'sometime in March' cannot be
complied with or enforced." `corpus/contracts/v1` itself was authored afterward (commit
`f62fd65`, 2026-09-12 11:20), and the first B0–B4 Contracts run happened after that. Every
required-deadline `expected_answer` across `corpus/contracts/v1` independently cites the full
ISO day, not a coarsened form — pinned as a coherence guard test in
`tests/test_experiments_scoring_date_utility.py`, so this fact cannot silently drift from the
corpus's own content. The day-granularity requirement below therefore satisfies v1 §11's
anti-tuning discipline: it is a pre-result artifact, applied treatment-agnostically, that can
only ever *lower* credit relative to the old, defective rule — see §6 below.

## 2. The formal rule

### 2.1 Registry

`DATE_UTILITY_REQUIRED_GRANULARITY` (`experiments/scoring/utility.py`) maps a category to its
required GENERALIZE granularity. Today:

| Category | Required granularity |
| --- | --- |
| `deadline` | `day` |

A GENERALIZE on a category in this registry is scored by §2.2's rule below; every other
GENERALIZE (numeric categories: `salary`, `contract_value`, `penalty_amount`) keeps v1's
existing numeric-band rule (`_band_is_decidable`), byte-for-byte unchanged. `birth_date` has a
`MonthYearDateStrategy` registered in `transformations/generalization.py` but is not a member of
`CorpusCategory` (`corpus/models.py`) — no oracle can reference it in
`answer_depends_on_categories`, so `score_utility` never reaches it through a real case, and it
is correctly out of scope for this registry (pinned by
`tests/test_experiments_scoring_date_utility.py`'s drift guard, which also asserts this fact
rather than assuming it silently).

**Limitation.** Granularity is per category, not per task: every task that needs a `deadline`
answer is held to day-level granularity, even a hypothetical future task that would only need
month-level precision. A future task requiring a coarser granularity for an already-registered
category needs a new protocol version's own registry entry, not a change to this one — the same
freeze-before-inspection discipline v1 §1/§11 already require for every other methodological
choice.

### 2.2 `classify_generalized_date(original, transformed, required)`

A pure function, independent of any oracle object beyond the two string values and the
category's required granularity (it never reads `expected_actions` — v1 §5's isolation between
the conformance and utility oracles is unaffected; pinned by the existing AST test in
`tests/test_experiments_scoring.py`).

- **`original`** is the oracle span's own value. It must match strict `^\d{4}-\d{2}-\d{2}$` and
  be a real calendar date (`datetime.date(y, m, d)` must not raise). Anything else —
  including an impossible date like `2026-02-30`, or a non-ISO shape like `27/02/2026` — yields
  `not_answerable` / `generalized_date_unscorable_original`, evaluated **before** the
  transformed-value grammar below (an unscorable original makes the transformed value
  unevaluable regardless of its own shape).
- **`transformed`** must match one of exactly three closed grammar forms: `^\d{4}-\d{2}-\d{2}$`
  (day), `^\d{4}-\d{2}$` (month, month value 01–12), `^\d{4}$` (year). Only `YYYY-MM` is a form
  `MonthYearDateStrategy` actually produces; the other two exist so the classifier can name a
  day-precision "generalization" as excess precision (below) and, in principle, score a
  category that might one day generalize to year. Every other shape — a slash-separated date, a
  locale-formatted month name, a single-digit month, an out-of-range month (`2026-13`), `None`,
  or the empty string — is `not_answerable` / `generalized_date_invalid`. **The protocol defines
  no locale or day-month-order rule**: a string like `02/2026` is not "recovered" as
  day-month-swapped or month-year-swapped; it is simply invalid.

Evaluated in this order once both of the above pass; the first match wins:

1. `original` fails validity → `not_answerable`, `generalized_date_unscorable_original`;
2. `transformed` fails the closed grammar → `not_answerable`, `generalized_date_invalid`;
3. the parsed components of `transformed` disagree with `original`'s own components at the
   granularity `transformed` actually carries (e.g. a month-granularity `transformed` is
   compared on year+month only, never on a day `original` does not expose at that granularity)
   → `not_answerable`, `generalized_date_wrong_value`;
4. `transformed` is day-granularity → `not_answerable`, `generalized_date_excess_precision`.
   This is evaluated **unconditionally**, even when `required` is itself `"day"`: a
   day-precision GENERALIZE output never actually generalized anything, which breaks the
   GENERALIZE contract (`transformations/generalization.py`'s own "must never return the exact
   original value" invariant) — this classifier fails closed rather than crediting a
   generalization that did not happen;
5. `transformed`'s granularity is coarser than `required` → `not_answerable`,
   `generalized_date_insufficient_granularity`;
6. otherwise → `answerable`, `generalized_date_sufficient_granularity`.

**Equivalence is by parsed components, never string equality with `original`.** `"2026-02"` is
equally valid against an original of `2026-02-01` or `2026-02-27` — the day component is simply
outside what a month-granularity comparison examines. This is a deliberate design choice: the
whole point of GENERALIZE is that the transformed form does not pin down the day, so requiring
string equality with a specific day would make every correct GENERALIZE fail.

**The outcome set stays closed.** No `"partial"` outcome is introduced; every classification is
exactly `answerable` or `not_answerable`, matching the existing `UtilityOutcome` Literal.

**No-leak.** Every reason above is a fixed string constant, naming a category of failure, never
interpolating either date value. `CategoryUtility` (the dataclass this classifier's result feeds
into) carries only `category`/`outcome`/`reason` — no `original`/`transformed` field exists on
it for a value to leak through. Pinned adversarially in
`tests/test_experiments_scoring_date_utility.py` (a distinctive synthetic date pair, verified
absent from the reason string and from a full serialization of `UtilityScore`), and the existing
repository-wide `tests/test_no_sensitive_value_in_raises.py` continues to cover any future
`raise` this module might add.

## 3. Provenance / version boundary

`RunIdentity` (`experiments/run_identity.py`) gains a `protocol_id: str` field, populated from
`post_pilot_protocol.CURRENT_PROTOCOL_ID` and validated against `FROZEN_PROTOCOL_IDS`
(`validate_protocol_id`) at the point `execution.py` builds it — a run can no longer be produced
under an unregistered protocol id. `RunIdentity.schema_version` is bumped to
`t10-experiment-runner-v4` to reflect the added field.
`experiments/artifacts.write_pilot_artifacts`'s manifest also carries `protocol_id` at the top
level (alongside `schema_version`/`corpus_version`), so a manifest and its own rows can never
silently disagree about which protocol scored them — both are sourced from the same
`CURRENT_PROTOCOL_ID` constant.

This is additive, not a rewrite of history: every artifact already committed under
`RunIdentity.schema_version == "t10-experiment-runner-v3"` (the M2 HR pilot and the
`corpus/contracts/v1` run, `artifacts/experiments/contracts/v1/954ffae9f6e143d6af45e4842f6daef9`)
stays on disk exactly as written, still correctly labeled `post-pilot-v1` in its own
`reproducibility.protocol_id` field (that field already existed for the Contracts run — see
`scripts/run_contracts_v1_pilot.py` — this document only makes the *row-level* field the manifest
already implied). Nothing under `artifacts/` is rewritten by this protocol version.

## 4. Historical comparability

- **HR v1 results are fully comparable.** `corpus/hr/v1` has no date-shaped category at all
  (`GENERALIZATION_STRATEGIES` registers `MonthYearDateStrategy` only for `birth_date`, which is
  not a `CorpusCategory` and appears in no HR case's `answer_depends_on_categories`). Every HR v1
  utility number this protocol's predecessor produced is unaffected by this change.
- **Contracts v1 conformance, exposure and unnecessary-disclosure results are comparable.** This
  change touches only `score_utility`'s GENERALIZE branch for date categories; conformance
  (`expected_actions` matching), exposure (the REMOVE/PSEUDONYMIZE/GENERALIZE/PRESERVE ladder)
  and unnecessary disclosure (binary/ordinal) never consult `classify_generalized_date` at all.
- **Contracts v1 utility is NOT comparable** on the 12 rows where a required `deadline` scored
  `generalized_band_decidable` under v1: B1, B2 and B3, on
  `contracts_deadline_tracking_001`/`002` and `contracts_obligation_relation_001`/`002`
  (4 cases × 3 treatments = 12 category-level rows). **Verified by re-scoring** the committed
  run's inputs (`artifacts/experiments/contracts/v1/954ffae9f6e143d6af45e4842f6daef9`) against
  the patched scorer in a throwaway script (not committed):
  - all 12 of those rows flip from `deadline` category outcome `answerable` /
    `generalized_band_decidable` to `not_answerable` / `generalized_date_insufficient_granularity`
    (4 per treatment: B1, B2, B3);
  - of those 12, **10 flip the case's overall `UtilityScore.overall`** from `answerable` to
    `not_answerable` — **B1: 2** (the other two, both `contracts_obligation_relation_*`, were
    already `not_answerable` overall before this fix, because those cases also depend on
    `party_name`/`contract_value` and B1's static REMOVE/GENERALIZE choices already made the
    case unanswerable on a different category); **B2: 4**; **B3: 4**. This exactly matches the
    audit's predicted split;
  - on the 4 cases where B3's own overall utility flips (`contracts_deadline_tracking_001`/`002`,
    `contracts_obligation_relation_001`/`002`), the B3→B4 pairwise `utility_direction`
    (`aggregation.summarize_b3_to_b4`) moves from `"same"` (B4 also PRESERVEs `deadline` under
    `contracts-v1`, so both scored `answerable` before) to `"b4_better"` — B3's month-year
    GENERALIZE now correctly scores `not_answerable` while B4's PRESERVE stays `answerable`.
    Every other case's `utility_direction` (`incomparable` for the two `medical_or_prohibited`-
    style block cases, `same` for the remaining six) is unchanged.
  - No re-verification found a discrepancy with the audit's numbers.
- `corpus/contracts/v1` stays `pilot_development` regardless of this change — v1 §1's rule that a
  corpus whose results were inspected during development can never become
  `held_out_confirmatory` is untouched by a scoring fix.

## 5. No-post-result-tuning statement

This change satisfies v1 §11's four-step change procedure: (1) recorded here and in
`docs/implementation-status.md`; (2) `corpus/contracts/v1`'s existing run stays
`pilot_development` (it already was, and could never have become confirmatory once inspected);
(3) versioned as `post-pilot-v2`, this document; (4) no new held-out round is created by this
ticket — that is Gate 7, not Gate 6 (see below). The rule itself is treatment-agnostic (it reads
only the transformed string's own shape and the oracle's own original value, never which
treatment produced it) and derives from a pre-result artifact (§1 above). Its effect, disclosed
openly, is asymmetric: it can only ever move a date-category outcome from `answerable` to
`not_answerable` relative to the old rule, never the reverse — the old rule's defect was a
false-positive-*answerable* bug, and fixing it can only remove credit that should never have been
given, not add credit that was missing.

## 6. Out-of-scope findings (recorded, not fixed)

Discovered during this audit, deliberately **not** fixed by this ticket to keep the change
minimal and single-purpose:

- `_band_is_decidable` never checks that the reference figures used to judge decidability
  actually relate to a *correct* band containing the original value — a numeric GENERALIZE band
  that is simply wrong (does not contain the original at all) can still score `answerable` if no
  reference figure happens to fall inside it, and with zero reference figures every band is
  vacuously "decidable". Filed as a separate GitHub issue (linked below) rather than fixed here,
  because fixing it would touch the numeric-band path this ticket promises to leave unchanged,
  and because it needs its own methodological decision (what "the band is correct" means
  formally) before a fix can be written without repeating this ticket's own type-error mistake.
  Must be resolved, or explicitly accepted as a documented limitation via its own versioned
  protocol decision, before the Gate 8 authoritative B0–B4 batch.
- The same numeric-band code path is the one every non-date, non-numeric category would fall
  into if one were ever added without a `DATE_UTILITY_REQUIRED_GRANULARITY`-style registry entry
  of its own — unreachable today (every registered category is either purely numeric or a
  registered date category), but worth naming so a future category addition does not silently
  inherit numeric-band semantics by omission.

## 7. Change log

- 2026-09-21 — `post-pilot-v2` frozen (Gate 6 / Issue #38): adds §6.1a-equivalent date-aware
  GENERALIZE utility rule (this document's §2), the provenance/version-boundary fields (§3), and
  records historical-comparability impact on the `contracts/v1` pilot run (§4). No other
  methodological content changes; `post-pilot-v1` remains the frozen historical record of what
  governed every run before this date.
