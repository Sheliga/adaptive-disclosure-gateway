---
protocol_id: post-pilot-v4
status: FROZEN
frozen_date: 2026-09-21
supersedes: post-pilot-v3
ticket: Issue #87 / M3
---

# Post-pilot confirmatory analysis protocol — v4

This document is a **delta** on `docs/research/post-pilot-protocol-v3.md`, not a rewrite. Every
section of v3 — and, through it, v2 and v1 — applies in full **except**:

- §6.1b's numeric-band GENERALIZE *sufficiency* step (the reference comparison, step 5 of
  `classify_generalized_band`), which for an **opted-in** (schema-v3) case is now driven by the
  oracle's own structured `utility_references` instead of free-text extraction from
  `input.text`. Fidelity (steps 1–3) is completely unaffected and stays byte-for-byte identical;
- provenance (v1 §13, carried by v2 §3, v3 §11 erratum): `RunIdentity.protocol_id` and the
  manifest-level `protocol_id` field already exist; only the value they carry moves forward to
  `post-pilot-v4`, and the manifest's `protocol_id` is now derived from the rows it actually
  contains rather than independently resolved (§6 below).

v3 itself is never edited: its own front matter, `frozen_date: 2026-09-21`, and every
methodological rule it states remain exactly as frozen. v2 and v1 remain untouched beneath it.
Where this document is silent, v3 governs (and, transitively, v2 and v1).

## 0. Versioning

This is the third exercise of v1 §1/§11's own change procedure (after Gate 6 / `post-pilot-v2`
and Issue #85 / `post-pilot-v3`): Issue #87, filed alongside `post-pilot-v3` itself (its §8,
finding (a)/(b)), is resolved here by option 1 — a new protocol version with structured
category/operator/value oracle references. `protocol_id: post-pilot-v4` is registered in
`src/adaptive_disclosure_gateway/experiments/post_pilot_protocol.py` (`FROZEN_PROTOCOL_IDS`, now
containing `post-pilot-v1` through `post-pilot-v4`; `CURRENT_PROTOCOL_ID` now `post-pilot-v4`).
`tests/test_post_pilot_protocol.py` pins that the four can never silently drift apart, for every
document independently.

**Semantic change: yes.** Replacing free-text reference extraction with a structured oracle
schema for the sufficiency step is a classification-rule change under v1 §0's own test, and it
changes which rows a numeric-dependent case can resolve to `answerable` for a case that opts in
(§9 below) — exactly the kind of change v1 §0 requires a new protocol version for, never a patch
to v3.

**Not every frozen protocol id is scorable going forward.** `SCORABLE_PROTOCOL_IDS` —
`{post-pilot-v3, post-pilot-v4}` — is now a real, separate registry from `FROZEN_PROTOCOL_IDS`:
v1 and v2 remain frozen historical record, but this codebase's numeric-band scorer was replaced
*in place* by `post-pilot-v3`'s `classify_generalized_band`, so nothing implementing the v1/v2-era
rule remains in the source tree to dispatch to. `validate_scorable_protocol_id` checks both that
an id is frozen at all and that it is still executable; asking to score a fresh run under v1/v2
now raises `UnsupportedScoringProtocolError`, distinct from `UnknownProtocolIdError` for an id
that was never registered.

## 1. Rationale: two defects in `_reference_values`, and why a text-coupled fix was rejected

`post-pilot-v3` froze fidelity-first scoring but left step 5 (sufficiency) exactly as the
pre-v3 rule computed it: `_reference_values` scans `input.text` for any numeric token outside a
detected span's own offsets and treats every one it finds as a candidate reference for *every*
numeric category in the case. `post-pilot-v3` §8 (filed as this ticket, Issue #87) named two
concrete defects in that mechanism:

**(a) Lower-bound equality is ambiguous for a strict comparison but decidable for a non-strict
one, and the old rule could not tell them apart.** `_reference_values` returns a bare `float`;
`classify_generalized_band`'s step 5 asks only whether that float falls inside or outside the
band, with no way to know whether the case's real relational question was "strictly greater
than," "at least," or something else. For a reference sitting exactly on a band's lower bound,
those questions have different answers (§4 below) — the old rule silently picked one answer for
every case, without the information to tell whether it was the right one.

### Minimal reproduction

`hr_department_aggregation_001` states a department floor of "at least R$ 5,000.00" and
`hr_salary_analysis_001`/`002` states an analogous floor; the generated salary band for these
cases is `[5000, 10000)`. The stated reference figure is `5000.0` — exactly the band's own lower
bound.

| Reference reading | Old rule's outcome | Correct outcome |
| --- | --- | --- |
| `x >= 5000.00` (what "at least" actually means) | `indeterminate` / `generalized_band_ambiguous` (the old rule treats `5000.0` as inside `[5000, 10000)`, so it cannot resolve the comparison) | `answerable` — every salary in `[5000, 10000)` already satisfies `x >= 5000.00` |
| `x > 5000.00` (a stricter reading the old rule implicitly assumed) | `indeterminate` / `generalized_band_ambiguous` | `indeterminate` — some values in the band equal `5000.00` (fails `x > 5000.00`), others exceed it (passes), so this reading genuinely is undecidable |

The old rule produced the *same* `indeterminate` outcome for both readings, because it had no
operator to distinguish them. Sixteen category-level rows across four cases
(`hr_department_aggregation_001`/`002`, `hr_salary_analysis_001`/`002`, × B1–B4) sit at exactly
this boundary (§9 below) — none of them is the *documented* ambiguous case
(`_003` of each family, which is a genuine sufficiency failure, unaffected by this fix).

**(b) The extraction is category-blind.** `_reference_values` has no notion of which category a
number in the text belongs to; a reference figure intended for `salary` could equally be applied
as a candidate reference for `contract_value` in a case that depends on both, purely because
both numbers survive the same "outside every detected span" filter. This is latent in both
registered corpora today (no committed row is actually miscategorized by it — v3 §9 confirms
zero rows change), but it is a real defect waiting for a corpus author to trip over, and it gets
worse, not better, as Gate 7 adds a new corpus.

### Option 2 (rejected): patch `_reference_values` to also infer an operator from surrounding text

A tempting narrower fix keeps free-text extraction but adds a small NLP-ish heuristic: look for
words like "at least," "more than," "up to" near a number and infer an operator from them.
**Rejected** for three reasons:

1. **It re-couples the oracle to `input.text`'s exact surface phrasing** — the same coupling
   `post-pilot-v3` §6 already names as a known limitation of the mechanism, not something to
   double down on. A phrasing change in the case text (paraphrasing "at least" as "no less than")
   would silently change what the oracle means, with no test able to catch the drift because
   nothing declares the intended operator independently of the prose.
2. **It does not fix defect (b).** A phrase-adjacency heuristic is, if anything, *more*
   category-blind than a pure number scan: "at least R$ 5,000.00" near a `salary` figure and a
   `contract_value` figure in the same sentence gives the heuristic no more information about
   which category the phrase modifies than the current rule has.
3. **It could not be tested to the standard this codebase requires.** A regex/heuristic operator
   inference is exactly the kind of mechanism `tests/test_no_sensitive_value_in_raises.py`'s
   sibling architectural tests exist to keep out of the evaluation oracle — untestable in the
   adversarial sense §5/§7 below require, because its correctness depends on prose it does not
   control.

**Decision: option 1 (chosen) — structured category/operator/value oracle references,
replacing free-text extraction for evaluation purposes only.** The oracle states what it means
directly, as data, rather than the scorer inferring it from prose. This is the same shift `T09`
already made for every other oracle field (`expected_actions`, `answer_depends_on_categories`,
`obligation_relations`): ground truth is authored data, not inferred from the case's own surface
text.

## 2. What changes and what does not

**Unaffected, byte-for-byte:**

- steps 1–3 (fidelity) of the numeric-band GENERALIZE rule — extracted into a shared
  `_check_band_fidelity` helper so both the v3 and v4 sufficiency paths call the exact same
  fidelity check, but its logic is unchanged;
- `classify_generalized_band` itself — the frozen v3 function, same signature, same behavior,
  still the scorer for any case scored under `protocol_id="post-pilot-v3"`;
- the date-aware rule (`classify_generalized_date`), the category-unregistered fail-closed path,
  and every other utility-scoring rule not discussed here;
- `corpus/hr/v1` and `corpus/contracts/v1` — neither frozen corpus is edited; both stay scorable
  only under `post-pilot-v3` (§6 below), exactly as v3 left them.

**New:**

- `CaseOracle.utility_references: list[NumericUtilityReference] | None` (§3);
- `classify_generalized_band_against_references`, a new function (not a modified
  `classify_generalized_band`) implementing the same fidelity-first shape with a structured
  sufficiency step (§4);
- protocol dispatch in `score_utility` and the runner, so a caller states which protocol id it
  wants and gets the matching scorer (§6).

## 3. The oracle schema

```python
NUMERIC_REFERENCE_CATEGORIES: frozenset[str] = frozenset(
    {"salary", "contract_value", "penalty_amount"}
)


class ReferenceOperator(StrEnum):
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"


class NumericUtilityReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    category: CorpusCategory
    operator: ReferenceOperator
    value: str = Field(pattern=r"^(0|[1-9][0-9]*)\.[0-9]{2}$")
```

`NUMERIC_REFERENCE_CATEGORIES` (`corpus/models.py`) is pinned equal to
`experiments.scoring.utility.NUMERIC_BAND_UTILITY_CATEGORIES` by a drift test — the two sets are
defined independently (the corpus package must never import `experiments`; see
`tests/test_corpus_oracle_isolation.py`) but must never diverge.

**Long operator names, not symbols.** `greater_than`/`greater_than_or_equal`/`less_than`/
`less_than_or_equal` rather than `gt`/`ge`/`lt`/`le` or mathematical symbols — a case file is
read by a human author, and a mistyped symbol (`=>` for `>=`) is a schema violation waiting to
happen that a long, unambiguous name avoids entirely.

**Value grammar: canonical decimal, ASCII digits only, no currency, no text-grounding.**
`^(0|[1-9][0-9]*)\.[0-9]{2}$` — explicit `[0-9]`, never `\d` (which also matches non-ASCII
Unicode digit characters; see §11's note on the *separate*, unfixed `\d` finding in the v3
fidelity regexes). No `R$` prefix, no thousands separator, no sign: this is the scorer's own
canonical amount, independent of whatever surface format `input.text` happens to use for the same
figure. **There is deliberately no check that a reference's value textually appears anywhere in
`input.text`** — no "grounding" requirement. Two reasons:

1. It would force every case's prose into this scorer's own canonical surface format (`R$
   <digits>.<2 digits>`) merely to satisfy a structural check unrelated to what the reference
   means, re-introducing exactly the lexical coupling option 1 exists to remove.
2. It directly conflicts with Issue #88 (Brazilian-formatted amount parsing): a case author must
   remain free to write `R$ 5.000,00` in the prose while the oracle states `5000.00` as the
   canonical reference value, with no requirement that the two strings match syntactically.

**No load-time coverage requirement.** An opted-in case (a list, however empty) is not required
to state a reference for every numeric category it depends on. **Rejected as an authoring
constraint**: a real task can legitimately depend on a numeric category without there being any
stated threshold to test decidability against at all — forcing every such case to invent a
reference merely to satisfy a coverage check would fabricate oracle data that does not correspond
to anything the task actually asks. An uncovered category instead scores
`indeterminate`/`generalized_band_no_reference` at score time (§4 step 4) — the same outcome a
covered-but-empty-list case already produced under v3's own zero-reference behavior, so this is
not a new outcome, only a new way to reach it deliberately rather than by omission.

**Validation** (`CaseOracle` model validators, `corpus/oracle.py`):

- a blocked case (`expected_block_request: true`) must have `utility_references` absent or empty
  — nothing is ever disclosed for such a case, so no reference could decide anything about it;
- every reference's `category` must be one of `NUMERIC_REFERENCE_CATEGORIES` (checked on
  `NumericUtilityReference` itself) and must be present in the case's own
  `answer_depends_on_categories` (checked on `CaseOracle`) — a reference for a category the case
  does not even depend on is a corpus-authoring defect, not something to score;
- no duplicate `(category, operator, value)` triple within one case.

All three failure modes raise `pydantic.ValidationError`/`CorpusLoadError` naming only the field
path, category and error type — never the value (CLAUDE.md's no-leak invariant; `loader.py`'s
own `_describe_validation_errors` already reads only `loc`/`type`, never `msg`/`input`).

`corpus/models.CORPUS_SCHEMA_VERSION` moves to `"corpus-case-schema-v3"` — purely additive, like
the v1→v2 move for `obligation_relations`: `utility_references` defaults to `None` (absent), so
every `corpus/hr/v1` and `corpus/contracts/v1` case file loads byte-for-byte unchanged. `None`
means *legacy* (a case that never states the field at all); a list — even an empty one — means
*opted in*. The distinction only matters for protocol dispatch (§6): a legacy case that depends
on a numeric category is refused outright under `post-pilot-v4`, while an opted-in case with an
empty or partial reference set is scored, deliberately, as merely uninformative for the
categories it did not cover.

`loader.py`'s existing domain-consistency check (`_check_domain_consistency`) is extended to
cover `("oracle.utility_references", category)` alongside every other oracle field it already
checks — a reference naming a category real in the schema but foreign to the case's own
`input.domain` is rejected exactly like every other cross-domain leak this function already
guards against.

## 4. The formal sufficiency rule

A generalized band is a half-open interval `[L, U)` over the reals, with integer bounds `L < U`
(`NumericBandStrategy`'s own contract, unchanged). A reference is `(operator, r)` with `r` a
`Decimal`. The relational question a reference states is about the original value `x` (which the
scorer never sees directly once GENERALIZE has run — only the band is available): does `x
{operator} r` hold?

**Decidable iff every `x` in `[L, U)` gives the same answer to that question** — equivalently, iff
`r` never falls where the band's own values straddle the relation's boundary:

| operator | relation | decidable iff |
| --- | --- | --- |
| `greater_than` | `x > r` | `r < L or r >= U` |
| `less_than_or_equal` | `x <= r` | `r < L or r >= U` |
| `greater_than_or_equal` | `x >= r` | `r <= L or r >= U` |
| `less_than` | `x < r` | `r <= L or r >= U` |

The first two operators share a condition and the last two share a different one because of how
each relation's own boundary interacts with the band's own half-open one: for `greater_than`/
`less_than_or_equal`, `r == L` is still ambiguous, because some `x` in `[L, U)` equal `L` too
(giving `x > r` = false, `x <= r` = true) while others exceed `L` (giving the opposite pair) — a
genuine split. For `greater_than_or_equal`/`less_than`, `r == L` is already decidable, because
every `x >= L` in the half-open band uniformly satisfies `x >= r` (resp. uniformly fails `x <
r`) — there is no split at that exact boundary for these two operators.

**Worked example**, band `[500000, 550000)`:

| reference | outcome |
| --- | --- |
| `greater_than 500000.00` | ambiguous (`r == L`, straddles for a strict `>` comparison) |
| `greater_than_or_equal 500000.00` | answerable (`r == L`, but `>=` never straddles at `L`) |
| `less_than_or_equal 549999.99` | ambiguous (`549999.99` is inside `[500000, 550000)`) |
| `less_than_or_equal 550000.00` | answerable (`550000.00 >= U`) |
| `greater_than 550000.00` | answerable (`550000.00 >= U`) |
| `less_than 500000.00` | answerable (`500000.00 <= L`) |
| `less_than 550000.00` | answerable (`550000.00 >= U`) |

Note that `post-pilot-v3`'s own step 5 rule (`reference < L or reference >= U`, applied to a bare
float with no operator) is exactly the `greater_than`/`less_than_or_equal` row of this table —
`post-pilot-v4` differs from `post-pilot-v3` on the *same* band/reference figure only for the
`greater_than_or_equal`/`less_than` rows at `r == L` (§9's sixteen rows are exactly this case,
read as `greater_than_or_equal`).

**Multiple references for one category: decidable iff every one of them is individually
decidable** against the band — an atom-level AND. This is sound for any boolean combination of
threshold questions a case author might intend (a range stated as two atoms, an exact-value
question stated as `>=` and `<=` against the same figure): if any single atom is undecidable, the
combined question cannot be decided from the band alone either, regardless of how the atoms would
otherwise combine.

**No `between`/`equal` operator.** An inclusive range "between X and Y" is two atoms
(`greater_than_or_equal` X + `less_than_or_equal` Y); an exact-value question is
`greater_than_or_equal` X + `less_than_or_equal` X. A fifth composite operator would only
duplicate what two atoms already express, at the cost of a second code path to keep in sync with
the table above.

**Universal over spans, not scoped to one span instance.** A reference applies to *every*
GENERALIZE span of its own category in a case — a case with more than one span of the same
numeric category (e.g. several salaries under `hr_department_aggregation`) is judged against the
same reference set for each of them, mirroring how v3's free-text extraction was never scoped to
one span either.

## 5. Fidelity/sufficiency separation, preserved

`_check_band_fidelity(original, transformed)` is `_check_band_fidelity`'s own steps 1–3
(unscorable original, invalid/inverted/degenerate band, band excludes original), extracted
verbatim from `post-pilot-v3`'s `classify_generalized_band` so both the frozen v3 function and the
new `classify_generalized_band_against_references` share the exact same fidelity check rather
than risking the two drifting apart under future maintenance. Both functions then apply their own
sufficiency step (v3: free-text float comparison; v4: the structured operator table above) only
once fidelity has already been confirmed — a wrong band is `not_answerable` under both protocol
ids, unconditionally, regardless of what references exist.

## 6. Protocol dispatch and legacy compatibility

`post_pilot_protocol.py`:

- `FROZEN_PROTOCOL_IDS` gains `"post-pilot-v4"`; `CURRENT_PROTOCOL_ID` is now `"post-pilot-v4"`;
- `SCORABLE_PROTOCOL_IDS = frozenset({"post-pilot-v3", "post-pilot-v4"})` (§0);
- `UnsupportedScoringProtocolError(ValueError)`, raised by the new
  `validate_scorable_protocol_id()` for a frozen-but-unscorable or unregistered id (the latter via
  `validate_protocol_id`, called first).

Threading: `execute_case`, `run_case_for_treatment` and `run_pilot` all gain a keyword-only
`protocol_id: str | None = None`, resolved **at call time** (never at import time, so a test that
monkeypatches `CURRENT_PROTOCOL_ID` still observes the effect — the existing Gate 6 regression
pin already depends on this) to `CURRENT_PROTOCOL_ID` when left `None`, then validated as both
frozen and scorable. `score_case` passes `case_execution.identity.protocol_id` down to
`score_utility` — a case execution is scored under the exact protocol id it was stamped with,
never a value `score_case` could independently drift from it. `score_utility` itself takes
`protocol_id` as a required keyword-only argument with no default — a caller must always say
which protocol it wants.

`run_pilot` additionally calls `check_corpus_protocol_compatibility(cases, protocol_id)`
(`experiments/scoring/utility.py`) immediately after loading a corpus directory and **before any
treatment or provider call** — an incompatible corpus/protocol pairing costs zero provider calls,
not a partial run that fails midway through.

**Compatibility matrix** (per case, treatment-independent — a property of the oracle and the
protocol id, not of what any one treatment happens to produce):

- **`post-pilot-v4`**: a case whose `oracle.utility_references is None` (legacy) *and* whose
  `answer_depends_on_categories` includes a registered numeric category →
  `MissingUtilityReferencesError`. A legacy corpus is refused under v4 by design — `corpus/hr/v1`
  and `corpus/contracts/v1` are never edited to add the field, so they simply cannot be scored
  under `post-pilot-v4` and must be scored under `post-pilot-v3` instead (§9). A case that has
  opted in (a list, however empty) is compatible regardless of whether every numeric category it
  depends on actually has a reference — an uncovered category scores
  `indeterminate`/`generalized_band_no_reference` at score time (§3's "no load-time coverage
  requirement").
- **`post-pilot-v3`**: a case with a non-empty `oracle.utility_references` →
  `StructuredReferencesRequireV4Error` — v3's scorer has no mechanism to honor declared
  operator/value semantics, so scoring such a case under v3 would silently ignore what the case
  author actually stated rather than apply it.
- **any other id**: `UnsupportedScoringProtocolError`.
- a case with no numeric-category dependency at all is compatible with both v3 and v4
  unconditionally.

`scripts/run_hr_v1_pilot.py` and `scripts/run_contracts_v1_pilot.py` pin
`protocol_id="post-pilot-v3"` explicitly and record it in their own reproducibility block — both
corpora stay legacy/non-opted-in and their historical results remain scored, and reproducible,
under `post-pilot-v3` going forward, unaffected by `CURRENT_PROTOCOL_ID` moving on.

**No-regex-fallback guarantee.** `_reference_values` is renamed `_legacy_v3_reference_values` and
is reachable only from the `post-pilot-v3` branch of `score_utility` (pinned by an AST test); the
`post-pilot-v4` path never calls it and never reads `case_input.text` for reference purposes at
all — a behavioral test monkeypatches the legacy function to raise and confirms v4 scoring still
succeeds.

`artifacts.write_pilot_artifacts`'s manifest `protocol_id` is now derived from the
`RunIdentity.protocol_id` values the passed-in `CaseResult` rows actually carry (raising
`MixedProtocolIdsError` if they disagree) rather than independently resolved from
`CURRENT_PROTOCOL_ID` — a run explicitly scored under an older, still-scorable id must have its
manifest agree with what its own rows carry, never silently claim whatever happens to be current.

`RunIdentity`'s shape is unchanged (`protocol_id: str`, populated exactly as before); no
`SCHEMA_VERSION` bump.

## 7. No-leak

Every no-leak guarantee `post-pilot-v3` already established for `CategoryUtility`/`UtilityScore`
(reason strings are fixed constants, never interpolate a value; `NUMERIC_BAND_UTILITY_REASONS`
stays the same six values) is unaffected — `classify_generalized_band_against_references` returns
exactly the same reason vocabulary as `classify_generalized_band`. New surface area this ticket
adds:

- `NumericUtilityReference`/`ReferenceOperator`/`utility_references` are reachable, by AST
  allowlist, only from `corpus/{models,oracle,loader,__init__}.py`,
  `experiments/scoring/utility.py`, and the runner code that calls
  `check_corpus_protocol_compatibility` — never from a treatment, the detector, a policy, a
  provider, or `CorpusCaseInput`/`DisclosureRequest`;
- `CorpusCaseInput` has no field containing "reference" or "threshold"; `DisclosureRequest`'s
  field set stays exactly `{text, task, context}` — a structured reference has no path into what a
  treatment or provider ever sees;
- a marker value planted in a v4 fixture case's `utility_references` (not present anywhere in
  `input.text`) is run through every treatment via the real runner and confirmed absent from the
  external payload, the provider payload/task, the task analyzer's input, `repr()` of the audit
  record, `repr()`/`json.dumps()` of the safe-serialized result, and captured span attributes;
- treatment-side output (decisions, actions, generalized band values, the payload once PSEUDO
  tokens are normalized) is identical whether `utility_references` is `None`, an empty list, or
  populated — the field influences only post-execution scoring, never what a treatment produces;
- loader validation errors for an invalid reference never contain the offending value and always
  break the exception chain (`raise ... from None`) where a lower-level parser might otherwise
  echo it.

`tests/test_corpus_utility_references.py` and
`tests/test_experiments_scoring_utility_references_v4.py` are the adversarial suites pinning all
of the above.

## 8. Item (c) — deferred, not resolved here

`post-pilot-v3` §8 also named a third finding: no utility-side check that a numeric GENERALIZE
actually coarsened the value by at least `MIN_NUMERIC_BAND_WIDTH` — the utility scorer trusts the
generator's own width invariant rather than re-verifying it. **This is moved to its own issue,
[Issue #90](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/90), filed alongside
this document, and is explicitly not resolved by `post-pilot-v4`.** On reflection
this is not a utility-scoring gap at all: utility sufficiency asks whether the disclosed band lets
the task's question be answered, and a *narrower* band that still resolves the question is, if
anything, *more* useful, not less — penalizing width in the utility metric would double-count a
privacy property that belongs to a different metric entirely. The real, still-open risk is
under-reported *exposure*: `scoring/exposure.py` ranks a numeric GENERALIZE by its action label
alone, with no check that the band it actually produced respects `MIN_NUMERIC_BAND_WIDTH` — a
band narrower than the frozen minimum would still be counted as ordinary GENERALIZE exposure, not
flagged as a tighter, more identifying disclosure than GENERALIZE is supposed to allow. The new
issue is scoped to `exposure.py`, not `utility.py`, and does not affect Gate 7 corpus authoring
(a Gate 7 case author states thresholds and expected answers exactly as this document already
specifies, independent of how exposure ranks a band's width).

## 9. Historical comparability

**Neither registered corpus can be scored under `post-pilot-v4` at all** — both are legacy
(`utility_references` absent from every case file) and both have at least one case depending on a
registered numeric category, so `check_corpus_protocol_compatibility`/`score_utility` refuse them
outright under v4 (§6's compatibility matrix, first bullet). This is by design, not an oversight:
neither frozen corpus is edited to add the field, and both remain scorable exactly as before under
`protocol_id="post-pilot-v3"` (`scripts/run_hr_v1_pilot.py`/`run_contracts_v1_pilot.py` pin this
explicitly). **No committed artifact changes under this ticket** — every `artifacts/experiments/**`
file already on disk was produced under `post-pilot-v1`/`-v2`/`-v3` and remains valid under
whichever of those ids it already names.

**Analytical historical-impact estimate (rule written first; not committed corpus data).** To
understand what `post-pilot-v4`'s corrected sufficiency rule *would* change if the two corpora
could be re-annotated with structured references, every case × treatment of `corpus/hr/v1` and
`corpus/contracts/v1` was re-executed via `FakeProvider` and scored under v3, then re-scored with
the v4 classifier fed a **throwaway, uncommitted fixture** mapping each numeric-dependent case's
own prose threshold to a structured reference (operator read from the expected-answer's own
relational phrasing — never tuned to produce a particular result):

| Case | Reference(s) used |
| --- | --- |
| `hr_salary_analysis_001` | `salary` `greater_than_or_equal 5000.00`, `less_than_or_equal 10000.00` |
| `hr_salary_analysis_002` | `salary` `greater_than_or_equal 10000.00`, `less_than_or_equal 15000.00` |
| `hr_salary_analysis_003` | `salary` `greater_than 1518.00` |
| `hr_department_aggregation_001` | `salary` `greater_than_or_equal 5000.00`, `less_than_or_equal 10000.00` |
| `hr_department_aggregation_002` | `salary` `greater_than_or_equal 0.00`, `less_than_or_equal 10000.00` |
| `hr_department_aggregation_003` | `salary` `greater_than_or_equal 5000.00`, `less_than_or_equal 16000.00` |
| `contracts_obligation_relation_001` | `contract_value` `less_than 700000.00` |
| `contracts_penalty_review_001` | `penalty_amount` `less_than_or_equal 12500.00` |
| `contracts_penalty_review_002` | `penalty_amount` `greater_than 20000.00` |
| `contracts_summary_001` | `contract_value` `less_than 3000000.00` |
| `contracts_summary_002` | `contract_value` `greater_than 100000.00` |
| `contracts_value_audit_001` | `contract_value` `greater_than_or_equal 1275000.00`, `less_than_or_equal 1275000.00` |
| `contracts_value_audit_002` | `contract_value` `greater_than 500000.00` |

**Result: 65 numeric-category rows checked (13 numeric-dependent cases × 5 treatments); 16
rows change from `ambiguous` to `decidable`** —
`hr_department_aggregation_001`/`002` and `hr_salary_analysis_001`/`002`, each × B1–B4 (B0 is
excluded from both the v3 and v4 rules identically, since B0 — Direct never applies GENERALIZE at
all). Every one of these 16 rows flips its case-level `overall` utility outcome from
`indeterminate` to `answerable` for that treatment; **Contracts: 0 rows change.** The documented,
genuinely ambiguous cases (`hr_department_aggregation_003`, `hr_salary_analysis_003`) are
preserved exactly as `indeterminate` — their references read as `greater_than_or_equal
5000.00`/`less_than_or_equal 16000.00` (falls inside the band) and `greater_than 1518.00`
(genuinely straddles the band for a strict comparison), neither of which is the `r == L` boundary
case this ticket's fix affects. This finding is robust to the alternative reading of each
reference as the other operator sharing its outcome row (e.g. reading a "minimum" floor as
`greater_than` instead of `greater_than_or_equal` reproduces the old, unresolved `ambiguous`
result for exactly the four affected cases and no others — confirming the fix's effect is
isolated to the operator distinction, not an artifact of a particular reading). Pairwise
(`aggregation.summarize_b3_to_b4` and the adjacent B0→B1/B1→B2/B2→B3/B3→B4 comparisons): only the
B0→B1 comparison changes for these four cases (B0 was already `answerable` via direct disclosure;
B1 moves from `indeterminate` to `answerable`), since B1 is the first treatment where GENERALIZE
is actually applied to salary.

## 10. Anti-tuning statement

This satisfies v1 §11's four-step change procedure exactly as v2/v3 did: (1) recorded here and in
`docs/implementation-status.md`; (2) neither corpus this rule could reach stays scorable under it
at all (§9) — `pilot_development` classification is unaffected either way; (3) versioned as
`post-pilot-v4`, this document; (4) no new held-out round is created by this ticket — that remains
Gate 7, not this one.

**This fix can only ever *add* credit relative to v3 on the affected rows, and this is not
tuning.** Unlike `post-pilot-v3`'s fix (which was strictly one-directional the other way — it
could only *remove* previously-unwarranted credit), this one *adds* credit for the 16 rows in
§9 (`ambiguous` → `decidable`). This is not a violation of the anti-tuning discipline for three
reasons: first, the defect and its fix (structured operators distinguishing `>=`/`<` from `>`/`<=`
at a shared boundary) were named in `post-pilot-v3` §8 — filed as Issue #87 — **before** the
historical-impact numbers in §9 above were ever computed; the fix's shape was fully decided
(§1's rejection of option 2, §2's "what changes and what does not") before any row-level number
existed to tune against. Second, neither registered corpus can actually be scored under this
protocol at all (§9) — the "impact" in §9 is an analytical estimate from a throwaway fixture,
explicitly not committed corpus data, so no real experimental result is retroactively improved by
this ticket; it demonstrates what the fix *would* do to a case, not what it *did* do to one.
Third, the fix corrects a **structurally missing distinction** (no operator existed to express
"at least" vs. "greater than" at all under v3), not a threshold, a weight or a comparison cell
tuned toward a particular treatment's results — it is closer in kind to `post-pilot-v2`'s
date-vs-numeric type-error fix than to any adjustment of an existing numeric rule's parameters.

## 11. Limitations

- **A reference's value has no requirement to appear anywhere in `input.text`.** This is
  deliberate (§3) but means a Gate 7 case author must take independent care that a stated
  reference actually reflects what the case's prose says, since no structural check enforces
  agreement between them.
- **No aggregate or disjunctive semantics.** A case cannot state "the answer is decidable if
  either of these two thresholds resolves it" — every reference for a category is combined by AND
  (§4), never OR. A future task needing disjunctive semantics would require its own protocol
  version.
- **Contradictory reference sets are under-credited, never over-credited.** If a case somehow
  states two references that cannot both be satisfied by any real value (an authoring error this
  ticket does not attempt to detect), the AND-combination can only make the case harder to
  resolve as `answerable`, never easier — consistent with the rule's own fail-closed posture.
- **`#88` interaction.** `NumericBandStrategy`'s own Brazilian-format amount misparse (Issue #88)
  is a treatment-behavior defect, not a scoring one, and is unaffected by this ticket; a
  structured reference's canonical `value` is independent of whatever surface format the
  generator itself parsed the original amount from.
- **The v3 fidelity regexes' `\d` finding is unfixed, unreachable, and recorded, not fixed,
  here.** `_parse_strict_original_amount`/`_parse_band` (both frozen v3 code, `experiments/
  scoring/utility.py`) use `\d`, which matches non-ASCII Unicode decimal digit characters as well
  as ASCII `0`–`9` — e.g. `R$ ١٢.00` (Eastern Arabic-Indic digits) would parse as `12.00` under
  Python's `re` module's default (non-`ASCII`) flag. Neither registered corpus nor the case
  generator ever produces such a string, so this is unreachable today; filed as
  [Issue #91](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/91) rather than fixed
  here, since fixing it touches frozen v3 code this ticket commits to leaving byte-for-byte
  unchanged. The new `NumericUtilityReference.value` grammar (§3) is written correctly from the
  start (`[0-9]`, never `\d`), so this finding does not recur in any code this ticket adds.

## 12. Test coverage mapping

| Area | Test file |
| --- | --- |
| Oracle schema (`NumericUtilityReference`, validators, drift guards) | `tests/test_corpus_utility_references.py` |
| Formal sufficiency rule, dispatch, legacy/opted-in behavior | `tests/test_experiments_scoring_utility_references_v4.py` |
| Protocol registry (`FROZEN_PROTOCOL_IDS`, `SCORABLE_PROTOCOL_IDS`, document drift) | `tests/test_post_pilot_protocol.py` |
| No-leak marker run, AST allowlist | `tests/test_corpus_utility_references.py` |
| Fidelity unchanged (v3 pin) | `tests/test_experiments_scoring_numeric_band_utility.py` (unchanged assertions; `protocol_id="post-pilot-v3"` call args only) |

## 13. Change log

- 2026-09-21 — `post-pilot-v4` frozen (Issue #87): adds `CaseOracle.utility_references`
  (structured category/operator/value references, schema-v3), a new
  `classify_generalized_band_against_references` sufficiency rule sharing fidelity with the frozen
  v3 rule, protocol dispatch/legacy compatibility (`SCORABLE_PROTOCOL_IDS`,
  `check_corpus_protocol_compatibility`, `MissingUtilityReferencesError`), moves item (c) to
  [Issue #90](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/90), records an
  analytical (non-committed) historical-impact estimate (§9) -- independently re-verified against
  the live implementation: 65 numeric category-level rows, 16 change from `ambiguous` to
  `decidable` (`hr_department_aggregation_001`/`002`, `hr_salary_analysis_001`/`002` × B1–B4),
  Contracts 0 -- and files
  [Issue #91](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/91) for the
  pre-existing, unreachable `\d` finding in the v3 fidelity regexes (§11).
  No other methodological content changes; `post-pilot-v1`, `post-pilot-v2` and `post-pilot-v3`
  remain the frozen historical record of what governed every run before this date.
