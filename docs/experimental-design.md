# Experimental design — B0–B4

This document defines the controlled comparison across the frozen treatment sequence:

**B0 — Direct → B1 — Static Sanitization → B2 — Reversible Pseudonymization → B3 — Task-aware → B4 — Policy-governed.**

The identifiers `b0`–`b4` are frozen. Implementation status is tracked in [`implementation-status.md`](implementation-status.md). Factual M2 pilot results are recorded separately in [`milestone-2-pilot.md`](milestone-2-pilot.md).

## Treatment definitions

### B0 — Direct

Unsafe control treatment. The original input is sent without disclosure-control transformation. Detection/scoring may still be executed externally by the evaluation harness for outcome comparison, but that work is not part of B0 treatment latency.

### B1 — Static Sanitization

Detected sensitive information is transformed by a fixed, task-independent static mapping. No task-awareness participates in action selection.

### B2 — Reversible Pseudonymization

Retains B1's task-independent/static behavior while adding reversible local pseudonymization, vault isolation and authorized reconstruction. Pseudonym/vault/reconstruction behavior is the reference mechanism reused by B3/B4.

### B3 — Task-aware

Adds task-aware minimization while retaining B2's reversible mechanism.

Frozen pilot semantics:

- task analysis is deterministic and implemented behind a replaceable interface;
- the analyzer receives only the task/case input, never ground-truth labels;
- B3 uses a **generic fixed action space per category/type**;
- that generic action space is independent of `domain`, `purpose`, `requester_role`, `provider_class` and contextual `policy_version`;
- task relevance chooses the least-disclosing useful action inside that generic space;
- ambiguous exact-value binding is conservative and must not widen disclosure.

B3 frozen implementation commit: `31bce08b7ea6a5c905f7a20bbb4bb99a05682bab`.

This design allows B2→B3 to isolate task-awareness.

### B4 — Policy-governed

B4 retains B3's task analyzer, reversible pseudonymization, vault, reconstruction and provider boundary, but adds explicit contextual organizational policy constraints.

Policy resolves the permitted action space first. Task-awareness may then minimize only within that space and can never expand permission.

Primary contextual dimensions available to the experiment are:

- `domain`;
- `purpose`;
- `requester_role`;
- `provider_class`;
- `policy_version`.

Requester-specific overrides remain supported by the architecture but are outside the initial primary matrix. Pseudonym scope remains governed separately.

The frozen HR contextual policy matrix is versioned through `hr-v2` / `hr-v3`; the original HR corpus remains on frozen `hr-v1`.

B4 frozen implementation commit: `5abea8514fa10ac64b9bc3714bbfd3f18682f713`.

## Pairwise causal comparisons

| Comparison | Variable isolated |
| --- | --- |
| B0 → B1 | Presence of static local disclosure control vs. direct disclosure. |
| B1 → B2 | Reversibility/local reconstruction while static task-independent behavior is otherwise retained. |
| B2 → B3 | Addition of task-aware action selection while the reversible mechanism remains constant. |
| B3 → B4 | Addition of explicit contextual organizational policy constraints while task-awareness/reversibility remain constant. |

For B3→B4, a claim about a contextual dimension is only valid when the compared cells actually change the resolved policy permission/action while all other relevant dimensions are held constant.

## Controlled corpus and ground truth

### Phase A — HR pilot

Completed and frozen as `corpus/hr/v1/` with 13 controlled cases.

Each case includes:

- `sample_id`;
- controlled text/document input;
- `GovernanceContext`;
- task/instruction;
- expected sensitive spans/categories;
- `policy_version`;
- expected action or acceptable action set per information unit;
- task-necessity annotation;
- expected answer or objectively verifiable property;
- expected `BLOCK_REQUEST` behavior where applicable;
- pseudonym/reconstruction expectation where applicable.

Any future modification to the frozen HR v1 schema/cases/labels must create a new corpus version rather than editing v1 in place.

### Task necessity oracle

Primary labels:

- `REQUIRED`;
- `NOT_REQUIRED`.

`HELPFUL` may be stored only as auxiliary annotation initially. It must not be mixed into the primary unnecessary-disclosure metric unless an objective criterion is later frozen.

Ground truth is strictly an evaluation oracle. Treatments do not receive it as privileged input.

### Minimum HR task families

The frozen HR pilot includes:

1. authorized salary analysis;
2. team summary/description where salary is not required;
3. aggregation by department without individual identity;
4. medical/prohibited-data cases that should block.

Each family uses a response or property that can be scored without relying only on subjective judgment whenever feasible.

### Phase B — broader validation

After the completed HR pilot:

1. **Contracts** is the second priority domain, especially for party-role, obligation, deadline, penalty and semantic-relation preservation;
2. **Accounting/Finance** is an optional third domain if the evidence and schedule justify it.

T12 / Issue #9 owns document-ingestion/normalization infrastructure. T24 / Issue #37 separately owns the Contracts evaluation corpus/oracle. Parser infrastructure must not be conflated with evaluation evidence.

## Development vs confirmatory evidence

The runner supports explicit run classification:

- `pilot_development`;
- `held_out_confirmatory`.

The completed HR M2 run is `pilot_development` because `corpus/hr/v1` was used while B3/B4 were developed and reviewed.

A later run may be labeled `held_out_confirmatory` only if its dataset/domain exposure, metric definitions, thresholds, provider configuration and analysis procedure were frozen before the comparative treatment results were inspected.

If a new domain requires treatment/category/policy/generalization extensions after cases have already been inspected at result level, that run must remain development evidence unless a fresh held-out corpus is created after those extensions are frozen.

## Held constant across treatments

Within a comparable run/batch:

- same case/input;
- same task text/scaffolding except disclosure-controlled transformed content;
- same detector for B1–B4 and the same detector output used for exposure scoring around B0;
- same provider model/snapshot/configuration when a real model is used;
- same reversible pseudonymization/vault/reconstruction implementation for B2–B4;
- same evaluation/scoring implementation;
- same corpus version;
- same policy version where the comparison requires it;
- same run configuration and environment as far as practical.

The evaluation harness must not introduce treatment-specific integration paths that change anything other than the treatment object/decision behavior under comparison.

## Provider strategy

### Development/integration

`FakeProvider` remains the deterministic default for TDD, offline integration and core reproducibility.

The M2 pilot uses FakeProvider and therefore measures a utility **information-sufficiency proxy**, not actual LLM answer correctness. That limitation is preserved rather than hidden.

### Authoritative utility/token/cost results

At least one real provider/model is required before making authoritative claims about:

- task utility with an actual LLM;
- provider tokens;
- external API cost;
- genuine provider/provider-class behavior.

For comparable B0–B4 batches, freeze and record:

- provider/model id;
- snapshot/version when available;
- decoding configuration;
- task/prompt scaffolding;
- provider class;
- date/run metadata;
- transmitted bytes/tokens where measurable.

Real network adapters must use native client/transport timeout or cancellation in addition to the caller-side deadline already present in the shared boundary.

T22 / Issue #30 implements the real adapter. T23 / Issue #36 freezes the provider/model/configuration used for confirmatory analysis.

## Metrics

### Policy/conformance

- policy violation rate;
- incorrectly widened permissions;
- correctly blocked impossible-under-policy cases;
- false/excessive blocks where relevant.

A task that cannot be executed externally because required information is forbidden by policy is **not** counted as an ordinary utility failure. It is reported as a separate correctly-blocked/non-executable policy outcome when B4 behaves as specified.

### Exposure

Available runner outputs include:

- representation exposure level (`REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE`);
- binary unnecessary disclosure;
- transmitted controlled-content bytes;
- detector precision/recall/F1.

The M2 pilot used the binary unnecessary-disclosure rate:

> transmitted sensitive units labeled `NOT_REQUIRED` / total sensitive units labeled `NOT_REQUIRED` present in the case.

This binary rate treats `PSEUDONYMIZE` as transmitted. The pilot showed that this can penalize B2 relative to B1 even when the representation is less revealing.

**Post-pilot rule (frozen by T23):** the M2 metric is not changed retrospectively. Per
`docs/research/post-pilot-protocol-v1.md` (§4), the binary rate is **preserved unchanged as a
secondary metric**; an ordinal/cumulative metric over the same ordered exposure ladder — exact
per-level proportions and the exceedance distribution `P(exposure >= PSEUDONYMIZE)` /
`P(exposure >= GENERALIZE)` / `P(exposure >= PRESERVE)`, plus ordinal statistics (maximum,
median, counts) — is frozen as **primary** for confirmatory analysis. It is an aggregation over
data the runner already produces, not a new scoring concept or new interval-scale assumption;
the binary secondary metric and the first threshold share a numerator but not always a
denominator. With `N = S + B + U` for all, scorable, blocked and unscorable `NOT_REQUIRED`
spans respectively, the binary rate is `T/N` and the threshold is `T/S`; reports include
coverage `S/N` and explicit `B`/`U` counts. They coincide when `B + U = 0` (or trivially
when `T = 0` and both denominators are non-zero), but are not unconditionally recoverable. A
mean of `level_rank` may still be reported as a secondary descriptive statistic, but only with
an explicit uniform-spacing caveat and never as the primary basis for a comparison. Its
implementation in `experiments/aggregation.py` is deferred to the task that executes the next
confirmatory batch.

### Utility

- task success rate;
- objective accuracy/error metrics where applicable;
- verifiable properties/rubrics for outputs that cannot be reduced to a single scalar automatically.

For FakeProvider M2 runs, utility is an information-sufficiency proxy based on whether the controlled payload retains the information required for the answer. Real-provider runs must score actual provider output under the frozen T23 procedure.

**Date-aware GENERALIZE decidability (frozen by Gate 6 / Issue #38, `post-pilot-v2`).** The
GENERALIZE decidability rule above was numeric-band-only; applied to a month-year date it was a
type error, not a calibration choice (a month-coarsened deadline was scored `answerable`
regardless of correctness). `docs/research/post-pilot-protocol-v2.md` freezes a separate,
date-aware rule (`DATE_UTILITY_REQUIRED_GRANULARITY`, `classify_generalized_date`) for
categories registered as date-shaped (`deadline`, required to the day); every other GENERALIZE
category kept the numeric-band rule unchanged at that point. `post-pilot-v1` is not edited;
`CURRENT_PROTOCOL_ID` moved to `post-pilot-v2`.

**Numeric-band GENERALIZE fidelity (frozen by Issue #85, `post-pilot-v3`).** The numeric-band
rule Gate 6 left unchanged (`salary`, `contract_value`, `penalty_amount`) checked only
*sufficiency* (can the band be resolved against a stated reference figure) and never *fidelity*
(does the band actually contain the case's own oracle value at all) — a wrong band could still
score `answerable` whenever no reference figure happened to fall inside it, and every band was
vacuously "decidable" with zero references (`all([])` is `True`).
`docs/research/post-pilot-protocol-v3.md` freezes `NUMERIC_BAND_UTILITY_CATEGORIES` and
`classify_generalized_band`, which check fidelity first: an invalid, inverted, degenerate or
non-containing band is `not_answerable` unconditionally, before any reference is even consulted;
sufficiency (the pre-existing comparison) is only reached once fidelity holds, and a band with no
stated reference is `indeterminate`, never vacuously `answerable`. Re-scoring both registered
corpora under the new rule changed zero category-, overall- or B3→B4-level rows (every numeric
oracle span in both corpora already sits inside its own generated band). `post-pilot-v1` and
`post-pilot-v2` are not edited; `CURRENT_PROTOCOL_ID` moved to `post-pilot-v3`.

**Structured numeric utility references (frozen by Issue #87, `post-pilot-v4`).** `post-pilot-v3`
left band *sufficiency* on the pre-existing free-text mechanism (`_reference_values`): a bare
`float` scanned from `input.text` outside any detected span, with no operator and no category
awareness. Two defects followed: a reference sitting exactly on a band's lower bound could not be
told apart from a strict "greater than" reading and a non-strict "at least" one (they have
different correct answers, §4 of `docs/research/post-pilot-protocol-v4.md`); and a reference
found in the text could be applied as a candidate for a numeric category it was never actually
about. `CaseOracle.utility_references` (`corpus/models.py`'s `NumericUtilityReference`/
`ReferenceOperator`, `corpus-case-schema-v3`, purely additive) replaces free-text extraction with
structured `(category, operator, value)` references, read only by `experiments/scoring/utility.py`
for evaluation purposes — never by a treatment, the detector, a policy or a provider. A new
function, `classify_generalized_band_against_references`, shares fidelity (steps 1–3) byte-for-byte
with the frozen `post-pilot-v3` `classify_generalized_band` and replaces only the sufficiency step
with the structured per-operator table (`greater_than`/`greater_than_or_equal`/`less_than`/
`less_than_or_equal`). Deliberately **no load-time coverage requirement** (an opted-in case whose
numeric-dependent category has no reference scores `indeterminate`/`generalized_band_no_reference`
at score time, not a schema violation) and **no lexical-match requirement, but semantic grounding
is required** (a reference's value need not appear textually in `input.text` — a canonical
`500000.00` may correspond to `R$ 500.000,00` or a prose statement of the same threshold in the
text — but every reference must correspond to a condition actually visible to the provider
(`CorpusCaseInput.text`/`task`), never an evaluation-only threshold invented solely to make a band
decidable; enforced as a Gate 7 authoring/audit requirement, not a scorer heuristic, since checking
semantic correspondence to prose is exactly the kind of judgment call this ticket declined to
automate — see `docs/research/post-pilot-protocol-v4.md` §3a/§3b). Protocol dispatch
(`SCORABLE_PROTOCOL_IDS`, `check_corpus_protocol_compatibility`) refuses to score a legacy oracle
(`utility_references is None`) under `post-pilot-v4` when it depends on a numeric category, and
separately refuses **any** opted-in oracle — an empty list included, not only a non-empty one —
under `post-pilot-v3` (an explicit but empty opt-in must never silently fall back to free-text
extraction). `corpus/hr/v1` and `corpus/contracts/v1` are neither edited nor scorable under v4, and
remain scored under `protocol_id="post-pilot-v3"` explicitly. `post-pilot-v1`, `-v2` and `-v3` are
not edited; `CURRENT_PROTOCOL_ID` is now `post-pilot-v4`. See
`docs/research/post-pilot-protocol-v4.md` for the full rule, the anti-tuning justification for the
fix's one case of *adding* credit relative to v3, and the item (c)/Unicode-`\d` findings moved to
their own issues rather than fixed here.

### Reconstruction

- reconstruction success rate;
- correct pseudonym→original association;
- unresolved references;
- collisions;
- unauthorized reconstruction attempts/outcomes.

### Performance/cost

Available from M2:

- treatment latency;
- provider latency;
- total pipeline latency;
- process CPU time;
- peak Python traced memory;
- disclosure-controlled transmitted bytes;
- total provider-request bytes.

Deferred to real-provider runs:

- provider tokens;
- estimated/actual external API cost.

## Measurement boundaries

### B0 timing

If detector/scoring is run around B0 for comparable exposure measurement, it must be measured outside B0 treatment latency. Shared evaluation overhead must not be silently attributed to Direct.

### Transmission/cost

Report disclosure-controlled payload contribution separately from task/prompt scaffolding. Total provider request volume may also be reported so absolute provider cost is not understated.

### CPU/memory

M2 records process CPU time and peak Python-traced allocation across the documented whole-pipeline measurement scope. These are lightweight portable proxies, not OS-level profiling/RSS claims.

## M2 pilot calibration and T23 freeze

No numeric utility-loss or overhead threshold was selected before M2.

That pilot occurred, and its observations informed — without determining post hoc from desired
treatment outcomes — the protocol candidate in PR #53:
`docs/research/post-pilot-protocol-v1.md` (`protocol_id: post-pilot-v1`, `status: FROZEN`).
While the PR is open, that front matter marks the candidate's immutable content; T23 is not yet
the authoritative completed gate.

The candidate freezes, before any confirmatory result inspection:

- metric primary/secondary roles (protocol §4);
- interpretation rules where a numeric threshold could not be justified from pilot-scale
  evidence, rather than an invented number (protocol §6.4, §7.5);
- B3→B4 primary contextual comparison procedure (protocol §8);
- provider/model/configuration requirements (protocol §9);
- dataset/run classification rules, including the Contracts transition gate (protocol §1–§2);
- statistical/descriptive analysis procedure (protocol §10).

After approval and merge, later results must be interpreted under that protocol rather than re-optimizing the rules. A
future methodological change creates `post-pilot-v2`; `post-pilot-v1` is never rewritten in
place.

## M2 methodological findings carried forward

The first pilot surfaced three explicit design decisions:

1. binary unnecessary disclosure vs representation-sensitive exposure;
2. main frozen `hr-v1` B3→B4 pairwise vs targeted `hr-v2/hr-v3` contextual governance comparisons;
3. FakeProvider development evidence vs real-provider authoritative measurement.

These findings do **not** invalidate M2 and must not trigger retroactive tuning of B3/B4 or the frozen HR corpus/policies.

The known B3 `hr_salary_analysis_003/salary` divergence also remains visible by design: conformance and utility are separate dimensions, and the analyzer is not tuned to the oracle after the fact.

## Non-scientific integration surfaces

The following are product/integration surfaces, not experimental treatments:

- CLI;
- HTTP API;
- MCP server;
- simplified Next.js audit/experiment UI.

They must call/consume the same core contracts and cannot define policy logic, treatment semantics or scientific metrics independently. M2's versioned safe result schema may be reused by these surfaces.

## Current implementation / planning status

Milestone 2 is complete. The next research phase is Milestone 3 / Issue #38.

Methodological gate: **T23 / Issue #36 — candidate frozen in PR #53; awaiting human review and
merge.** `docs/research/post-pilot-protocol-v1.md` becomes authoritative after that gate
completes. Scientific order after T23 (protocol §14):

```
T23 → T12 → Contracts domain extensions → T24 → next B0–B4 batch
```

T22 (real provider) proceeds in parallel with T12/Contracts/T24; it gates authoritative
utility/token/cost claims, not the Contracts corpus/oracle freeze itself.

T01 line/advisor selection remains a parallel academic track. T20/T21 remain non-blocking integration/product work.
