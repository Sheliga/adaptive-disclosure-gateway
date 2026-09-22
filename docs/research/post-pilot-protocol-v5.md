---
protocol_id: post-pilot-v5
status: FROZEN
frozen_date: 2026-09-21
supersedes: post-pilot-v4
ticket: Issue #93 (#88, #91)
---

# Post-pilot confirmatory analysis protocol — v5

This document is a **delta** on `docs/research/post-pilot-protocol-v4.md`, not a rewrite. Every
section of v4 — and, through it, v3, v2 and v1 — applies in full **except**:

- the numeric amount format contract used by the treatment (`transformations/generalization.py`)
  and by the fidelity scorer's original-amount grammar, which is replaced end-to-end by a single,
  closed, versioned amount grammar (`NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"`), resolving
  Issue #88 and Issue #91 within one methodological boundary (§2);
- a new, v5-only pre-run check over the whole corpus, including blocked cases, that refuses an
  incoherent amount format before any provider call (§6).

Date utility semantics do **not** change in v5. The `deadline`/`birth_date` treatment path and
`classify_generalized_date` remain the v4 behavior; the separate date treatment/scorer asymmetry
found during review is tracked in Issue #96 and intentionally left outside Issue #93 / PR #97.

v4 itself is never edited: its own front matter, `frozen_date: 2026-09-21`, and every
methodological rule it states remain exactly as frozen. v3, v2 and v1 remain untouched beneath
it. Where this document is silent, v4 governs (and, transitively, v3, v2 and v1).

## 0. Versioning

This is the fourth exercise of v1 §1/§11's own change procedure (after Gate 6 / `post-pilot-v2`,
Issue #85 / `post-pilot-v3`, and Issue #87 / `post-pilot-v4`). Issue #93 is the pre-Gate-7
checkpoint the project owner required before a confirmatory Contracts corpus may be authored:
Issue #88 (found during the Issue #85 audit) showed that the treatment's own amount parser
misreads a common, realistic surface format; Issue #87's own §11 recorded, but explicitly did
not fix, a related ASCII-digit defect in the frozen v3 fidelity regexes (Issue #91). Fixing
either issue in isolation is insufficient (§1): the treatment and the scorer must agree on the
same amount format contract, or a value the treatment can legitimately generalize can still be
unscorable at evaluation time. `protocol_id: post-pilot-v5` is registered in
`src/adaptive_disclosure_gateway/experiments/post_pilot_protocol.py` (`FROZEN_PROTOCOL_IDS`, now
`post-pilot-v1` through `post-pilot-v5`; `SCORABLE_PROTOCOL_IDS`, now `{v3, v4, v5}`;
`CURRENT_PROTOCOL_ID` now `post-pilot-v5`). `tests/test_post_pilot_protocol.py` pins that the
five can never silently drift apart, for every document independently.

**Semantic change: yes, on the monetary axis.** A treatment-behavior change: `NumericBandStrategy`
now accepts and correctly bands a wider set of amount surface forms than before (Brazilian,
NBSP-separated), and rejects some forms a pre-#93 free-for-all regex used to silently misparse
(trailing prose, negatives, leading zeros, cents-less amounts) — this changes what a real case
using one of those forms discloses, which per v1 §0/§11 requires its own versioned decision,
never a silent patch. The v5 fidelity amount grammar accepts a Brazilian-formatted original
where v4's frozen amount grammar would reject it as unscorable, and rejects non-ASCII digits or
trailing characters that v3/v4's frozen amount regex could silently accept. Date utility scoring
is inherited from v4 unchanged; Issue #96 owns any future date treatment/scorer change.

**Not every frozen protocol id is scorable going forward** — unchanged from v4's own statement of
this rule; v5 only adds `post-pilot-v5` to `SCORABLE_PROTOCOL_IDS`, it does not remove v3 or v4.

## 1. Rationale: why fixing only `_parse_amount` is insufficient

Issue #88 found that `NumericBandStrategy`'s original amount parser
(`_AMOUNT_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")`, `float(match.group())`) has no concept of a
thousands separator, so a Brazilian-formatted amount is misread: `R$ 125.000,00` (one hundred
twenty-five thousand) is read as `125.0`, and `R$ 1.275.000,00` is read as `1.275` — a band three
to six orders of magnitude too small, silently disclosed as if it were correct. The same
permissive regex also has no upper bound: a very long digit string overflows `float` to `inf`,
and `int(inf)` — reached via the (buggy) pre-existing band-index arithmetic — raises
`OverflowError`/`ValueError`, not the `GeneralizationError` the fail-closed pre-pass
(`decision_application.py`, `static_sanitization.py`) expects; a case that should BLOCK_REQUEST
instead crashes with an unhandled exception type.

**A narrower fix touching only `transformations/generalization.py` is not sufficient**, for the
same reason Issue #93's own filing states: `experiments/scoring/utility.py`'s v4 fidelity check
(`_parse_strict_original_amount`, `_ORIGINAL_AMOUNT_PATTERN = re.compile(r"^R\$ (\d+\.\d{2})$")`)
independently re-derives the oracle span's own value from a *different*, dotted-decimal-only
grammar — by design, so a shared-parser bug cannot make fidelity circularly agree with a wrong
treatment output. If only the treatment learned to generalize a Brazilian amount correctly, the
v4 scorer would still classify that exact same oracle value as
`generalized_band_unscorable_original` — a correctly-generalized band that can never score
`answerable`, because the *evaluation* side of the contract never learned the new format exists.
Gate 7 cannot author a confirmatory corpus against a format the treatment supports but the scorer
cannot evaluate, or vice versa: detector, oracle span, treatment and scorer must all agree on
one grammar, end to end. This document is that single, versioned, closed grammar.

## 2. The grammar

Closed, `fullmatch`-only, ASCII-digit (`[0-9]`, never `\d`), no locale guessing:

```text
AMOUNT  := "R$" SEP ( DOTTED | BRAZIL )
SEP     := exactly one of U+0020 (space) or U+00A0 (NBSP)
DOTTED  := (0|[1-9][0-9]{0,14}) "." [0-9]{2}
BRAZIL  := ( 0 | [1-9][0-9]{0,2}(\.[0-9]{3}){0,4} | [1-9][0-9]{3,14} ) "," [0-9]{2}
```

Registered as `NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"`
(`transformations/generalization.py`), recorded in the run scripts' manifest `reproducibility`
block so a result can be tied back to exactly which amount-format contract its treatment ran
under.

**Orchestrator decisions on the owner points, made before any implementation evidence:**

- **cents mandatory** in both families — an integer amount with no cents (`R$ 1.000`,
  `R$ 125000`) is rejected, never guessed;
- **ungrouped Brazilian amounts ACCEPTED** (`R$ 125000,00`) — unambiguous, because the comma
  unambiguously marks the decimal point regardless of whether the integer part is grouped;
- **NBSP ACCEPTED as the single alternate separator** — the one real-world artifact of
  Docling/Office-style export this project's own ingestion path is expected to produce, not a
  step toward general whitespace tolerance;
- **grouped-without-cents amounts REJECTED** (`R$ 125.000`, `R$ 1.234`) — an ambiguous class: a
  grouped integer with no comma could otherwise be misread as a dotted-decimal amount one order
  of magnitude smaller (`R$ 1.234` as `1.234`, i.e. one dollar and 234 thousandths, versus one
  thousand two hundred thirty-four);
- **negatives REJECTED** — there is no protocol need for a negative amount anywhere in this
  project's registered categories (salary, contract value, penalty), and the pre-#93 `-?` prefix
  traces to commit `5a0cde3` with no accompanying rationale or test;
- **leading zeros REJECTED** (`0.00`/`0,00` remain the one string starting with `0`) — a leading
  zero on a multi-digit amount is not a real amount representation in either family;
- **integer part capped at 15 digits** in both families — safely below `2**53`, so no amount this
  grammar accepts can ever motivate a float round-trip;
- digits are `[0-9]` only in every position.

**Disjointness (no string has two readings).** Every `BRAZIL` string contains exactly one `,`;
no `DOTTED` string contains one — the two alternatives are syntactically disjoint by construction,
never by a tie-breaking rule. Value extraction: `DOTTED` is already `<integer>.<cents>`; `BRAZIL`
strips every `.` from the integer part and replaces `,` with `.`.

**Accepted (examples):** `R$ 125000.00`, `R$ 125.000,00`, `R$ 1.275.000,00`, `R$ 125000,00`,
`R$ 1275000,00`, `R$ 1.00`, `R$ 1,00`, `R$ 999,99`, `R$ 1.000,00`, `R$ 0.00`, `R$ 0,00`,
`R$ 999.999.999.999.999,99`, `R$ 999999999999999.99`, `R$ 999999999999999,99`, and the NBSP
variant of any dotted or Brazilian form above.

**Rejected (examples, by reason):** cents-less (`R$ 1.000`, `R$ 1.234`, `R$ 125.000`,
`R$ 125000`); locale-ambiguous (`R$ 1,000.00`); wrong cents digit count (`R$ 125.000,0`,
`R$ 125.000,000`); malformed grouping (`R$ 1.2345,00`, `R$ 12.75.000,00`, `R$ 1.27.500,00`,
`R$ 1.000000,00`); negative (`R$ -5000.00`); leading zero (`R$ 0125000.00`, `R$ 0.000,00`,
`R$ 01,00`); non-ASCII digits (Arabic-Indic, fullwidth, or a single non-ASCII digit mixed into
an otherwise-ASCII string); separator defects (`R$125.000,00`, `R$  125000.00`, `R$\t1.00`,
trailing `\n`, trailing `\r`); trailing prose (`R$ 125000.00 was paid`); over the 15-digit bound
(`R$ 1.000.000.000.000.000,00`, `R$ 1000000000000000.00`); wrong/no currency (`US$ 1.00`,
`1.00`); degenerate (`""`, `None`).

**Anti-ambiguity strategy.** The grammar is closed and exhaustively enumerated rather than
inferred: every accepted string has exactly one syntactically valid reading, and no shape is
resolved by guessing which locale produced it. `tests/test_amount_grammar_cross_check.py`
transcribes this table from the protocol document (not from either implementation's own source)
and asserts both independent parsers (§4) agree with it on every entry.

**Rejection is fail-closed.** `NumericBandStrategy.generalize` raising `GeneralizationError` for
any string outside this grammar reaches the existing pre-pass
(`decision_application._resolve_generalize_downgrades`,
`static_sanitization._resolve_actions_and_generalized_values`) unchanged, downgrading the span to
`BLOCK_REQUEST` — the request blocks with an empty payload; it never raises out of the pipeline,
and never emits a wrong band. The message names only the category (added by the caller,
`generalize()`), never the value, and breaks any exception chain (`from None` is unnecessary
here since no lower-level parser is invoked, but the raised message itself is category-free by
construction).

**Scorer v5.** An oracle span value outside the grammar scores
`generalized_band_unscorable_original` at score time (unchanged reason vocabulary, §5), *and* is
additionally caught by the new pre-run check (§6) before any case in the corpus is even executed.

## 3. The Decimal decision and the canonical band representation

`NumericBandStrategy` now parses to `Decimal`, never `float`: `_parse_amount` returns a
`Decimal` built directly from the matched grammar groups (string concatenation, never a
floating-point division), so no amount this grammar accepts can round-trip through IEEE-754 —
closing both the mis-banding (imprecision) and the `inf`/`NaN`/`OverflowError` failure modes
Issue #88 named. `NumericBandStrategy.__post_init__` additionally requires an integral
`band_width` (both registered widths, `5000.0` and `50000.0`, already satisfy this) — banding is
now done in exact integer arithmetic (`units = int(amount)`, non-negative by construction since
the grammar has no sign; `lower = (units // width) * width`; `upper = lower + width`), so there
is no fractional band boundary to round.

**The canonical transformed-band representation is unchanged.** `NumericBandStrategy.generalize`
still emits `f"{prefix}{lower}-{upper}"` — ASCII digits, a plain space after `R$`, no separator in
`lower`/`upper` — identical in shape to every band this codebase has ever produced, regardless of
which original-amount family (dotted or Brazilian) produced it. This is a deliberate asymmetry: the
*accepted-original* grammar is widened (§2), but the *emitted-band* grammar is not touched at all,
so every existing test/fixture that pattern-matches a band string (`R\$ \d+-\d+`) keeps matching
without modification, and Gate 7's own `_MONEY_PATTERN` helpers (§12) need no change to keep
recognizing a band.

## 4. Independence: two implementations, no shared canonicalizer

Two separate parsers implement the grammar above, deliberately with different techniques, so a
bug shared between them could not make a fidelity check circularly agree with a wrong treatment
output:

- **A (the treatment), `transformations/generalization.py`'s `_parse_amount`** — one alternation
  regex with named groups (`dotted`/`brazil`), `fullmatch`-ed once;
- **B (the scorer, v5 only), `experiments/scoring/utility.py`'s `_parse_original_amount_v5`** —
  two separate compiled patterns (dotted, then Brazilian), each `fullmatch`-ed in turn, tried in
  that order.

`tests/test_amount_grammar_cross_check.py` is the literal table (string → expected `Decimal` or
`REJECT`) written from this document, not from either module's own source; it asserts A and B
agree with the table and, therefore, with each other on every accepted value, and separately
asserts `generalize()`'s emitted band contains B's independently-reparsed value for every
accepted string.

`corpus/models.py`'s existing `NumericUtilityReference.value` grammar
(`_CANONICAL_DECIMAL_PATTERN`, unchanged, `post-pilot-v4`) remains a **third**, independent
reference grammar — the oracle's own canonical-reference value, already ASCII-only and
`fullmatch`-adjacent (`re.Field(pattern=...)`, which pydantic evaluates as a `fullmatch`). It is
not reused by either A or B, and this ticket does not touch it.

## 5. Detector and span coherence

The detector (`detection/rules.py`) stays amount-format-agnostic: it captures whatever text sits
after a labeled line's colon, or a structured pattern for CPF/CNPJ/email/phone, with no
amount-format awareness at all. Grammar enforcement lives entirely in `GENERALIZE` (fail
closed), never in detection. This is deliberate: a grammar-aware detector would let a
*non-conforming* value pass through *undetected* — a privacy regression strictly worse than the
amount being detected and then correctly blocked. `REMOVE`/`PSEUDONYMIZE`/`PRESERVE` are
entirely unaffected by this ticket; only the `GENERALIZE` path's own parser changed.
CPF/CNPJ/phone detection rules keep `\d` (unrelated to the amount grammar) — over-detection there
is the safe direction and out of this ticket's scope.

**CRLF/LF span coherence (Issue #94, fixed in PR #97).** Review found that the labeled-line
detector's old trailing `[ \t]*$` did not strip a `\r` immediately before `\n`, so a CRLF line
such as `Contract value: R$ 125.000,00\r\n` produced `SensitiveSpan.value ==
"R$ 125.000,00\r"`. The v5 amount parser correctly rejects that trailing character with
`fullmatch`, which meant a semantically valid amount could block only because of newline style.
The fix is local to the cause: the labeled-line value group now excludes `\r`/`\n` and permits
the optional CR outside the group. In CRLF text, `start` is unchanged and `end` points just before
`\r`; in LF text, offsets remain the same. In both cases
`input.text[span.start:span.end] == span.value` holds without any artificial offset correction.
Tests cover HR salary and Contracts contract value/penalty with LF and CRLF, plus an end-to-end
CRLF path through detector → `GENERALIZE` → v5 fidelity scoring.

## 6. Dispatch, the compatibility matrix, and the pre-run check

`post_pilot_protocol.py`: `FROZEN_PROTOCOL_IDS` gains `"post-pilot-v5"`;
`SCORABLE_PROTOCOL_IDS = frozenset({"post-pilot-v3", "post-pilot-v4", "post-pilot-v5"})`;
`CURRENT_PROTOCOL_ID = "post-pilot-v5"`.

`experiments/scoring/utility.py` gains, alongside the unchanged v3/v4 code:

- `_parse_original_amount_v5`/`_parse_band_v5`/`_check_band_fidelity_v5` (§4);
- `classify_generalized_band_against_references_v5` — **reuses v4's structured-reference
  sufficiency semantics unchanged** (extracted into a shared private helper,
  `_classify_structured_sufficiency`, called by both the v4 and v5 functions after their own,
  different fidelity check); only the fidelity/grammar underneath differs;
- `UnsupportedOriginalAmountFormatError(ValueError)` and the new pre-run check,
  `_check_v5_original_amount_formats`.

**v3/v4 code paths stay bit-for-bit**, including their `\d` regexes
(`_ORIGINAL_AMOUNT_PATTERN`/`_BAND_STRING_PATTERN`/the v2-era date patterns) and
`_check_band_fidelity`/`classify_generalized_band`/`classify_generalized_date` themselves —
historical pins, unchanged by this ticket.

**Fixed silent fallback.** `score_utility`'s numeric-band dispatch and
`_check_case_protocol_compatibility`, were each an `if v3 … else <v4>` / `if v4 … elif v3` before
this ticket — a structure that would have silently applied v4's own rule to any future scorable
id added without a matching branch. Both are now exhaustive per id
(`if v3: … elif v4: … elif v5: … else: raise UnsupportedScoringProtocolError(...)`), pinned by a
monkeypatch test that adds a fake id to `SCORABLE_PROTOCOL_IDS` without adding a matching branch
and confirms the dispatch raises rather than reusing v4's (or v3's) semantics for it.

**Compatibility matrix** (per case, treatment-independent):

- **`post-pilot-v3`**: legacy oracles only (unchanged from v4's own statement) — a case with a
  non-empty or opted-in-empty `oracle.utility_references` raises
  `StructuredReferencesRequireV4Error`; historical corpora (`hr/v1`, `contracts/v1`) are pinned
  here via `scripts/run_hr_v1_pilot.py`/`run_contracts_v1_pilot.py`.
- **`post-pilot-v4`**: opted-in oracles only (unchanged) — a legacy oracle (`utility_references
  is None`) that depends on a numeric category raises `MissingUtilityReferencesError`; dotted
  originals only (the frozen v4 grammar); a Brazilian original scores
  `generalized_band_unscorable_original` at score time — no new check is added to frozen v4 code.
- **`post-pilot-v5`**: opted-in oracles only, **same** `MissingUtilityReferencesError`/
  `StructuredReferencesRequireV4Error` rules as v4 (the class names are kept — no new exception
  type for this half of the matrix — and the shared message text is broadened from
  "post-pilot-v4 requires" to "post-pilot-v4+ requires" to reflect that both v4 and v5 now share
  the same opted-in requirement), **plus** a new pre-run check over **all** cases in the corpus,
  blocked ones included: any numeric-category oracle span whose value is outside the §2 grammar
  raises `UnsupportedOriginalAmountFormatError` (naming only the case id and category, never the
  value), before any provider call. `hr/v1` and `contracts/v1` are refused under v5 for the same
  legacy-oracle reason as v4 (`MissingUtilityReferencesError`); neither corpus reaches the
  amount-format check at all, since the opted-in-oracle refusal is checked first and both corpora
  fail it identically to v4.
- **any other id**: `UnsupportedScoringProtocolError`.

**The pre-run check, precisely** (`check_corpus_protocol_compatibility` →
`_check_v5_original_amount_formats`, called only when `protocol_id == "post-pilot-v5"`, after the
existing per-case opted-in check): for every case in the corpus, for every `ExpectedSpan` whose
category is a registered numeric category, `_parse_original_amount_v5(span.value)` must not be
`None`. This runs **regardless of `oracle.expected_block_request`** — deliberately not folded
into the existing per-case compatibility check, which returns immediately for a blocked case
(nothing is ever disclosed for one, so no *reference* semantics are exercised) — because a
blocked case's own oracle annotation is still a value Gate 7 authoring must get right, and the
whole point of this checkpoint is that the treatment/scorer amount contract is coherent
end-to-end, independent of any one case's outcome. Zero provider calls: `run_pilot` already calls
`check_corpus_protocol_compatibility` immediately after loading the corpus and before any
treatment/provider call (unchanged since v4); this check is reached at exactly that point.

`scripts/run_hr_v1_pilot.py` and `scripts/run_contracts_v1_pilot.py` are **unchanged in this
ticket** and keep pinning `protocol_id="post-pilot-v3"` explicitly — both corpora stay legacy and
their historical results remain reproducible under `post-pilot-v3`, unaffected by
`CURRENT_PROTOCOL_ID` moving to `post-pilot-v5`. `NUMERIC_AMOUNT_GRAMMAR_ID` is recorded in both
scripts' own `reproducibility` manifest block, since the treatment they run already implements
the widened grammar regardless of which protocol id scores the result.

`RunIdentity`'s shape is unchanged; no `SCHEMA_VERSION` bump. Per-row treatment provenance and
recording the actual code commit in a run's manifest are moved to a new issue, scoped to Gate 8
(§10) — out of scope here, exactly as v4's own §8 moved a different finding to its own issue.

**Semantic grounding is unaffected.** v4 §3a/§3b's semantic-grounding rule for
`utility_references` — a reference need not match the case text lexically, but must correspond
to a condition actually visible to the provider (`CorpusCaseInput.text`/`task`), audited at Gate
7 authoring time, never invented solely to make a band decidable — carries forward to
`post-pilot-v5` unchanged: this ticket widens which *surface forms* of an amount the treatment
and scorer can parse, it does not touch what a reference is permitted to state relative to the
case's provider-visible content.

## 7. Treatment change and provenance

`NumericBandStrategy` (`transformations/generalization.py`) is the only production code whose
*behavior* changes under this ticket (§2/§3). `NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"`
identifies this contract in run-script manifests, mirroring how `post_pilot_protocol.py` versions
the *scoring* methodology on a separate axis — a future grammar change (accepting or rejecting a
different set of strings) requires a new id here, independent of whether the scoring protocol id
also moves.

## 8. ASCII vs. Unicode digits (Issue #91): what changed, what stays, and why the detector keeps `\d`

**What changed.** The new v5 **amount** grammar — treatment-side `_parse_amount`, scorer-side
`_parse_original_amount_v5`, and scorer-side `_parse_band_v5` — uses explicit `[0-9]` character
classes and `fullmatch` exclusively. This closes the amount-path defects Issue #91 named in the
frozen v3/v4 code: (1) bare `\d` under Python's `re` module's default (non-`re.ASCII`) semantics
also matches every Unicode character with the `Nd` (decimal digit) property, so e.g.
`R$ ١٢.00` (Eastern Arabic-Indic digits) parsed as `12.00` under the old grammar; (2)
`.match(...)` combined with a trailing `$` anchor still accepts one trailing `\n` after the
matched content, so a value with a stray trailing newline was silently accepted.

**What stays, for v3/v4 reproducibility and v5 date scope.** `_ORIGINAL_AMOUNT_PATTERN`,
`_BAND_STRING_PATTERN`, `_AMOUNT_PATTERN` (the legacy free-text scanner), and the v2-era date
patterns (`_ORIGINAL_DATE_PATTERN`/`_YEAR_ONLY_PATTERN`/`_YEAR_MONTH_PATTERN`/
`_YEAR_MONTH_DAY_PATTERN`) are frozen historical code and are **not** touched. v5 deliberately
inherits `classify_generalized_date` from v4 unchanged. Review found that
`MonthYearDateStrategy` can accept Unicode digits via `datetime.strptime`; changing only the
scorer-side date grammar would create a treatment/scorer asymmetry, so the date issue remains in
Issue #96 and is outside this v5 monetary contract.

**Why the detector keeps `\d` in CPF/CNPJ/phone rules.** `detection/rules.py`'s structured
identifier patterns (`CPF_PATTERN`, `CNPJ_PATTERN`, `PHONE_PATTERN`) are unrelated to the amount
grammar and are explicitly out of this ticket's scope (the hard constraints forbid editing
detector rules at all) — over-detecting a non-ASCII-digit string as a candidate CPF/CNPJ/phone is
the *safe* direction (it can only lead to more, never less, disclosure control being applied),
the opposite of the amount grammar's own failure mode (a permissive parser silently producing a
wrong band rather than failing closed).

## 9. Historical comparability

**Neither registered corpus is edited, and neither can be scored under `post-pilot-v5` at all**
— both remain legacy (`utility_references` absent) and both have at least one case depending on a
registered numeric category, so they are refused under v5 for the same
`MissingUtilityReferencesError` reason v4 already refuses them (§6); both remain scored under
`protocol_id="post-pilot-v3"` exactly as before this ticket.

**Re-verified directly against the live implementation (not committed corpus data; no new
artifact written):**

- every numeric-category `ExpectedSpan.value` across `corpus/hr/v1` and `corpus/contracts/v1` —
  33 spans total — parses to the identical `Decimal` and produces the identical band string under
  the new grammar/implementation as it did under the pre-#93 permissive-regex/float
  implementation (checked value-by-value, both implementations run side by side against every
  registered numeric oracle span);
- a full `run_pilot` over both corpora under `protocol_id="post-pilot-v3"`, all five treatments,
  `FakeProvider` — 125 case executions total (65 for `hr/v1`, 60 for `contracts/v1`) — is
  unaffected: since every underlying `generalize()` call returns byte-identical output on
  byte-identical input (the point immediately above), and no other code this ticket touches is on
  the `post-pilot-v3` scoring path, status/payload/transformations/scores/deterministic key are
  necessarily unchanged for every case × treatment pair in both corpora.

**No committed artifact changes under this ticket** — every `artifacts/experiments/**` file
already on disk was produced under `post-pilot-v1`/`-v2`/`-v3` and remains valid under whichever
of those ids it already names.

## 10. Separate issues filed (recorded, not fixed here)

1. **[Issue #95](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/95) — manifests do
   not record the actual code commit or per-row treatment provenance** — decided at Gate 8, not
   here; `NUMERIC_AMOUNT_GRAMMAR_ID` (§7) is the one new provenance field this ticket adds, and it
   is a free-form `reproducibility` value, not a schema change.
2. **[Issue #96](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/96) —
   `MonthYearDateStrategy` (`transformations/generalization.py`, `strptime`) accepts Unicode
   digits** (e.g. a date string using Eastern Arabic-Indic digits parses successfully, verified for
   this ticket) — this is a treatment/scorer date-boundary issue, not part of the numeric-amount
   contract this ticket is scoped to. v5 therefore inherits v4 date semantics unchanged.

## 11. Anti-tuning statement

This satisfies v1 §11's four-step change procedure exactly as v2/v3/v4 did: (1) recorded here and
in `docs/implementation-status.md`; (2) neither corpus this rule reaches stays scorable under it
at all (§9) — `pilot_development` classification is unaffected either way, and the amount-grammar
widening is orthogonal to any oracle value either corpus actually uses (both are dotted-decimal
only); (3) versioned as `post-pilot-v5`, this document; (4) no new held-out round is created by
this ticket — that remains Gate 7, not this one, and this ticket explicitly does not author any
confirmatory corpus. The grammar itself (§2) was fixed from the realistic-format requirement
(#88), the ASCII-correctness requirement (#91) and the detector/span-coherence requirement,
decided **before** any confirmatory Contracts case existed and before any B0–B4 result under a
Brazilian-formatted amount was ever produced or inspected — no B3/B4-improvement argument
motivates any part of this grammar, and neither historical corpus's own numbers change (§9).

## 12. Test coverage mapping

| Area | Test file |
| --- | --- |
| Amount grammar, both parsers, literal table | `tests/test_amount_grammar_cross_check.py` |
| Treatment-side generalization (bands, edges, fail-closed) | `tests/test_generalization.py` |
| B1 static-sanitization GENERALIZE fixture/fail-closed | `tests/test_static_sanitization.py` |
| v5 fidelity, v5 date-inherits-v4 pin, dispatch exhaustiveness, pre-run check | `tests/test_experiments_scoring_post_pilot_v5.py` |
| Detector/span LF and CRLF coherence | `tests/test_detection_rules.py` |
| v3 fidelity unchanged (historical pin) | `tests/test_experiments_scoring_numeric_band_utility.py` (unchanged) |
| v4 structured references unchanged (historical pin) | `tests/test_experiments_scoring_utility_references_v4.py` (unchanged) |
| Protocol registry (`FROZEN_PROTOCOL_IDS`, `SCORABLE_PROTOCOL_IDS`, document drift) | `tests/test_post_pilot_protocol.py` |

**Gate 7 note.** A future confirmatory corpus must be authored to fit this grammar (§2). The
`_MONEY_PATTERN` helpers in `tests/test_corpus_answer_grounded_in_input.py:42` and
`tests/test_corpus_contracts_coverage.py:74` (`re.compile(r"R\$\s?\d+(?:\.\d+)?")`) are
dotted-only, free-text grounding scanners over `expected_answer`/case text — unrelated to, and
must not be reused for, the closed §2 grammar a Gate 7 oracle span/original-amount value must
satisfy; Gate 7 tooling should add its own grammar-aware guard rather than repurpose either
helper. Gate 7 has **not** started as part of this ticket — this document only removes the
pre-Gate-7 numeric-format blocker Issue #93 was filed to close.

## 13. Change log

- 2026-09-21 — `post-pilot-v5` frozen (Issue #93, resolving #88 and #91): closes the pre-Gate-7
  numeric-amount-format checkpoint end to end. Replaces `NumericBandStrategy`'s permissive
  float-based amount parser with a closed, ASCII-only, `fullmatch`-only grammar
  (`NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"`) parsed to `Decimal`; adds an independent
  v5 scorer-side re-derivation of the same grammar (different technique) and a v5 band grammar;
  fixes labeled-line CRLF span coherence for HR and Contracts values; makes `score_utility`'s
  and `_check_case_protocol_compatibility`'s
  protocol-id dispatch exhaustive per id instead of an unconditional non-v3-means-v4 fallback;
  adds a v5-only pre-run check (`UnsupportedOriginalAmountFormatError`) over the whole corpus,
  blocked cases included, before any provider call. v3/v4 code paths (regexes included) stay
  byte-for-byte, and v5 date utility semantics intentionally inherit v4. Re-verified against the
  live implementation: 33/33 numeric oracle spans across
  both frozen corpora produce identical bands; a full `post-pilot-v3` run (125 case executions)
  over both corpora is unaffected. Files three further, narrower findings as separate issues
  (§10) rather than fixing them here.
