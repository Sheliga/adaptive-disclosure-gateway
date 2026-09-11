---
protocol_id: post-pilot-v1
status: FROZEN
frozen_date: 2026-09-11
supersedes: none
ticket: T23 / Issue #36
---

# Post-pilot confirmatory analysis protocol — v1

This document is a **methodological gate**, not a report of results and not a plan to improve
any number. It freezes, before any held-out confirmatory B0–B4 batch is run, the rules that
batch must obey — dataset classification, metrics, provider requirements, analysis plan and
provenance — so that later results cannot drive the rules used to judge them.

It is authoritative alongside `docs/experimental-design.md` (treatment definitions and
pairwise comparisons) and `docs/milestone-2-pilot.md` (the M2 pilot's factual record). Where
this protocol names a runner field, artifact, module or function, that name was verified
against the current repository at freeze time (commit range ending at the branch point of
`research/t23-freeze-protocol`); it does not invent a field the runner does not produce.

## 0. Versioning

- `protocol_id: post-pilot-v1` is this document's frozen identifier, registered in
  `src/adaptive_disclosure_gateway/experiments/post_pilot_protocol.py`
  (`FROZEN_PROTOCOL_IDS`, `CURRENT_PROTOCOL_ID`). A test
  (`tests/test_post_pilot_protocol.py`) pins that the two can never silently drift apart.
- `status: FROZEN` means this document's methodological content — metrics, thresholds/
  interpretation rules, dataset classification, the primary B3→B4 comparison, provider
  requirements, the analysis plan and the anti-tuning rule — is not edited in place once
  a held-out confirmatory batch has been run under it.
- A later methodological change (a new metric, a changed threshold, a different primary
  comparison, …) creates `docs/research/post-pilot-protocol-v2.md` with `protocol_id:
  post-pilot-v2`, added to `FROZEN_PROTOCOL_IDS`. `post-pilot-v1` is never rewritten or
  deleted; it stays the historical record of what governed whichever runs cited it.
- This document may still be edited for a pure typo/clarity fix that changes no
  methodological content, exactly like a frozen corpus's own non-normative prose could be
  corrected without changing `sample_id`s or offsets — but any change to a number, a
  formula, a classification rule or a comparison cell requires a new version.

## 1. Dataset/run classification

Two run classifications exist, already implemented as a closed
`Literal["pilot_development", "held_out_confirmatory"]`
(`src/adaptive_disclosure_gateway/experiments/run_identity.py`, `RunClassification`,
`PILOT_DEVELOPMENT`, `HELD_OUT_CONFIRMATORY`). This protocol does not add a third value; it
freezes the rule for choosing between the two existing ones.

### `pilot_development`

Every result produced against `corpus/hr/v1` — including the M2 pilot recorded in
`docs/milestone-2-pilot.md` (`experiment_run_id 13198a3b95bd49b88a62f591f3da1224`) and
everything produced while developing or observing it — is, permanently, `pilot_development`.
This includes:

- the 13-case main pairwise run over `hr-v1`;
- the five `hr-v2`/`hr-v3` contextual-matrix comparisons (`CONTEXTUAL_MATRIX_SPECS`,
  `src/adaptive_disclosure_gateway/experiments/contextual_matrix.py`);
- any re-run of the same corpus/policy/treatment combination for debugging, regression or
  documentation purposes.

`corpus/hr/v1` can **never** be relabeled `held_out_confirmatory` after the fact. It was used
while B3 and B4 were built and reviewed (`docs/experimental-design.md`, "Development vs
confirmatory evidence"), and freezing the corpus after development does not erase that it was
inspected during development — held-out status is about the *history* of a dataset relative to
the treatments and metrics being judged, not about whether the files are currently immutable.

### `held_out_confirmatory`

A run may be classified `held_out_confirmatory` **only if every one of the following was
frozen before that run's results were inspected at all**:

1. corpus (documents/cases);
2. tasks (the instruction/task text paired with each case);
3. oracle (expected spans, task-necessity labels, expected actions, expected answer,
   reconstruction expectations);
4. categories (the set of sensitive-information categories the detector/oracle use);
5. necessity rules (how `REQUIRED`/`NOT_REQUIRED` are assigned to a span);
6. policies (the policy YAML document(s) governing the run, e.g. an `hr-vN` or
   `contracts-vN` document);
7. generalization strategies (`transformations/generalization.py`'s banding/strategy
   configuration for any category exercised);
8. treatment implementations (the B0–B4 code actually executed, named by commit — see
   §13, Provenance);
9. metrics (which scorers run and how they aggregate — this protocol, §4–§7);
10. statistical protocol (this protocol, §10);
11. provider/model/config (this protocol, §9);
12. canonical representation (this protocol, §3).

If **any** of these is still being developed, tuned or extended using that dataset's own
results, the run is `pilot_development` — never `held_out_confirmatory` — regardless of how
final it otherwise looks. There is no partial-confirmatory state: a run is confirmatory only
once every item above was frozen *before* its results were looked at.

### Practical consequence for what exists today

At freeze time, nothing qualifies as `held_out_confirmatory` yet. `corpus/hr/v1` is
pilot/development by the rule above; a second domain (Contracts) has none of items 1–7 frozen
yet (`docs/experimental-design.md`'s Phase B, T24/#37). The next confirmatory-eligible run
requires, at minimum, T12 (representation stability), the Contracts domain extensions, and a
newly frozen held-out corpus under this protocol — see §14.

## 2. Contracts transition gate

This section makes explicit the gate Issue #36's follow-up comment asked T23 to freeze.

A Contracts run may be inspected as `held_out_confirmatory` only after, in this order:

1. **T12 / Issue #9** stabilizes ingestion/representation (direct normalized text is
   available as a parser-independent canonical path — see §3);
2. Contracts domain support is implemented in the shared core (categories, detector rules,
   policy engine support for the domain — not a parallel implementation);
3. Contracts categories, policies, generalization strategies and tasks are defined and
   committed;
4. the Contracts oracle (expected spans/actions/answers, analogous to
   `corpus/hr/v1/SCHEMA.md`'s `oracle` block) is frozen;
5. the Contracts held-out corpus itself is frozen (case files committed, immutable under a
   freeze rule analogous to `corpus/hr/v1/README.md`'s);
6. **only then** may held-out Contracts B0–B4 results be inspected.

If any change to categories, policies, generalizations, tasks, the oracle or the corpus is
made **after** a held-out Contracts round's results have been inspected, that round is
retroactively reclassified `pilot_development` (never left labeled confirmatory after the
fact), and a new, independently frozen held-out corpus must be produced before the next
confirmatory attempt. This is the general anti-tuning rule (§11) applied specifically to the
Contracts transition, per Issue #36's follow-up comment.

**T22 (real provider) proceeds in parallel** with the Contracts transition gate: it is required
before any authoritative real-provider claim (§9), but it is not itself a Contracts held-out
result and is neither blocked by, nor a precondition for, this gate.

**Preliminary Contracts work may proceed in parallel with T12** only for work that does not
depend on T12's final, stabilized representation — conceptual survey, candidate category
taxonomy, domain analysis and requirements-gathering are not blocked by T12 being unstable.
**The confirmatory Contracts freeze may not happen while T12 is still unstable.** Before
corpus, oracle, offsets, canonical representation and fixtures/scoring representation
(items 3-5 above, and §3's canonical-representation rule) are definitively frozen, T12 (item 1)
must be stabilized — a Contracts corpus frozen against a still-moving parser/representation
would be frozen against a variable this protocol requires held constant (§3), and would need to
be re-frozen once T12 stabilizes. In one line: **T12 is a prerequisite for the final
confirmatory Contracts freeze; T22 is parallel.**

## 3. Canonical representation

**Direct normalized text is the frozen canonical representation for scientific scoring,
independent of which parser produced it.**

T12/Docling may attach additional structure to a document — sections, tables, hierarchy,
metadata, block boundaries — but that structure is *ingestion* metadata, not a second
scientific representation. The representation any scorer in
`src/adaptive_disclosure_gateway/experiments/scoring/` reads (span offsets into `input.text`,
per `corpus/hr/v1/SCHEMA.md`'s "every offset in `oracle.expected_spans` is relative to this
exact string") stays plain normalized text for every treatment compared in one batch.

Rule: **within one comparison, every treatment (B0–B4) is fed the same normalized document via
the same parser/ingestion path.** It is never valid to compare "B0 over parser A's output"
against "B4 over parser B's output" and attribute the difference to the treatment — that
would confound the treatment variable with an ingestion variable
(`docs/experimental-design.md`'s "Held constant across treatments" already states this
generally for "same case/input"; this section makes it explicit for a parsed/normalized
document specifically, since T12 introduces the first alternative to hand-authored plain
text).

Concretely, for any batch (HR or Contracts): same source document → same normalized text →
same parser/ingestion version recorded in provenance (§13) → identical text fed to every
treatment under comparison. A parser version bump is a provenance fact to record, never a
silent per-treatment variable.

## 4. Exposure metrics

### 4.1 The ladder (pinned, not redefined)

The ordered exposure ladder is `REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE`, implemented in
`src/adaptive_disclosure_gateway/experiments/scoring/exposure.py`'s `score_exposure`, which
itself reuses `transformations.relevance_selection.CANONICAL_DISCLOSURE_ORDER` — the same
ladder B3/B4 use internally to reason about "least disclosing". This protocol does not
redefine or re-derive that ladder; it is pinned by reference to that one source, so the two
can never drift apart (the source has never been duplicated or re-typed here).

`score_exposure` already produces, per oracle span, a `SpanExposure{index, category,
task_necessity, outcome, level, level_rank}` where `outcome` is one of `"exposure_level"`,
`"block_request"` or `"unscorable"`. `BLOCK_REQUEST` is deliberately not a rung on the ladder
(a blocked span transmitted nothing in *any* representation — it is a categorically different
outcome from choosing among the four ordered levels).

### 4.2 Secondary metric — binary unnecessary disclosure (preserved)

**Preserved exactly as M2 computed it, demoted from sole-primary to secondary.** Formula
(`experiments/scoring/unnecessary_disclosure.py`, `score_unnecessary_disclosure`):

```
rate = (# NOT_REQUIRED spans transmitted in any representation other than REMOVE)
       / (# NOT_REQUIRED spans present in the case)
```

- "transmitted" means exposure outcome `"exposure_level"` with `level != REMOVE` — i.e.
  `PSEUDONYMIZE`, `GENERALIZE` and `PRESERVE` all count as transmitted; only `REMOVE` does
  not.
- `BLOCK_REQUEST` spans are excluded from the numerator by construction (nothing was
  transmitted for a blocked case) but still count toward the denominator if the span is
  `NOT_REQUIRED` — a correctly-blocked case does not artificially improve the rate by
  shrinking its own denominator.
- `rate` is `None` (never `0.0` or `1.0`) when a case has zero `NOT_REQUIRED` spans — an
  undefined rate is reported as undefined, not manufactured.
- This metric is never redefined by this protocol: `tests/test_post_pilot_protocol.py`
  (§15 below) pins, as a real regression, that `PSEUDONYMIZE` still counts as transmitted —
  exactly the M2 finding this section preserves for historical continuity
  (`docs/experimental-design.md`, "binary unnecessary disclosure penalizes pseudonymization").

This metric answers: *did any readable trace of a not-required unit leave the boundary at
all?* It treats "opaque pseudonym" and "raw value" as the same answer (both "yes, something
left"), which is exactly the M2 finding — it does not distinguish a protected representation
from direct preservation, and it is retained specifically so that limitation stays visible and
comparable to M2's own numbers, not because it is the more informative metric of the two.

This rate is not merely a separate, coexisting number alongside §4.3's primary metric: it is
**recoverable as that family's first threshold** — see §4.3's "The historical secondary metric
is one threshold of this family" for the exact correspondence.

### 4.3 Primary metric — ordinal/cumulative unnecessary exposure

**This is an aggregation over data `score_exposure` already produces — no new scoring concept,
no new detector or oracle field.** It answers a different question from §4.2: *when a
not-required unit was transmitted, how exposed was it, without assuming the ladder's rungs are
evenly spaced?*

**Unit of analysis:** one oracle `expected_span` (`ExpectedSpan`), scored once per case per
treatment — identical unit to `score_exposure`/`score_unnecessary_disclosure`.

**Population:** every span with `task_necessity == NOT_REQUIRED` and exposure `outcome ==
"exposure_level"` (i.e. excludes `block_request` and `unscorable` spans from the population
being scored for *level*, exactly as the ladder itself excludes them from ranking — see §4.1).

**Why an ordinal/cumulative representation, not a mean of ranks:** §4.1 already establishes
`REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE` as an **ordinal** scale — B3/B4 use it only to
pick "the least disclosing available option", never to claim e.g. that PRESERVE is "three times
as exposing" as REMOVE. Taking the arithmetic mean of the integer `level_rank`
(`CANONICAL_DISCLOSURE_ORDER.index(level)`, so `REMOVE=0, PSEUDONYMIZE=1, GENERALIZE=2,
PRESERVE=3`) silently treats the three gaps between consecutive levels as equal in size — an
**interval** assumption the ladder's own ordering carries no empirical justification for, and
which an earlier draft of this section froze as primary without acknowledging. The primary
representation frozen here instead uses only the information the ordering actually supports:
how the population distributes *across* levels, and how far up the ladder it reaches — never an
arithmetic distance between levels.

**Per-case and per-treatment primary statistics**, reported over the scorable `NOT_REQUIRED`
population (denominator `not_required_count`, always explicit, never implied):

- **exact per-level counts and proportions** — `not_required_level_counts` (the count at each
  of the four levels) and the corresponding proportions
  (`proportion_remove`/`proportion_pseudonymize`/`proportion_generalize`/`proportion_preserve`,
  summing to 1 over a non-empty population) — both reported together, so a reader is never left
  reconstructing a count from a rounded percentage;
- **exceedance distribution** — the cumulative complement of the level proportions, computed
  directly from them (never independently, so the two can never drift apart):
  - `p_exposure_at_least_pseudonymize` = `1 - proportion_remove`
  - `p_exposure_at_least_generalize` = `proportion_generalize + proportion_preserve`
  - `p_exposure_at_least_preserve` = `proportion_preserve`

  each answers "what fraction of not-required content was exposed at or beyond this level" —
  exactly the ordinal question the ladder supports, without inventing a distance between rungs;
- **maximum level reached** (`not_required_max_level`) — the single most-exposed not-required
  unit's level, reported by name (e.g. `"GENERALIZE"`), not only its rank; ordinal-safe, since
  "more exposed than" is well-defined without needing a distance; `None` if the population is
  empty;
- **median level** (`not_required_median_level`) — the middle value of the sorted level
  sequence for a non-empty population (for an even-sized population, the lower of the two
  middle values, so the reported median is always a level that actually occurred, never an
  interpolated non-level); also ordinal-safe, unlike a mean;
- **counts, always alongside the above, never folded into them** — `not_required_count`,
  `not_required_block_count`, `not_required_unscorable_count`.

**Per-treatment (corpus-level) aggregation** mirrors `DetectorAggregateScore`'s existing
micro/macro distinction (`experiments/scoring/detector_scoring.py`), applied to the
proportions/exceedance values above rather than to a mean of ranks. Averaging a *proportion* (a
value in `[0, 1]` representing "what fraction of this population reached at least this level")
does not carry the interval-scale assumption the rejected `mean(level_rank)` formulation would,
because it never treats the *distance between levels* as meaningful — only membership at or
beyond a named level:

- `micro_*` — pool every not-required span across the whole corpus first (weighting every span
  equally, regardless of case), then compute the proportions/exceedance/max/median over the
  pooled population;
- `macro_*` — compute each case's own proportions/exceedance/max/median first, then average
  those per-case values across cases with a non-empty population (weighting every *case*
  equally).

Neither is "more correct" than the other, exactly as documented for detector scoring; both are
reported.

**The historical secondary metric is one threshold of this family, not a separate concept.**
`unnecessary_disclosure.py`'s binary rate (§4.2) counts a span as "transmitted" when exposure
`outcome == "exposure_level"` and `level is not DisclosureAction.REMOVE` — i.e. `level` in
`{PSEUDONYMIZE, GENERALIZE, PRESERVE}`. That is, by construction, exactly
`p_exposure_at_least_pseudonymize` as defined above. The two metrics are therefore
**commensurable, not merely coexisting**: §4.2's binary rate is recoverable, without
re-deriving it, as the first exceedance threshold of this primary family — a genuine continuity
argument M2's own report could not make, since the exceedance family did not exist yet. This is
stated once, here, rather than duplicated at every mention of either metric.

**Handling `block_request`:** a `BLOCK_REQUEST` outcome is never assigned a level and never
enters any proportion, exceedance, maximum or median computed above — a case that blocks
entirely removed every not-required unit from readable transmission, which is a categorically
different (better, on the exposure axis) outcome than any of the four ranked levels, not
equivalent to `REMOVE` and not folded into any statistic here. It is reported as a separate
count (`not_required_block_count`) so a reader can see it without it silently pulling any
statistic toward "fully removed" or being excluded without a trace.

**Handling `unscorable`:** a span whose category's transformation pool ran out
(`span_matching.py`'s documented behavior when detection recall is imperfect for a category) is
excluded from every statistic above and reported separately
(`not_required_unscorable_count`), never treated as `REMOVE` and never silently dropped from
the reported denominator context.

**Behavior when no relevant spans exist:** if a case (or, in the corpus-level aggregate, the
whole corpus/treatment) has zero `NOT_REQUIRED` spans with a scorable exposure level, every
proportion/exceedance/maximum/median field is `None` — never `0` or `0.0` (which, for
exceedance specifically, would misleadingly assert "definitely not exposed at this level") and
never omitted (which would hide that the case contributed nothing to the metric).

**How to read a value:** a higher `p_exposure_at_least_generalize` (or any other threshold)
means more not-required content was exposed at or beyond that level. Comparing two treatments'
`micro_p_exposure_at_least_pseudonymize` answers exactly what §4.2's binary rate already answers
(by construction — see above), while `micro_p_exposure_at_least_generalize` and
`micro_p_exposure_at_least_preserve` add the ordinal detail the binary rate collapses: a
treatment that consistently pseudonymizes not-required content shows a high value at the
`pseudonymize` threshold but a low value at the `preserve` threshold, distinguishing it from a
treatment that regularly preserves it (high at every threshold) — exactly the distinction §4.2's
binary rate collapses (both would show up as "100% transmitted") — without asserting that any of
the thresholds are equally spaced from one another.

**`mean_level_rank` — an optional secondary descriptive statistic, never the primary one.** A
report may additionally compute `micro_mean_level_rank`/`macro_mean_level_rank` (the arithmetic
mean of `level_rank` over the same population — what an earlier draft of this section froze as
*the* primary metric) **only** alongside an explicit note that it assumes the four levels are
uniformly spaced purely for summarization convenience, and **never** as the sole basis of a
scientific claim comparing treatments. The exceedance/proportion family above is the frozen
primary representation; a mean-of-ranks figure, if reported at all, is decoration on top of it,
not a substitute for it.

**Why no weighting beyond exact per-level proportions and cumulative exceedance is used:** the
brief instructs against choosing weights that make B4 look better, and to prefer a formulation
that avoids an indefensible weighting where none exists. Exact per-level proportions and their
cumulative exceedance use only the ordering the ladder's own definition supports — "at or beyond
this level" — without asserting a size for any gap between levels. No alternative weighting
(e.g. giving `PRESERVE` a disproportionately large penalty, or any interval-scale distance
between rungs) is adopted, because no such weighting was derivable from the ordering's own
documented meaning ("least disclosing useful action") without inventing an additional, unfrozen
judgment call — exactly the kind of post hoc choice §11 forbids once results exist to be
improved.

**Requirement for future execution:** the runner (`experiments/aggregation.py`) does not yet
compute `not_required_level_counts`, the per-level proportions, the exceedance distribution,
`not_required_max_level`, `not_required_median_level` (micro or macro), or the optional
`mean_level_rank` today — `TreatmentSummary` currently reports only the binary rate (§4.2); it
does, separately, already contain some rank-based logic elsewhere in the runner
(`aggregation._exposure_rank_sum`, used only for `B3ToB4CaseComparison.exposure_direction`
in the B3→B4 pairwise comparison, §8 — a per-case ordinal direction check, not a corpus-level
mean and not this primary metric). Implementing this section's aggregation (reading
`CaseResult.score.exposure.spans`, already present on every serialized result, and
`CaseResult.score.conformance.spans[*].task_necessity` for the `NOT_REQUIRED` filter) is
in-scope for the next runner change that executes a confirmatory batch under this protocol —
**not** for T23 itself, which freezes the formula, not the implementation. No number in this
document should be read as already computed by the current runner.

## 5. Necessity

`task_necessity` (`REQUIRED`/`NOT_REQUIRED`) comes **exclusively** from the frozen oracle
(`corpus/*/SCHEMA.md`'s `oracle.expected_spans[*].task_necessity`, a primary, strictly binary
field per schema — `HELPFUL` is a separate, auxiliary-only annotation that never participates,
per `docs/experimental-design.md` and `tests/test_experiments_scoring.py`'s existing
`test_helpful_flag_never_participates_in_unnecessary_disclosure_scoring`).

The evaluated treatment (B0–B4) never decides, retroactively or otherwise, what was necessary.
This is already structurally enforced, not merely documented:

- `execute_case` (`experiments/execution.py`) takes a `CorpusCaseInput`, never a `CaseOracle`
  — there is no parameter through which necessity labels could reach treatment execution;
- ground truth is read only after `execute_case` returns, by `score_case`
  (`runner.run_case_for_treatment`'s own ordering: `execute_case` then `score_case`);
- `tests/test_corpus_oracle_isolation.py` pins, by AST inspection, that no module under
  `transformations/`, `detection/`, `policies.py` or `pipeline.py` imports anything from
  `adaptive_disclosure_gateway.corpus` at all.

This protocol adds no new mechanism here — it freezes that the existing isolation is a
methodological requirement, not an implementation convenience that a future ticket may relax
"just for one case". Any future PR that gives a treatment, analyzer or policy engine a
parameter shaped like ground truth (an oracle, an expected action, a necessity label) violates
this section regardless of how it is justified, and must be rejected or redesigned before a
confirmatory run may use it.

## 6. Utility

### 6.1 What is scored, and how

Utility is scored against `CaseOracle.expected_answer`/`answer_depends_on_categories` — the
**utility oracle**, deliberately independent of the **conformance oracle**
(`expected_actions`), per `corpus/hr/v1/SCHEMA.md`'s "Conformance and utility are independent
oracles". `experiments/scoring/utility.py`'s `score_utility` already implements this scoring
and this protocol freezes it (no code change), separating exactly these outcomes:

| Outcome | Meaning |
| --- | --- |
| `answerable` | The disclosure-controlled payload retains enough information, per category, for the task to succeed. |
| `not_answerable` | It does not (removed/pseudonymized-non-reconstructable/unexpected-block/unscorable). |
| `indeterminate` | A generalized band cannot be resolved against a stated reference value (`_band_is_decidable`) — genuinely ambiguous, not a failure to compute. |
| `not_applicable` | The case has no answer to score at all (`expected_block_request` cases) or no categories the answer depends on. |

Additionally, **separated, never fused into a single utility scalar** (per
`experiments/scoring/outcomes.py`'s `CaseOutcomeFlags` and `classify_ordinary_utility_failure`,
already implemented and frozen by this protocol):

- **task success** — `UtilityScore.overall == "answerable"`;
- **utility loss** — `not_answerable` or `indeterminate` while the case was *not* blocked and
  not impossible-under-policy (`classify_ordinary_utility_failure`'s "ordinary utility
  failure");
- **baseline comparison** — B0's own utility outcome is the experimental reference point for
  what "everything preserved" achieves, reported alongside every other treatment's outcome for
  the same case, never presented as a target other treatments should match (see §6.2);
- **provider failure** — `AuditRecord.provider.failed` (`CaseOutcomeFlags.provider_failure`),
  reported distinctly from an ordinary task failure — the provider errored, the treatment did
  not get a chance to succeed or fail on the merits;
- **blocked response** — `outcomes.blocked` (`DisclosureResult.status == "blocked"`); a
  correctly-blocked, policy-expected case is not an ordinary utility failure at all
  (`classify_ordinary_utility_failure` explicitly excludes it);
- **absent response** — `"unexpected_block"` (an oracle that did **not** expect a block but the
  run produced one anyway — `score_utility`'s own branch for this), reported distinctly from
  an *expected* block.

### 6.2 B0 is a reference, never a recommendation

B0 — Direct is the unsafe-control/reference baseline, never an operational recommendation. Its
utility-maximization claim must be scoped to where it actually holds, not stated unconditionally:

- **Under `FakeProvider`'s information-sufficiency proxy (§6.3):** B0 sends the original text
  with no disclosure control, so it preserves all original information and therefore provides
  the *ceiling of information availability* under that proxy — every category the task could
  possibly need is present in the payload by construction. This is a claim about *information
  availability* under the current proxy, not about real task success.
- **Under a real provider (T22):** more context does not guarantee a better answer. Irrelevant
  or excessive information can affect provider behavior in ways the FakeProvider proxy cannot
  model (distraction, dilution of the relevant signal, and similar effects). **B0 must not be
  assumed a priori to show the highest observed utility once a real provider scores the
  response** — whether B0 in fact achieves the highest utility under a real provider is an
  empirical question that provider's run must answer, not a conclusion this protocol fixes in
  advance.

Any comparison that treats "B0 achieves higher utility" as evidence that B0 is operationally
preferable inverts the experiment's own premise regardless of provider — B0 exists to bound what
*information is available* at zero disclosure control, not to recommend zero disclosure control,
and (under a real provider) not even guaranteed to bound observed task success. Every report
under this protocol states both of these points explicitly whenever a B0 utility figure is shown
alongside B1–B4.

### 6.3 Provider-dependence of the utility measurement itself

Under `FakeProvider`, utility is necessarily an **information-sufficiency proxy** — whether the
disclosure-controlled *payload* retains enough information for a competent provider to answer,
never the literal correctness of an actual provider response (`FakeProvider` never computes a
real answer at all — see `providers/fake.py`). This proxy is the only utility measurement
`FakeProvider` makes possible and this protocol does not treat it as equivalent to real-LLM
task success (§9 formalizes this boundary generally). Once a real provider is available (T22),
utility must be re-scored from actual provider output for any run claiming authoritative
utility results; the FakeProvider proxy result for the same batch remains a distinct,
separately labeled measurement, not silently overwritten or averaged together with it.

### 6.4 Acceptable utility-loss threshold

**No numeric utility-loss threshold is frozen.** M2's own record
(`docs/experimental-design.md`, "M2 pilot calibration and T23 freeze") states plainly that no
threshold was selected before M2, and the pilot's N=13 cases per treatment cannot justify
deriving one now without it being, in substance, reverse-engineered from the one dataset it
would then be evaluated against — exactly the post hoc selection this protocol exists to
prevent.

Instead, the frozen **interpretation rule** (which cannot itself be changed after seeing
held-out confirmatory results, per §11) is:

- report the full `by_category` utility breakdown and the case-level `overall` outcome for
  every case — never reduce a batch to one percentage without the underlying distribution
  alongside it (§10's "no reduction to one mean" rule applies here specifically);
- an *ordinary* utility failure (§6.1) is evidence the treatment under-minimized or
  over-minimized relative to what the task needed; it is not, by itself, evidence the
  treatment is unacceptable — that judgment requires comparing the *rate* and *pattern* of
  ordinary utility failures against the adjacent, less-disclosing treatment in the canonical
  sequence (§4.1's pairwise comparisons), not against an absolute cutoff;
  the frozen `hr_salary_analysis_003/salary` divergence (§12) is the canonical illustration:
  the correct interpretation is "B3 chose a conformant-in-spirit-but-ambiguous generalization
  that this task's stated reference cannot resolve", not "B3 crossed a numeric threshold and
  therefore failed";
- a numeric threshold may be proposed only in a future protocol version (`post-pilot-v2`+),
  justified from an external basis (a stated organizational risk tolerance, a task-specific
  acceptance criterion agreed before the batch, or a larger held-out sample where a threshold's
  discriminating power can itself be validated) — never derived from tuning against the very
  batch it would then gate.

## 7. Performance/overhead

### 7.1 What is measured and how (frozen from M2, unchanged)

| Signal | Unit | Source |
| --- | --- | --- |
| Treatment latency | ms | `stage_timings.treatment_ms` (`stage_timing.py`, the `<semantic>.sanitize` span, structurally proven disjoint from `detection.detect` — `b0_treatment_span_is_isolated_from_detection`) |
| Detection latency | ms | `stage_timings.detection_ms` (first `detection.detect` child span) |
| Task-detection latency | ms | `stage_timings.task_detection_ms` (second `detection.detect` call, absent for B0) |
| Reconstruction latency | ms | `stage_timings.reconstruction_ms` (absent for B0/B1) |
| Provider latency | ms | `ProviderCallMetrics.latency_ms` (`provider_instrumentation.py`, wall-clock around `generate()`) |
| Total pipeline latency | ms | `stage_timings.pipeline_total_ms` (whole `pipeline.run_disclosure_case` span) |
| Process CPU time | ms | `ResourceMetrics.cpu_time_ms` (`resource_metrics.py`, `time.process_time()` delta) |
| Peak memory | bytes | `ResourceMetrics.peak_memory_bytes` (`tracemalloc` peak *traced* Python-level allocation — not RSS, not C-extension allocation) |
| Disclosure-controlled payload volume | bytes | `ProviderCallMetrics.payload_bytes` |
| Total provider-request volume | bytes | `ProviderCallMetrics.total_request_bytes` (payload + task) |
| Token usage | — | **not available under FakeProvider**; deferred to T22 |
| Cost | — | **not available under FakeProvider**; deferred to T22, and only meaningful once a real provider with real pricing exists |

### 7.2 Aggregation level and reported statistics

- report **per-case** values (already serialized in full in `results.jsonl` via
  `to_safe_dict`) — never discard the distribution;
- report **per-treatment** means (`TreatmentSummary.mean_treatment_ms`,
  `mean_provider_ms`, `mean_pipeline_total_ms`, `mean_payload_bytes`,
  `mean_total_request_bytes`, `mean_cpu_time_ms`, `mean_peak_memory_bytes` — already computed
  by `aggregation.summarize_treatment`) alongside, never instead of, the per-case values;
- resource measurement scope is reported verbatim
  (`ResourceMetrics.measurement_scope` /
  `TreatmentSummary.resource_measurement_scope`, currently
  `"detection+treatment+provider+reconstruction (whole pipeline.run_disclosure_case call, via
  run_case_with_span_capture)"`) — a reader must never be left to guess whether a number covers
  the whole pipeline or one stage.

### 7.3 Absolute vs relative comparison

Both are reported, with relative (pairwise, adjacent-only, per §4.1's canonical sequence)
treated as the primary read for a *causal* performance claim ("does adding policy governance
cost meaningfully more than task-awareness alone"), and absolute treated as descriptive context
only ("what does B4 cost on this hardware, under FakeProvider, for this corpus"). An absolute
number from FakeProvider/pilot hardware is never presented as a production capacity or SLA
claim.

### 7.4 Warm-up, outliers, failures

- **Warm-up:** the current runner executes cases serially with no explicit warm-up phase
  (`runner.run_pilot`). Any confirmatory batch introducing a warm-up convention (e.g.
  discarding the first N executions per treatment before measuring) must freeze and record
  that convention in provenance (§13) *before* the batch runs — it is not retrofittable after
  seeing which cases looked like outliers.
- **Outliers:** no case is excluded from a reported mean based on its own performance number.
  A case may be excluded only for a documented, performance-independent reason (e.g. a
  provider failure, see "Failures" immediately below) recorded in provenance, never because
  its latency/memory looked unusually high or low.
- **Failures:** a case whose provider call failed (`provider_failure`, `outcomes.py`) or that
  used `capture_raw_values_for_controlled_experiment` in a way that perturbs the measured
  window is reported with its own outcome flag, excluded from performance means with that
  exclusion stated in the summary (e.g. `provider_failure_count`, already tracked by
  `TreatmentSummary`) — never silently folded into "successful" timing statistics, and never
  silently dropped without a visible count.

### 7.5 No manufactured absolute threshold

No absolute latency/CPU/memory/volume threshold is frozen, for the same reason as §6.4: the
pilot's scale and FakeProvider's non-representativeness of real network/compute conditions
cannot justify one. These signals stay **secondary/operational** — useful for regression
detection between runs of the *same* configuration, and for relative treatment comparison —
until an external basis exists (a real deployment's actual latency budget, once a real provider
and realistic load are available). This is a rule about interpretation procedure, frozen now;
the threshold itself, if one is ever justified, arrives in a later protocol version.

### 7.6 `total_ms` is not the scientific latency metric

The advisor demo UI (T20/T21's HTTP API / Next.js surface) reports a `total_ms`-shaped
figure for user-facing responsiveness feedback. **`total_ms` is a product/UX metric, not the
scientific latency metric this protocol governs.** It may include UI-side overhead, network
round-trip to the browser, or a different measurement boundary than
`stage_timings.pipeline_total_ms`. Any scientific latency claim must cite the runner's own
`stage_timings`/`ProviderCallMetrics` fields (§7.1), never the UI's `total_ms`, even when the
two numbers happen to be close in a given run.

## 8. Primary B3→B4 comparison

Two genuinely different comparisons exist in the current evidence and this protocol keeps them
labeled separately rather than merging them into one claim.

### 8.1 Main frozen-corpus pairwise (`hr-v1`) — **secondary/historical**

The 13-case `hr-v1` B3→B4 pairwise (`summary_b3_to_b4.json`,
`aggregation.summarize_b3_to_b4`) is retained as **historical pilot evidence**, labeled
secondary for governance claims specifically because of a fact scoped to `hr-v1`'s own,
unextended policy document: under `hr-v1` *only*, `docs/hr-policy-matrix.md`'s "Inventory"
measured that `purpose`×`salary` is the *only* dimension/category pair that varies the
resolved disclosure action at all — under `hr-v1`, `requester_role` and `provider_class` are
"architecturally supported but experimentally inert for disclosure action". This finding is
**not** a general claim about `requester_role`/`provider_class` — it describes only what
`hr-v1`'s specific rule set happens to encode, and it is exactly the gap `hr-v2`/`hr-v3` were
designed to fill (§8.2 below), where those same two dimensions were deliberately given
governance rules that *do* change the resolved action (`docs/hr-policy-matrix.md`'s
`hr-v2` cell-by-cell table). A same-context B3-vs-B4 comparison under `hr-v1` mostly reflects
B4's *hard* policy actions overriding B3's task-aware choice for
`employee_name`/`department`/`salary` (`docs/milestone-2-pilot.md`: "B4 is more exposing than
B3 in 9/13 cases... In `hr-v1`, `employee_name` and `department` include hard policy actions
that can override B3's task-aware minimization"), not an isolated single-dimension governance
effect — which is the separate reason `hr-v1`'s own pairwise is secondary/historical here,
independent of and in addition to `hr-v1`'s narrower policy-dimension coverage.

### 8.2 Primary contextual governance comparison (`hr-v2`/`hr-v3`) — **primary**

The primary comparison for any claim about *which contextual dimension* changes B4's resolved
disclosure action is the existing targeted matrix
(`experiments/contextual_matrix.py`, `CONTEXTUAL_MATRIX_SPECS`), each varying exactly one
`GovernanceContext` dimension while holding every other field — including `text`/`task` —
identical. Verified against `docs/hr-policy-matrix.md` and the pilot's own
`contextual_matrix.json`, these five cells are frozen as the primary set, with `permission_
changed: true` confirmed for every one of them in the M2 artifact
(`artifacts/experiments/hr/v1/13198a3b95bd49b88a62f591f3da1224/contextual_matrix.json`):

| # | Spec name | Dimension | Base case / category | Cells compared | Label |
| --- | --- | --- | --- | --- | --- |
| 1 | `purpose_salary` | `purpose` | `hr_salary_analysis_001` / `salary` | `team_summary` vs `salary_analysis` (both `hr-v2`) | **Primary** |
| 2 | `requester_role_salary` | `requester_role` | `hr_salary_analysis_001` / `salary` | `hr_viewer` vs `hr_analyst` (both `hr-v2`, `purpose=salary_analysis`) | **Primary** |
| 3 | `requester_role_department` | `requester_role` | `hr_department_aggregation_001` / `department` | `hr_viewer` vs `hr_analyst` (both `hr-v2`) | **Primary** |
| 4 | `provider_class_employee_name` | `provider_class` | `hr_team_summary_001` / `employee_name` | `internal_llm` vs `external_llm` (both `hr-v2`) | **Primary** |
| 5 | `policy_version_compensation_review` | `policy_version` | `hr_salary_analysis_002` / `salary` | `hr-v2` vs `hr-v3`, `purpose=compensation_review` implied by the base case | **Primary** |

Each spec is single-dimension by construction (`experiments/contextual_matrix.py`'s own
`_ctx`/`_LIFECYCLE_IDENTIFIERS` convention holds every non-varied field, including lifecycle
identifiers, byte-identical on both sides — see that module's docstring for why the lifecycle
identifiers specifically must also be held constant, not just the dimension under test). All
five are labeled **primary** — none is demoted to secondary or exploratory — because
`docs/hr-policy-matrix.md`'s own "Identifiability guarantee" section already pins, as
independently failing tests (`tests/test_hr_policy_matrix.py`, section 2), that each dimension
has at least one cell where the resolved action or allowed-action space genuinely differs when
only that one dimension changes. There is currently no *exploratory* (i.e., not yet frozen as
identifiability-tested) contextual cell in the matrix to report separately.

This list is frozen now, before any future B0–B4 batch's results are inspected. A future batch
must not add, remove or substitute a cell in this table based on which cells looked most
favorable to a treatment; adding a **new** dimension or cell (e.g. a `domain` cross-cut, or a
`requester_id`-scoped override, both explicitly out of scope per
`docs/hr-policy-matrix.md`'s "Requester-specific overrides remain supported... but are outside
the initial primary matrix") requires a new protocol version, following the same
identifiability-guarantee discipline `hr-v2`/`hr-v3` already established.

### 8.3 How the two are reported together

Any report presenting B3→B4 results states both, explicitly labeled: "the main `hr-v1`
pairwise (secondary/historical, dominated by hard policy overrides) vs. the five primary
`hr-v2`/`hr-v3` contextual cells (primary, isolating one governance dimension each)". Neither
is silently omitted in favor of the other, and neither stands in as evidence for what the other
measures.

## 9. Provider

### 9.1 FakeProvider — valid uses

`FakeProvider` (`providers/fake.py`) is valid, without qualification, for:

- development, TDD and deterministic reproducibility (`generate` is a pure function of
  `request.payload`/`request.task`, byte-for-byte reproducible);
- plumbing/integration validation (the provider boundary, audit record, timing/volume
  instrumentation all exercise correctly regardless of what the provider itself does);
- disclosure evaluation that does not depend on real-LLM semantics — conformance, exposure,
  binary/level-sensitive unnecessary disclosure, reconstruction, detector scoring, and the
  information-sufficiency utility proxy (§6.3) are all valid under FakeProvider because they
  score the *disclosure-controlled payload*, not the provider's actual answer.

### 9.2 FakeProvider — invalid uses

`FakeProvider` **cannot alone** support any claim about:

- real-LLM utility/answer correctness (it never computes a real answer at all);
- token consumption (it has no tokenizer or usage accounting);
- real provider/provider-class behavior (a real `external_llm`/`internal_llm` boundary may
  behave differently from FakeProvider's uniform stand-in);
- real-provider latency (`FakeProvider`'s latency reflects in-process Python execution, not
  network/model inference time);
- monetary cost (no real pricing applies).

Any report citing one of these must use a real-provider run (T22) and must not average or
otherwise blend a FakeProvider figure into a real-provider figure for the same metric.

### 9.3 Requirements for an authoritative (real-provider) run

Before any run is treated as authoritative for the claims in §9.2, freeze and record, per
batch, in provenance (§13):

- `provider_class` (the `GovernanceContext.provider_class` value the batch's cases declare —
  `internal_llm`/`external_llm`, as already modeled);
- `provider` (the concrete adapter/vendor implementing the `Provider` protocol);
- `model_id`;
- `model_snapshot`/version, when the vendor exposes one (mirrors
  `ProviderCallMetrics.model_id`/`model_snapshot`, already part of `RunIdentity`);
- decoding configuration: sampling strategy, `temperature`, `max_tokens`, and any other
  generation-affecting parameter (mirrors `FakeProvider.decoding_config`'s existing shape —
  `{"temperature": ..., "max_tokens": ..., "sampling": ...}` — a real adapter must expose the
  same shape of configuration, not a narrower one);
- retry policy (attempts, backoff, what counts as retryable);
- timeout (the native client/transport timeout, in addition to the shared boundary's
  caller-side deadline — `docs/experimental-design.md`'s existing requirement, repeated here
  because it is a provenance field, not just an implementation note);
- run date/configuration (non-sensitive timestamp, environment/config identifier).

T22 / Issue #30 implements the real-adapter surface these fields describe; this protocol
freezes the requirement now so T22's adapter has a fixed contract to satisfy, rather than T22
inventing its own provenance shape independently.

### 9.4 No silent fallback

**An authoritative run must never silently fall back** to `FakeProvider`, to B0, or to a
different provider/model than the one frozen for that batch — for example on a transient
provider error, a timeout, or a missing credential. A failure in this situation is recorded as
a `provider_failure` outcome (already modeled — `CaseOutcomeFlags.provider_failure`,
`AuditRecord.provider.failed`) for that case, never silently retried against a different
provider class and then reported as if the frozen provider had answered. If a batch needs a
fallback behavior for operational reasons (e.g. a demo UI degrading gracefully for end users),
that fallback path must be excluded from, or clearly flagged out of, any confirmatory
scientific report — it is a product-availability concern, not a scientific one
(`docs/experimental-design.md`'s "Non-scientific integration surfaces").

## 10. Analysis plan

### 10.1 Design

**Paired.** The same document/task passes through every treatment being compared (B0–B4, or
the relevant adjacent subset) — this is already how the runner executes a batch
(`runner.run_pilot` runs every case through every treatment) and how comparisons are computed
(`aggregation.summarize_pairwise`/`summarize_b3_to_b4` match results by `case_id` via
`_matched_pairs`, never an unpaired/cartesian comparison). This protocol freezes that the
paired structure is preserved for any future batch's analysis — an unpaired comparison (e.g.
averaging one treatment's results from one corpus subset against another treatment's results
from a different subset) is not a valid substitute.

### 10.2 What is reported, per comparison

- **per-treatment statistics** — `TreatmentSummary` (`aggregation.summarize_treatment`):
  counts, rates and means already implemented and covering conformance, the **binary**
  unnecessary-disclosure/exposure metric (§4.2), utility, reconstruction, policy outcomes,
  detector scores and performance (§7). This is not the whole of §4: the runner also already
  contains `aggregation._exposure_rank_sum`, separate rank-based logic used only to compute
  `B3ToB4CaseComparison.exposure_direction` for the B3→B4 pairwise (§8), which is a per-case
  ordinal comparison, not a corpus-level metric. **The primary ordinal/cumulative exposure
  metric (§4.3) is frozen by this protocol but is not yet aggregated by `TreatmentSummary`** —
  see §4.3's "Requirement for future execution". This document must never be read as implying
  §4.3's metric is already computed by the current runner;
- **paired differences** — per matched case, the two treatments' own already-independently-
  computed values placed side by side (`PairwiseSummary`, `B3ToB4CaseComparison`'s
  `exposure_direction`/`utility_direction` fields: `"b4_less"/"b4_more"/"same"/"incomparable"`
  for exposure, `"b4_worse"/"b4_better"/"same"/"incomparable"` for utility) — never reduced to
  a single aggregate difference without the per-case direction breakdown alongside it;
- **per-document distribution** — every case's full `to_safe_dict` result remains in
  `results.jsonl`; a summary number is always traceable back to the individual cases behind
  it. No report may present only `summary_by_treatment.json`/`summary_pairwise.json` without
  making `results.jsonl` (or an equivalent full per-case table) available alongside it;
- **per-domain handling** — HR and Contracts (once frozen) are reported as separate domains,
  never pooled into one combined rate; a domain-level finding is scoped explicitly to that
  domain and is not generalized to "B0–B4 in general" without a second domain's confirmatory
  result to support that generalization;
- **primary vs secondary metrics** — labeled explicitly per §4 (ordinal/cumulative exposure
  primary, binary secondary — recoverable as its first threshold, §4.3) and §8 (contextual
  matrix primary, `hr-v1` pairwise secondary/historical) in every report, not left for a reader
  to infer;
- **uncertainty-interval / inferential-statistics procedure** — none is computed at
  pilot/small-N scale (see §10.3). **No specific inferential method is pre-selected by this
  protocol** — not a bootstrap, not a normal-approximation interval, not any other procedure.
  If a future round's scale is ever judged to justify confidence intervals, hypothesis testing,
  significance testing or any other statistical inference, the exact procedure must be defined
  and frozen in a new protocol version (`post-pilot-v2` or later) **before** that batch's
  results are inspected, per §10.3 — the same freeze-before-inspection discipline §1/§11
  already require for every other methodological choice, applied here to the choice of
  inferential method itself;
- **individual results and distributions stay auditable** — this protocol's own instruction:
  do not reduce everything to one mean. Every mean reported under §4/§6/§7 is reported
  alongside its own N and, where feasible, its per-case source values.

### 10.3 Hypothesis testing and small-sample handling

**No significance test is run at the current or near-term sample size.** `corpus/hr/v1` has 13
cases; even a frozen Contracts held-out corpus of comparable initial scale would not support a
defensible parametric or even most nonparametric hypothesis tests without an unacceptable risk
of either false confidence (an underpowered test failing to reject, misread as "no effect") or
manufactured significance (multiple comparisons across many categories/metrics without
correction). This mirrors `docs/experimental-design.md`'s existing "no sophisticated
statistical inference at pilot N" rule and `aggregation.py`'s own module docstring
("Deliberately descriptive only... never a significance test or confidence interval").

**No specific inferential procedure is frozen by this document, and none may be selected after a
future batch's results already exist.** This section is not merely "no test has been run yet" —
it is a rule about *when* a method may ever be chosen: choosing a bootstrap, a
normal-approximation interval, a specific hypothesis test, or any other inferential procedure
*after* seeing what the data look like is exactly the kind of post hoc selection this protocol
exists to prevent, even when the choice looks technically reasonable in isolation (e.g.
"the metrics are rates/ranks, so a nonparametric method fits better" is still a choice made with
the data in view once the corpus that would supply it already exists).

If a future round's scale is judged to justify statistical inference at all, the exact procedure
(which test or interval method, against which specific pre-registered comparison, with which
stated assumptions and correction for multiple comparisons) must be defined and frozen in
`post-pilot-v2` (or a later version) — **before** the batch that would supply its data is run —
following §1's freeze-before-inspection discipline. At minimum, before a future protocol version
freezes such a procedure it must address, for each comparison the procedure would cover:

1. the comparison and its metric are specified in that frozen protocol version **before** the
   batch that would supply the data is run;
2. the sample size is itself chosen (or at least assessed) for the intended procedure's power,
   not simply "however many cases the corpus happens to have";
3. the procedure's assumptions (independence of paired differences across cases, the metric's
   distributional shape) are stated and checked in that frozen version, not assumed by default.

Until a future, independently frozen protocol version satisfies this, every reported difference
in this protocol's scope — including under `post-pilot-v1` — is descriptive (a rate, a
proportion, a count, a per-case direction breakdown) — never accompanied by a p-value,
confidence interval, bootstrap estimate or "statistically significant" claim. This is a
**ceiling**, not a promise that a later, larger batch will add inferential statistics; it exists
to prevent both a significance ritual the corpus size cannot support and a post hoc choice of
inferential method after a batch's results are already visible, per the brief's explicit
instruction.

### 10.4 Failure handling in the analysis

A case whose execution failed in a way not modeled by any of §6/§7's outcome flags (an
unhandled exception during `execute_case`, for instance) is excluded from every summary
statistic for that case/treatment and reported as a distinct failure count in the batch's
manifest/summary — never silently dropped without a trace, and never imputed with a
placeholder value.

## 11. Anti-tuning rule (normative)

Once a run is classified `held_out_confirmatory` (§1), it is **forbidden** to adjust, in
response to that run's own results:

- detection rules/categories;
- necessity-assignment rules;
- policy documents (any `*-vN.yaml`);
- a treatment's implementation (B0–B4);
- generalization strategies/bands;
- the oracle (expected spans/actions/answers/reconstruction expectations);
- a task's text/instruction;
- a metric's definition or formula (§4/§6/§7);
- an interpretation threshold or rule (§6.4/§7.5);
- an aggregation procedure (§10);
- the statistical/descriptive analysis procedure itself.

If, after inspecting a held-out confirmatory round's results, the project determines that one
of the above genuinely needs to change (a real defect is found, a metric turns out to be
unmeasurable as specified, a category is missing): the required response is, in this exact
order —

1. **record the change** — what was found, and why it requires a change, in a docs/ record
   (an ADR, an implementation-status.md entry, or a new protocol version's own change log —
   never only in a commit message or PR description);
2. **reclassify the observed round as `pilot_development`** — its results remain visible and
   usable as development evidence, but permanently lose confirmatory status; this
   reclassification is never reversed;
3. **version the changed protocol/configuration** — a new protocol document (`post-pilot-
   vN+1`) if the change touches this document's own content, or a new corpus/policy version
   (`hr/v2`, `hr-v4`, `contracts/v2`, …) if the change touches frozen experimental material,
   following each artifact's own existing freeze-and-version convention
   (`corpus/hr/v1/README.md`'s freeze rule is the precedent for a corpus; this document's §0 is
   the precedent for the protocol itself);
4. **create a new, independently frozen held-out round** — under the new version, before any
   of its results are inspected, satisfying §1's full checklist again from scratch. The
   previous held-out round's data does not get "topped up" or reused as part of the new
   held-out set; a truly new held-out sample is required, or the new round remains development
   evidence too.

Skipping any of these four steps — most commonly, "fixing" something and quietly re-running the
same nominally-held-out corpus — invalidates the confirmatory claim regardless of how the
fixed run then performs.

## 12. Known pilot divergence (preserved, not fixed)

Verified against the current repository (`scripts/report_b3_corpus_divergence.py`, run at
freeze time): **55/56 spans converged** between B3's actual decisions and the frozen
`corpus/hr/v1` oracle's acceptable-action sets (the script's own denominator excludes spans
belonging to the three `medical_or_prohibited_block` cases, whose oracle expects the whole case
to block rather than naming a per-span acceptable action — 71 total annotated spans minus those
excluded leaves 56 scored). The one remaining divergence:

- **case/span:** `hr_salary_analysis_003` / `salary`;
- **B3's actual action:** `GENERALIZE`;
- **oracle's acceptable action:** `PRESERVE` only;
- **conformance outcome:** `nonconformant`;
- **utility consequence:** `indeterminate` (reason `generalized_band_ambiguous` — the
  generalized band straddles the case's own stated reference figure, per `utility.py`'s
  `_band_is_decidable` rule), scored as a **separate**, independent utility outcome — never
  fused into the conformance divergence itself;
- **B4 reproduces the identical divergence** under `hr-v1` (`policy_restricted`,
  `impossible_under_policy` and `policy_block` all `False` for this case), confirming the cause
  is task-analysis behavior, not a policy effect.

This is pinned as a real regression test today
(`tests/test_experiments_hr_salary_analysis_003_regression.py`) and this protocol adds nothing
new here — it records the fact, confirms it still holds at freeze time, and states explicitly
that it is **pilot evidence of a genuine analyzer/oracle disagreement, not a bug**: §5/§11
forbid tuning the analyzer's indicator tables, the oracle's acceptable-action set, or the
corpus's reference figure to force `56/56` convergence. Any future PR that makes this specific
case converge, without an accompanying record under §11's four-step change procedure, violates
this protocol.

## 13. Provenance

### 13.1 What already exists and is reused (not renamed)

Every batch executed under this protocol must record at least the fields the runner already
produces, using the runner's own field names — this protocol does not introduce a parallel
naming scheme:

| Requirement | Existing field |
| --- | --- |
| Schema version (result shape) | `RunIdentity.schema_version` (`run_identity.SCHEMA_VERSION`) |
| Dataset/corpus version | `RunIdentity.corpus_version` |
| Dataset classification | `RunIdentity.run_classification` |
| Policy version | `RunIdentity.policy_version` |
| Treatment / code revision | `RunIdentity.treatment_code`, `RunIdentity.treatment_version`, `RunIdentity.task_aware_baseline_version` (frozen commits, per treatment — never conflating B3's and B4's own commits, per `run_identity.py`'s documented PR #35 fix) |
| Contextual matrix cell (B4 only) | `RunIdentity.matrix_cell` |
| Provider class/model/config | `RunIdentity.provider_name`, `provider_model_id`, `provider_model_snapshot`; `manifest.json`'s `reproducibility.decoding_config` |
| Non-sensitive run/execution id | `RunMetadata.experiment_run_id` (shared per batch), `RunMetadata.case_execution_id` (unique per execution) — both opaque UUIDs, never a sensitive identifier |
| Non-sensitive timestamp | `RunMetadata.generated_at` |
| Artifact bundle version | `artifacts.ARTIFACT_FORMAT_VERSION` |
| Contextual-matrix spec version | `contextual_matrix.CONTEXTUAL_MATRIX_VERSION` |

### 13.2 Newly required for this protocol

Two fields this protocol requires that the runner does not yet emit — **marked here as a
requirement for future execution**, not implied to already exist:

- **`protocol_id`** — the frozen protocol version (`post-pilot-v1`, from
  `experiments/post_pilot_protocol.CURRENT_PROTOCOL_ID`) governing the batch's metrics,
  thresholds and comparison procedure. Should be added to `manifest.json`'s
  `reproducibility` mapping (a free-form mapping already designed to carry exactly this kind
  of caller-supplied provenance — see `artifacts.write_pilot_artifacts`'s own docstring) the
  next time a batch is run for a confirmatory purpose, and is good practice for any
  development batch run after this protocol exists.
- **`oracle_version`** — an explicit identifier for which revision of the oracle a batch was
  scored against. Today the oracle's version is implicit in `corpus_version` (the oracle lives
  inside the same versioned corpus directory as the input), which is sufficient while oracle
  and input are versioned together one-to-one; if a future corpus separates oracle revisions
  from input revisions (e.g. correcting an oracle label without touching `input.text`), an
  explicit `oracle_version` field becomes necessary and must be added before that split is
  used for a confirmatory run.
- **`parser_ingestion_version`** — required once T12/Docling is in use (§3): which
  parser/ingestion path produced the normalized text a batch scored. Not applicable to HR v1
  (hand-authored plain text, no parser stage), so not present in the M2 manifest; required for
  any Contracts batch that goes through Docling.

### 13.3 No-leak requirement (restated, not new)

Every provenance field is an identifier, version string, category name, count or
classification label — never a sensitive value, a payload, a pseudonym/original mapping, or a
`requester_id`. This is not a new rule: `CLAUDE.md`'s no-leak invariant already covers it, and
`case_result.to_safe_dict` already drops `audit.raw` unconditionally and never includes a raw
value. This protocol adds one specific instance of the general rule: **no publicly reproducible
hash counts as safe provenance** (`CLAUDE.md`: "hashing content is not anonymizing it") — the
existing `audit.py` HMAC hashes are keyed per-process specifically so they are not
dictionary-reversible from outside that process's trust boundary
(`case_result.py`'s own documented rationale for excluding them from
`deterministic_key`); provenance recorded for a confirmatory batch must never substitute a
plain (non-keyed) hash of sensitive content as if it were a safe identifier.

## 14. Scientific order

The frozen execution order after T23, correcting Issue #36's original follow-up comment (which
placed T24 immediately after T23 — outdated once T12 was recognized as a representation-
stability prerequisite for a Contracts corpus):

```
T23 (this protocol)
  → T12 (Docling / normalized-representation ingestion, stabilizing §3's canonical path)
    → Contracts domain extensions (categories, policies, generalization strategies, tasks —
       implemented in the shared core, per §2)
      → T24 (Contracts v1 held-out corpus/oracle frozen, per §1/§2, then inspected)
        → next confirmatory B0–B4 batch
```

**T22 (real provider) proceeds in parallel** with T12 and the Contracts domain extensions — it
is required before any *authoritative* utility/token/cost claim (§9), but it neither gates nor
is gated by T12 stabilization or the Contracts corpus/oracle freeze; Contracts
categories/policies/oracle can be defined and confirmatorily frozen against FakeProvider first,
exactly as HR's B3/B4 development did.

**T12 itself is not parallel with the Contracts *confirmatory* freeze.** Per §2, only
preliminary, representation-independent Contracts work (taxonomy, domain analysis,
requirements) may proceed alongside T12; the confirmatory freeze of Contracts corpus, oracle
and canonical representation requires T12 to have stabilized first. §2 is the authoritative
statement of this rule; this section restates only the resulting order, not a separate rule.

This section supersedes Issue #36's original follow-up-comment ordering for this one point; the
comment's other content (the Contracts-transition checklist) is preserved and elaborated in §2.

## 15. Enforcement summary

This protocol is deliberately narrative where narrative is sufficient, and backed by a small,
targeted set of automatic checks where drift would otherwise be silent:

- `src/adaptive_disclosure_gateway/experiments/post_pilot_protocol.py` — a closed registry of
  frozen protocol ids (`FROZEN_PROTOCOL_IDS`), mirroring `RunClassification`'s existing
  closed-set treatment, so a manifest recording an unregistered/misspelled `protocol_id` fails
  fast rather than silently passing;
- `tests/test_post_pilot_protocol.py` —
  - pins that `CURRENT_PROTOCOL_ID` can never silently drift from this document's own
    `protocol_id`/`status` front matter (a drift test, the same pattern already used elsewhere
    in this repo to keep UI copy and wire schemas from diverging, applied here to protocol
    identity instead);
  - pins, as a real regression, that the historical binary unnecessary-disclosure metric
    (§4.2) still counts `PSEUDONYMIZE` as transmitted — the exact M2 finding this protocol is
    required to preserve rather than silently redefine.
- the existing `tests/test_corpus_oracle_isolation.py` and
  `tests/test_experiments_hr_salary_analysis_003_regression.py` continue to enforce §5 (ground
  truth isolation) and §12 (the known divergence) respectively; this protocol relies on them by
  reference rather than duplicating them.

No new framework, scoring module or runner infrastructure is introduced by T23. The
ordinal/cumulative primary metric (§4.3) is specified formally here; its implementation in
`experiments/aggregation.py` is explicitly deferred to the next task that executes a batch
under this protocol.
