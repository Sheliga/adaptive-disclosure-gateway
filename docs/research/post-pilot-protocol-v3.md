---
protocol_id: post-pilot-v3
status: FROZEN
frozen_date: 2026-09-21
supersedes: post-pilot-v2
ticket: Issue #85 / M3
---

# Post-pilot confirmatory analysis protocol — v3

This document is a **delta** on `docs/research/post-pilot-protocol-v2.md`, not a rewrite. Every
section of v2 — and, through it, v1 — applies in full **except**:

- §6.1 (utility outcomes), which gains a new subsection, §6.1b below, for GENERALIZE on a
  numeric-band category;
- provenance (v1 §13, carried by v2 §3), unaffected in shape — `RunIdentity.protocol_id` and
  the manifest-level `protocol_id` field already exist; only the value they carry moves forward
  to `post-pilot-v3`.

v2 itself is never edited: its own front matter, `frozen_date: 2026-09-21`, and every
methodological rule it states remain exactly as frozen. v1 remains untouched beneath it. Where
this document is silent, v2 governs (and, transitively, v1).

## 0. Versioning

This is the second exercise of v1 §1/§11's own change procedure (the first was Gate 6 /
`post-pilot-v2`): a defect was found in a frozen metric's implementation (not a result anyone
wanted to look better), so per §11 the fix is a new protocol version, not an edit to v1 or v2.
`protocol_id: post-pilot-v3` is registered in
`src/adaptive_disclosure_gateway/experiments/post_pilot_protocol.py` (`FROZEN_PROTOCOL_IDS`, now
containing `post-pilot-v1`, `post-pilot-v2` and `post-pilot-v3`; `CURRENT_PROTOCOL_ID` now
`post-pilot-v3`). `tests/test_post_pilot_protocol.py` pins that the three can never silently
drift apart, for every document independently.

**Semantic change: yes.** This is a classification-rule change under v1 §0's own test ("any
change to a number, a formula, a classification rule or a comparison cell requires a new
version") and v2 §2.1's promise that the numeric rule stays byte-for-byte unchanged under v2 —
both are exactly why this fix cannot land as a v2 patch and requires `post-pilot-v3`.

## 1. Rationale: fidelity and sufficiency are two distinct properties

`score_utility` (`src/adaptive_disclosure_gateway/experiments/scoring/utility.py`) scored every
numeric `GENERALIZE` action (`salary`, `contract_value`, `penalty_amount` — every category not
routed through v2's date-aware rule) through `_band_is_decidable`:

```python
def _band_is_decidable(transformed: str, references: list[float]) -> bool:
    match = _BAND_PATTERN.search(transformed)
    if not match:
        return False
    lower, upper = float(match.group(1)), float(match.group(2))
    return all(reference < lower or reference >= upper for reference in references)
```

This checks exactly one thing: whether every reference figure stated elsewhere in the case text
falls unambiguously on one side of the parsed band. It never checks the thing a reader would
assume "decidable" already implies — that the band actually **contains** the case's own original
value at all. These are two distinct properties, and the old rule checked only the second
(**sufficiency**: can the band be resolved against a stated reference) while silently skipping
the first (**fidelity**: is the band even a correct representation of the value it claims to
generalize). Checking sufficiency without first checking fidelity lets a *wrong* band pass as
`answerable` merely because no reference happens to fall inside it — and with zero references at
all, `all([])` is vacuously `True`, so *every* band was "decidable" by default.

### Minimal reproduction

Oracle value `R$ 125000.00` (a numeric span in some `salary`/`contract_value`/`penalty_amount`
category), transformed band `R$ 600000-650000` (does not contain `125000` at all — a wrong band,
however it arose: a treatment defect, a detector misread, a future treatment implementation
bug), reference figure `500000.0` stated elsewhere in the case text:

| Reference figures present | Old outcome (v2) | New outcome (v3) |
| --- | --- | --- |
| `[500000.0]` (outside the wrong band) | `answerable` / `generalized_band_decidable` | `not_answerable` / `generalized_band_excludes_original` |
| `[]` (none stated) | `answerable` / `generalized_band_decidable` (vacuous `all([])`) | `not_answerable` / `generalized_band_excludes_original` |
| `[620000.0]` (inside the wrong band) | `indeterminate` / `generalized_band_ambiguous` | `not_answerable` / `generalized_band_excludes_original` |

The old rule's outcome depends entirely on which reference figures happen to be present in the
text, never on whether the band is correct. The new rule's outcome is `not_answerable` in every
row, because the band is simply wrong — that fact alone should end the classification, before
any reference is even consulted.

Four other shapes shared the same blind spot and are fixed the same way: an **inverted** band
(`R$ 10000-5000`), a **degenerate** zero-width band (`R$ 5000-5000`, never produced by
`NumericBandStrategy` but not rejected by the old regex either), and a **malformed** band (a
Brazilian-formatted amount, a different currency, stray whitespace) all previously either parsed
into nonsense bounds or fell through to `False` inconsistently; the new rule names each with its
own closed reason (`generalized_band_invalid`) rather than leaving the behavior to depend on
regex accident.

## 2. Fidelity vs. sufficiency, and why the order matters

**Fidelity** — does the transformed band actually represent the original value at all: is it a
validly-shaped, non-degenerate, half-open interval, and does it contain the value it claims to
generalize? **Sufficiency** — granting that the band is a correct representation, can a reader
still resolve the underlying value against a reference stated elsewhere in the text, or does the
reference fall inside the band (leaving the comparison genuinely undecidable)? `hr_salary_
analysis_003`/`hr_department_aggregation_003` (`corpus/hr/v1/SCHEMA.md`) are the documented
illustration of a **sufficiency** failure on a **correct** band — the salary band is right, but
the stated minimum-wage floor happens to fall inside it, so "above or below the floor" cannot be
read off the band alone. That case is unaffected by this ticket: the band was never wrong, only
insufficiently informative relative to the stated reference, and it still scores `indeterminate`
under v3 exactly as it did under v2 — pinned by the existing regression test.

Fidelity must be checked **first**. A rule that checked sufficiency without first checking
fidelity — the v2/pre-v3 rule above — can rescue a wrong band into `answerable` merely because no
reference happens to land inside it; checking fidelity first closes that path unconditionally,
regardless of what references are or are not present in the text.

### Decision C (chosen): fidelity-first, sufficiency unchanged — and why A and B don't suffice

Three shapes of fix were considered for this defect. **Decision C** — check fidelity
unconditionally, then apply the pre-existing sufficiency rule unchanged, with an explicit
`no_reference` outcome when no reference is stated — is the one implemented (§3 below).

- **Option A — patch only the zero-reference vacuous-`True` case** (`all([])`), leaving the
  "does the band contain the value" question unchecked whenever at least one reference is
  present. **Rejected**: this is the narrower of the two failure modes the minimal reproduction
  table above documents, and leaves the wider one open — a wrong band with a reference figure
  that simply happens to fall outside it (row 1 of that table: `[500000.0]` against the wrong
  band `R$ 600000-650000`) would still score `answerable`/`generalized_band_decidable` under
  Option A, exactly as it did before this fix. Patching only the case that is easiest to notice
  (the vacuous default) without addressing the structural absence of any containment check would
  leave the actual defect — the rule never asks whether the band is correct — in place.
- **Option B — redefine "decidable" so any validly-shaped band is answerable without regard to a
  stated reference at all** (i.e., treat "the band contains the value" as sufficient by itself,
  dropping the reference-based sufficiency check entirely). **Rejected**: this would silently
  *add* credit relative to the pre-v3 rule for every band with zero or an unfavorably-placed
  reference — the reverse of what a defect fix is allowed to do under v1 §11's anti-tuning
  discipline (§7 below: a fix may only ever *remove* credit that should never have been given,
  never grant new credit the frozen protocol never promised). It would also invent a new
  decidability semantics with no documented basis — `corpus/hr/v1/SCHEMA.md` and v1 §6.1 define
  decidability only against a *stated* reference, and Option B would silently replace that
  definition rather than resolve the fidelity gap within it.
- **Option C (chosen) — fidelity first, then the existing sufficiency rule, unchanged** (§3
  below). Containment (fidelity) is checked as a precondition, independent of and prior to any
  reference; a band that fails it is `not_answerable` regardless of what references exist. A band
  that passes it is then judged by the *exact* pre-v3 sufficiency comparison (§3.2 step 5), with
  the one addition that zero references now yields an explicit `indeterminate` /
  `generalized_band_no_reference` rather than a vacuous `answerable`. This is the minimal change
  that closes both failure modes in the reproduction table, changes no comparison semantics that
  were not already broken, and cannot grant any credit the old rule did not already promise
  somewhere.

## 3. The formal rule

### 3.1 Registry

`NUMERIC_BAND_UTILITY_CATEGORIES` (`experiments/scoring/utility.py`) names every category this
rule governs: `salary`, `contract_value`, `penalty_amount` — exactly the categories whose
`transformations/generalization.py` strategy is `NumericBandStrategy`, and exactly the
complement of v2's `DATE_UTILITY_REQUIRED_GRANULARITY` registry among numeric-band-eligible
categories. The two registries are disjoint by construction and their union covers every
`GENERALIZATION_STRATEGIES` entry that is also a `CorpusCategory` — pinned by a drift guard test
in `tests/test_experiments_scoring_numeric_band_utility.py`. A GENERALIZE on any category in
neither registry is rejected outright (`generalized_category_unregistered`, §5 below) rather
than silently inheriting either rule's semantics — unreachable today, but named for the future.

### 3.2 `classify_generalized_band(original, transformed, references)`

A pure function, independent of any oracle object beyond the two string values and the list of
reference figures (it never reads `expected_actions` — v1 §5's isolation between the conformance
and utility oracles is unaffected).

- **`original`** is the oracle span's own value (`ExpectedSpan.value`) — **never**
  `Transformation.original`, for exactly the reason v2 §2.2 already established for the date
  rule: a detector misread or a span-matching mismatch must never let a wrong transformed band
  validate against its own wrong `original`. It must fullmatch `^R\$ (\d+\.\d{2})$` — the shape
  of every numeric oracle span value across both registered corpora. Parsed with `Decimal` via a
  scorer-owned strict parser, deliberately **not** `transformations/generalization.py`'s own
  `_parse_amount` (reusing it would make this fidelity check circular, and would inherit that
  parser's own Brazilian-thousands-format misparse — see §6 below). Anything else — a
  Brazilian-formatted amount (`R$ 9.200,00`), a bare number with no currency prefix, a different
  currency, an empty string, or `None` — yields `not_answerable` /
  `generalized_band_unscorable_original`, evaluated **before** the transformed value's own shape
  is even examined (an unscorable original makes the band unevaluable regardless of its own
  shape — mirrors v2 §2.2's ordering for the date rule).
- **`transformed`** must fullmatch `^R\$ (0|[1-9]\d*)-(0|[1-9]\d*)$` (matching
  `NumericBandStrategy.generalize`'s own `f"{prefix}{int(lower)}-{int(upper)}"` output exactly)
  **and** have `lower < upper`. Anything else — a malformed shape, a Brazilian-formatted amount,
  a different currency, stray whitespace, an inverted band (`lower >= upper` the wrong way), a
  degenerate zero-width band, `None`, or the empty string — is `not_answerable` /
  `generalized_band_invalid`.

Evaluated in this order once the above two checks pass; the first match wins:

1. `original` fails the strict parse → `not_answerable`, `generalized_band_unscorable_original`;
2. `transformed` fails the closed grammar or is inverted/degenerate → `not_answerable`,
   `generalized_band_invalid`;
3. the parsed band does not contain `original` at the half-open `[lower, upper)` interval
   `NumericBandStrategy` itself produces (`lower <= original < upper`) → `not_answerable`,
   `generalized_band_excludes_original` — **this is the fix**: a wrong band now fails
   unconditionally, never rescued by an absent or favorably-placed reference;
4. `references` is empty → `indeterminate`, `generalized_band_no_reference` — never vacuously
   `answerable`; no documented basis exists for crediting a band when no reference is stated at
   all (`corpus/hr/v1/SCHEMA.md`'s task-necessity/answer-coherence section and v1 §6.1 both
   define decidability only against a *stated* reference);
5. every reference falls strictly outside the band (`reference < lower or reference >= upper`
   for every reference) → `answerable`, `generalized_band_decidable`; otherwise → `indeterminate`,
   `generalized_band_ambiguous`. **Unchanged comparison semantics** from the pre-v3 rule — this
   step is copied byte-for-byte in its logic from `_band_is_decidable`, only reached now after
   fidelity has already been confirmed.

**The outcome set stays closed.** Every classification is exactly one of `answerable`,
`not_answerable` or `indeterminate` — matching the existing `UtilityOutcome` Literal, unchanged
by this ticket.

**No-leak.** Every reason above is a fixed string constant, naming a category of failure, never
interpolating either the original value, the band, or any reference figure.
`NUMERIC_BAND_UTILITY_REASONS` names the full closed set as a real constant.
`CategoryUtility` carries only `category`/`outcome`/`reason` — no field exists on it for a value
to leak through. Pinned adversarially in
`tests/test_experiments_scoring_numeric_band_utility.py` (a distinctive synthetic
original/band/reference triple, verified absent from the reason string and from a full
`repr()`/`json.dumps()` serialization of `UtilityScore`), and the existing repository-wide
`tests/test_no_sensitive_value_in_raises.py` continues to cover any future `raise` this module
might add.

## 4. Ground truth: the oracle `ExpectedSpan.value`, never a transformation's own field

Exactly as v2 §2.2 established for `classify_generalized_date`, `classify_generalized_band` is
always called with the oracle span's own `value` — `score_utility` pairs each `ExpectedSpan`
with its matched `Transformation` (`resolve_span_transformations`) specifically so this rule (and
the date rule) can be judged against ground truth, never against whatever a detector or
treatment self-reported as `Transformation.original`. A regression test constructs a
`Transformation.original` set to a value *inside* the wrong band while the oracle's real value is
outside it, and asserts the scorer still reports `not_answerable` — this is PR #86's principle
(the review finding that produced the same discipline for the date rule), applied here.

## 5. Category-unregistered fail-closed path

`score_utility`'s GENERALIZE branch now has three arms: a date-registry category (v2's
`classify_generalized_date`), a numeric-registry category (this document's
`classify_generalized_band`), and — new — anything in neither registry, which is rejected
outright as `not_answerable` / `generalized_category_unregistered` rather than silently falling
into either existing rule by omission. Unreachable today (every registered category is one or
the other; pinned by a drift guard test), but this closes v2 §6's third out-of-scope finding
(Issue #85) explicitly rather than leaving it as a named-but-unenforced risk.

## 6. Limitations (by design, not fixed here)

- **Brazilian thousands/decimal formats, negatives and other currencies are unscorable by
  design.** `_parse_strict_original_amount` accepts exactly `R$ <digits>.<2 digits>` — the shape
  every numeric oracle span value in both registered corpora already takes. A Brazilian-formatted
  amount (`R$ 9.200,00`), a negative amount, or a non-BRL currency yields
  `generalized_band_unscorable_original`, not a best-effort parse. This is deliberate: the
  generator (`NumericBandStrategy`/`_parse_amount`, `transformations/generalization.py`) has its
  own, separate Brazilian-format misparse (`R$ 1.275.000,00` → a wrong band), filed as its own
  issue (§8 below) rather than fixed here — reusing that parser for this fidelity check would
  make the check circular and inherit the same defect it exists to catch.
- **No-reference is always `indeterminate`, never `answerable`.** A hypothetical future task
  where "the band alone suffices, no stated reference needed" would require a new oracle field
  (some documented basis for what "sufficient" means without a reference) and its own protocol
  version — this document does not invent one.
- **Reference-extraction semantics are unchanged.** `_reference_values`'s own behavior — what
  counts as a candidate reference figure, and whether a reference exactly equal to a band's lower
  bound counts as "inside" the band for the sufficiency check (step 5 above) — is copied
  byte-for-byte from the pre-v3 rule and is explicitly out of scope here. See the new issue filed
  alongside this document (§8 below) for the follow-up this raises.

## 7. Anti-tuning statement

This change satisfies v1 §11's four-step change procedure exactly as v2 did for the date rule:
(1) recorded here and in `docs/implementation-status.md`; (2) every corpus this rule reaches
(`corpus/hr/v1`, `corpus/contracts/v1`) already stays `pilot_development` (unaffected by this
ticket); (3) versioned as `post-pilot-v3`, this document; (4) no new held-out round is created by
this ticket — that remains Gate 7, not this one.

**Provenance predates any result this fix could have been tuned against.** The band contract this
rule enforces — a half-open `[lower, upper)` interval, `f"{prefix}{int(lower)}-{int(upper)}"` —
is `NumericBandStrategy`'s own shape, frozen at commit `5a0cde3` (2026-09-06), before any HR
(2026-09-08) or Contracts (`corpus/contracts/v1`, 2026-09-12) result existed. This rule does not
invent a new definition of "correct band" — it enforces the one the generator itself already
implements, and was found and fixed *before* the historical impact below was computed (§9), not
in response to it. The rule is **treatment-agnostic**: it reads only the transformed string's own
shape, the oracle's own original value, and the case's own stated reference figures, never which
treatment produced the band. Its effect is **asymmetric and one-directional**: it can only ever
move a numeric-band outcome from `answerable`/`indeterminate` toward `not_answerable` relative to
the old rule, never the reverse — the old rule's defect was a false-positive-*answerable* (or
falsely-`ambiguous`-instead-of-`not_answerable`) bug, and fixing it can only remove credit that
should never have been given.

## 8. Related, separate issues filed (not fixed here)

Filed as their own GitHub issues rather than folded into this ticket, per the same
single-purpose-change discipline v2 §6 already followed:

- **[Issue #87](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/87) — Utility
  sufficiency proxy: reference extraction and lower-bound equality semantics.** (a) a reference
  exactly equal to a band's `lower` bound counts as "inside" the band for the sufficiency check
  (step 5 above) — correct for a strict "above X" comparison, wrong for an inclusive "within X to
  Y" one; this makes `hr_department_aggregation_001`/`002` and `hr_salary_analysis_001`/`002`
  indeterminate for a reason `corpus/hr/v1/SCHEMA.md` does not document as genuinely ambiguous
  (only `_003` of each family is documented as such) — 16 category-level rows (4 cases × B1–B4),
  verified by re-scoring. (b) `_reference_values`'s per-token regex scans text outside detected
  spans with no awareness of what kind of value it came from (it is category-blind), and can
  apply one category's reference figure as a candidate for another category's band; latent for
  Gate 7 authoring, not currently causing an incorrect score in either registered corpus. (c) no
  utility-side check that a numeric GENERALIZE actually coarsened the value by at least
  `MIN_NUMERIC_BAND_WIDTH` — the utility scorer trusts the generator's own width invariant rather
  than re-verifying it. This needs its own versioned methodological decision before the Gate 8
  batch. **Owner decision: resolved by option 1, before Gate 7** — a new protocol version
  `post-pilot-v4` with structured category/operator/value oracle references, replacing
  free-text reference extraction for evaluation purposes only (never reaching the
  treatment/provider payload). `corpus/hr/v1` and `corpus/contracts/v1` and their historical
  results stay intact under this decision. See `docs/milestone-3-current-plan.md`'s "Issue #87
  (reviewer's 'Issue #1') — methodological ordering decision" for the full analysis and the
  owner's decision; not implemented by this ticket.
- **[Issue #88](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/88) —
  `NumericBandStrategy` misparses Brazilian-formatted amounts.** `transformations/
  generalization.py`'s `_parse_amount` (~lines 58–66) reads `R$ 1.275.000,00` as `1.275` (the
  first `.` is treated as a decimal point) and `R$ 125.000,00` as `125.0`, producing a wrong band
  for any real-world or demo input in that format. This is a *treatment*-behavior change, not a
  scoring one, so it needs its own versioned decision. Both registered corpora use the
  dotted-decimal format exclusively (`R$ <digits>.<2 digits>`), so no recorded experiment result
  is affected by this defect. **Owner decision: moved before Gate 7** — a v3-conformant-only
  corpus (this document's own strict oracle grammar, unchanged by this decision) would let this
  parser defect dictate the corpus format rather than the other way around; see
  `docs/milestone-3-current-plan.md`, same section, for the full rationale and the narrow
  condition under which #88 could still be declared out of scope.

**Noted, not filed as an issue:** `contracts_value_audit_002`'s task asks the provider to give
"the specific contract value figure" while the oracle accepts `GENERALIZE` as a conformant
action for that span — the task's own wording is more specific than what the frozen oracle
requires. `corpus/contracts/v1` is a frozen pilot corpus (v1 §1's freeze-before-inspection rule),
so this wording is recorded here as an observation rather than corrected.

## 9. Historical comparability

**Both registered corpora are fully comparable between v2 and v3 — zero rows change.**
Re-verified by re-executing every case in `corpus/hr/v1` (65 rows: 13 cases × 5 treatments) and
`corpus/contracts/v1` (60 rows: 12 cases × 5 treatments) through `FakeProvider` and re-scoring
under both the v2 (pre-fix) and v3 (this document's) rules, following the same
re-execute/re-score/compare method v2 §4 used for the Gate 6 date-rule impact:

- **HR v1: 48/48 numeric GENERALIZE spans (`salary`) across every treatment and case contain
  their own oracle value** under `NumericBandStrategy`'s own half-open band contract — the
  generator has never produced a band it does not itself agree contains the value it generalized,
  which is exactly what §7's provenance point establishes structurally, and this count confirms
  it holds for every actual case in the corpus.
- **Contracts v1: 37/37 numeric GENERALIZE spans (`contract_value`, `penalty_amount`) likewise
  all contain their own oracle value.**
- No numeric-dependent case in either corpus has a required numeric category whose GENERALIZE
  span lacks a matched reference where the pre-v3 rule's outcome depended on that absence (i.e.
  no case flips from `answerable` under the old vacuous-`all([])` behavior to `indeterminate`
  under the new explicit `no_reference` outcome) — every case in this position already stated at
  least one reference figure.
- **Net result: 0 of 125 category-level numeric-GENERALIZE rows change outcome or reason at the
  category level, at the case-`overall` level, or in the B3→B4 pairwise comparison
  (`aggregation.summarize_b3_to_b4`).** This is expected, not merely convenient: §7 establishes
  that the generator has satisfied this fidelity rule since commit `5a0cde3`, before either
  corpus existed, so a defect the fix could have caught was never actually present in a committed
  run — the defect was in the *scorer's* willingness to credit a hypothetically wrong band, which
  neither corpus's committed run ever exercised.
- `corpus/hr/v1` and `corpus/contracts/v1` both stay `pilot_development` regardless of this
  change — v1 §1's rule that a corpus whose results were inspected during development can never
  become `held_out_confirmatory` is untouched by a scoring fix that changes zero rows.

## 10. Test coverage mapping

`tests/test_experiments_scoring_numeric_band_utility.py` is the primary suite for this rule,
structured to mirror the date-aware rule's own test file
(`tests/test_experiments_scoring_date_utility.py`). Every minimal case named in this document
maps to a specific test:

| Case in this document | Test |
| --- | --- |
| Correct band, sufficient reference (baseline) | `test_contains_original_and_sufficient_reference_is_decidable`, `test_correct_band_with_reference_outside_it_is_decidable` |
| Correct band, reference inside it (sufficiency-only ambiguity, §2's `hr_salary_analysis_003` illustration) | `test_correct_band_with_reference_inside_it_is_ambiguous`; regression: `tests/test_experiments_hr_salary_analysis_003_regression.py` |
| Band excludes the original (fidelity failure) | `test_band_excluding_original_is_not_answerable_regardless_of_references` |
| Central adversarial case (§1's minimal reproduction, row 1) | `test_central_adversarial_wrong_band_with_reference_outside_it_is_not_answerable` |
| Vacuous zero-reference case (§1's minimal reproduction, row 2) | `test_no_reference_and_correct_band_is_indeterminate_not_vacuously_decidable`, `test_no_reference_and_wrong_band_is_still_not_answerable` |
| Reference inside the wrong band (§1's minimal reproduction, row 3) | covered by the real-case end-to-end tests below, which inject a wrong band unconditionally regardless of reference placement |
| Exact lower/upper boundary (half-open interval) | `test_exact_lower_bound_is_contained_half_open`, `test_exact_upper_bound_is_excluded_half_open`, `test_upper_bound_value_is_contained_by_the_next_band`, `test_value_just_below_upper_bound_is_contained` |
| Inverted / degenerate band | `test_inverted_band_is_invalid`, `test_degenerate_zero_width_band_is_invalid` |
| Invalid band formats (§1's four other shapes) | `test_invalid_band_formats_are_rejected` |
| Unparseable original, including precedence over an invalid band | `test_unparseable_original_is_rejected_before_the_band_is_even_checked` |
| Real case, wrong band injected (`contracts_value_audit_002`) | `test_real_contracts_value_audit_002_with_a_wrong_band_is_not_answerable` |
| Real case, wrong band injected (`hr_salary_analysis_001`) | `test_real_hr_salary_analysis_001_with_a_wrong_band_is_not_answerable` |
| Ground truth is the oracle span value, never `Transformation.original` (§4) | `test_ground_truth_is_the_oracle_span_value_never_the_transformations_own_original` |
| Multi-span category, one wrong band among several | `test_real_hr_department_aggregation_003_one_wrong_salary_band_fails_the_category` |
| Category in neither registry (§5) | `test_synthetic_generalize_on_an_unregistered_category_fails_closed` |
| Determinism | `test_score_utility_numeric_band_rule_is_deterministic_across_repeated_calls` |
| Registry drift/coherence guards | `test_numeric_band_and_date_registries_are_disjoint`, `test_every_numeric_band_strategy_category_is_registered_for_utility_scoring`, `test_generalization_strategy_corpus_categories_equal_the_two_utility_registries_union`, `test_every_numeric_oracle_span_in_every_registered_corpus_is_self_consistent` |
| No-leak adversarial | `test_classify_generalized_band_reason_never_contains_either_value`, `test_score_utility_output_never_contains_a_distinctive_amount_or_band` |
| Closed reason set | `test_every_reason_classify_generalized_band_can_return_is_in_the_closed_set` |

Regression pins outside this file that stay green under v3, verified in the same test run: the
pre-existing `hr_salary_analysis_003` (ambiguous — sufficiency-only, §2) and
`contracts_obligation_relation_001` (decidable) pins.

## 11. Erratum: post-pilot-protocol-v2.md §3

`docs/research/post-pilot-protocol-v2.md` §3 ("Provenance / version boundary") contains two
statements that do not match the files as committed, verified against
`artifacts/experiments/hr/v1/13198a3b95bd49b88a62f591f3da1224/manifest.json` and
`artifacts/experiments/contracts/v1/954ffae9f6e143d6af45e4842f6daef9/manifest.json` directly:

1. It states both artifacts were "already committed under `RunIdentity.schema_version ==
   "t10-experiment-runner-v3"". Both manifests' `schema_version` (top-level and
   `reproducibility.schema_version`) actually read `"t10-experiment-runner-v2"`, not `-v3`.
2. It implies the HR run's manifest carries a `reproducibility.protocol_id` field. Only the
   Contracts manifest has one (`"protocol_id": "post-pilot-v1"`); the HR manifest has no
   `protocol_id` field at all — the field did not yet exist in the runner code when that run was
   produced (`scripts/run_contracts_v1_pilot.py` added it for the Contracts run specifically,
   ahead of the HR pilot's own tooling).

Per v1 §0, v2 is never edited to fix this (it is frozen, and the error is prose, not a
methodological rule or number that changed a result) — corrected here instead, since v3 is the
current document. Nothing about `RunIdentity.protocol_id`'s current behavior (added by Gate 6,
always populated on every run this codebase produces going forward) or either committed
artifact's own content is affected by this correction; it is a documentation-accuracy fix only.

## 12. Change log

- 2026-09-21 — `post-pilot-v3` frozen (Issue #85): adds the numeric-band GENERALIZE fidelity rule
  (`classify_generalized_band`, this document's §3), the category-unregistered fail-closed path
  (§5), records zero historical impact on both registered corpora, verified by re-scoring (§9),
  and corrects `post-pilot-protocol-v2.md` §3's schema-version/protocol_id erratum (§11) without
  editing that frozen document. No other methodological content changes; `post-pilot-v1` and
  `post-pilot-v2` remain the frozen historical record of what governed every run before this
  date.
