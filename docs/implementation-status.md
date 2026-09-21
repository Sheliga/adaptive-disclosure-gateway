# Implementation status

Last updated: 2026-09-21 — M3 Gate 6 / Issue #38 (date-aware GENERALIZE utility scoring,
`post-pilot-v2`) merged into `master` via PR #86 (merge commit `d1583f6`). M3 / Issue #85
(numeric-band GENERALIZE fidelity, `post-pilot-v3`) **merged into `develop` via PR #89** (merge
commit `7d3644e8e2bf9e1c903b21be753c5c999f127e66`), resolving the related defect Gate 6
deliberately left open. M3 / Issue #87 (structured numeric utility references, `post-pilot-v4`)
**merged into `develop` via PR #92** (merge commit
`dc2236bc81d16eac7a283edcd30a3ef2769c18ae`), resolving the two remaining Issue #85 §8 findings
that were not fixed by `post-pilot-v3` itself. M3 / Issue #93 (numeric amount format
stabilization end-to-end, `post-pilot-v5`) is now **in validation** in an open PR to `develop`
-- the pre-Gate-7 checkpoint resolving Issue #88 (Brazilian-formatted amount misparse) and
Issue #91 (non-ASCII-digit/trailing-newline scorer grammar defects). T30 / Issue #82 (guided
demo UX with progressive disclosure) merged to `master` in PR #83. T29 / Issue #72 (local Vault
Explorer for demo/debug) is now **in validation** in an open PR to `develop`. Issue #56
(Contracts domain extensions) **merged into `develop` via PR #59** (merge commit
`5a67c30daab68d06bbd16d1cf06433de97245910`), which freezes the Contracts categories, policies,
generalization strategies and relation semantics; T24 / Issue #37 (Contracts v1 corpus + frozen
oracle) is now **in validation** in an open PR to `develop`. T12 / Issue #9 Docling ingestion
merged into `develop` via PR #55 (merge commit `776e683a49818db35021bb62315dfc1ed7fb00ab`,
validated feature head `3c93f3297515c99c6fccd4c5e705f1e77cfada78`, real Docling 2.126.0
PDF/DOCX/XLSX validation); T23 post-pilot protocol remains merged into `develop` via PR #53; T21
fourth slice (pt-BR / English localization) completed and integrated into `master` via PRs
#51/#52 — T21/Issue #29 remains open for the remaining deliberately out-of-scope items.

This file tracks the current engineering/research state and execution order. Architectural decisions belong in ADRs; experimental definitions belong in `docs/experimental-design.md`; factual pilot results belong in `docs/milestone-2-pilot.md`; the frozen confirmatory-analysis protocol belongs in `docs/research/`; the parallel advisor-facing application plan belongs in `docs/advisor-demo.md`; historical PR/Issue descriptions remain in GitHub.

## Current phase

**Milestone 1 and Milestone 2 are complete on `master`.**

The project has moved from building the research treatments to **post-pilot methodological freeze and confirmatory-readiness**.

The canonical sequence is implemented and executable:

**B0 — Direct → B1 — Static Sanitization → B2 — Reversible Pseudonymization → B3 — Task-aware → B4 — Policy-governed.**

Milestone 2 closed via PR #35 / merge `027a2baead4a3cee35db23cb8d4b79005a3a75d0` after the frozen HR corpus, B3, B4 and the experiment runner were completed.

In parallel, the same Python implementation is now explicitly planned as the **reference application core for an advisor-facing interactive demo**. This application track does not change Milestone 3 gates.

## Milestone 2 — completed

Required scope:

- T09 / Issue #4 — frozen HR minicorpus + oracle ✅
- T07 / Issue #6 — B3 Task-aware ✅
- T08 / Issue #7 — B4 Policy-governed + contextual HR matrix ✅
- T10 / Issue #8 — reproducible runner + first B0–B4 HR pilot ✅

Milestone tracker: Issue #32.

### Frozen implementation / evaluation state

- `corpus/hr/v1/`: 13 controlled HR cases; frozen/versioned.
- `corpus/contracts/v1/`: 12 controlled Contracts cases; frozen/versioned; run classification `pilot_development`, decided before any result existed (T24 / Issue #37, in validation).
- corpus case-file schema: `corpus-case-schema-v2` (per-domain category/task-family registries plus the oracle's `obligation_relations`; additive, `corpus/hr/v1` files unchanged).
- B3 frozen implementation commit: `31bce08b7ea6a5c905f7a20bbb4bb99a05682bab`.
- B4 frozen implementation commit: `5abea8514fa10ac64b9bc3714bbfd3f18682f713`.
- B4 retains B3's task-aware baseline and adds contextual policy constraints.
- HR contextual matrix: `hr-v2` / `hr-v3`; original corpus cases remain on frozen `hr-v1`.
- experiment schema: `t10-experiment-runner-v3` (bumped by T22 / Issue #30: `ProviderCallMetrics` gained four provider-reported token-usage fields). The M2 HR and Contracts v1 artifacts on disk remain correctly labeled `t10-experiment-runner-v2` and were not rewritten.
- artifact bundle schema: `t10-pilot-artifact-bundle-v2`.
- final M2 pilot artifact: `artifacts/experiments/hr/v1/13198a3b95bd49b88a62f591f3da1224/`.

### Runner capabilities delivered

The experiment runner now provides, without sending ground truth into treatments:

- B0–B4 execution over the same case set;
- conformance/policy scoring;
- exposure representation levels;
- binary unnecessary-disclosure scoring;
- detector TP/FP/FN + precision/recall/F1 from the detector spans actually used by execution;
- utility information-sufficiency proxy for FakeProvider runs;
- reconstruction scoring;
- policy-restricted / impossible-under-policy / hard-block outcomes;
- stage-aware latency;
- provider/payload/request byte volume;
- process CPU time and peak Python traced memory;
- B3/B4 implementation provenance;
- B4 policy version/matrix-cell provenance;
- shared `experiment_run_id` plus per-execution ids;
- cross-process deterministic comparison without weakening audit HMAC security;
- safe machine-readable summaries and pairwise comparisons.

The final T10 branch reported 462 passing tests and clean Ruff checks before merge.

## M2 pilot classification

The HR result is **pilot/development evidence**, not held-out confirmatory evidence.

Reasons:

- `corpus/hr/v1` was used during B3/B4 development;
- FakeProvider does not produce real LLM task output, token usage or external API cost;
- the pilot is used to identify methodological decisions that must be frozen before authoritative analysis.

Do not describe M2 as proof that B4 outperforms other treatments.

## Post-pilot findings that now drive planning

Three methodological findings were carried forward without retroactively changing M2, and are
now addressed by the protocol merged into `develop` via PR #53:

1. **Binary unnecessary disclosure penalizes pseudonymization.** The binary rate counts `PSEUDONYMIZE` as transmitted, which can make B2 appear worse than B1 despite a lower representation exposure. **Candidate resolution:** preserve the binary rate unchanged as secondary and use an ordinal/cumulative primary family. With `N = S + B + U`, the binary rate is `T/N`, while the first threshold is `T/S`; reports include coverage `S/N` and explicit blocked/unscorable counts rather than claiming unconditional recoverability (protocol §4).
2. **The main HR B3→B4 pairwise uses `hr-v1`.** Contextual governance effects from `purpose`, `requester_role`, `provider_class` and `policy_version` are identified in targeted `hr-v2/hr-v3` matrix comparisons rather than the main frozen-corpus pairwise run. **Resolved:** the five `hr-v2`/`hr-v3` matrix cells are frozen as the primary B3→B4 comparison; the `hr-v1` pairwise is frozen as secondary/historical (protocol §8).
3. **FakeProvider is not evidence about a real provider.** It remains appropriate for deterministic TDD/pilot reproducibility but cannot support authoritative utility/token/cost or genuine provider-class behavior claims. **Resolved:** valid/invalid uses and the required provenance fields for an authoritative run are frozen, with an explicit no-silent-fallback rule (protocol §9).

The known B3 case `hr_salary_analysis_003/salary` remains intentionally visible: B3 selects `GENERALIZE` while the oracle accepts only `PRESERVE`. It is not tuned away (protocol §12; re-verified at T23 freeze time — 55/56 spans converged).

## Milestone 3 — active

Tracker: Issue #38 — **Post-pilot protocol freeze and confirmatory-readiness**.

### Required research path

Scientific order (frozen by T23, protocol §14 — corrects Issue #36's earlier follow-up comment,
which had placed T24 immediately after T23):

```
T23 → T12 → Contracts domain extensions → T24 → next B0–B4 batch
```

T22 (real provider) proceeds **in parallel** with T12/Contracts/T24: it gates authoritative
utility/token/cost claims (protocol §9), not the Contracts corpus/oracle freeze itself.

#### T23 / Issue #36 — freeze post-pilot methodology

Status: **merged into `develop` via PR #53**.
`docs/research/post-pilot-protocol-v1.md` (`protocol_id: post-pilot-v1`) retains
`status: FROZEN` and its immutable candidate date. It is the current post-pilot protocol
baseline for the M3 path on `develop`; `master` remains behind until the final feature
integration PR.

Frozen before any confirmatory analysis:

- primary (ordinal/cumulative) and secondary (binary, preserved unchanged) exposure/
  unnecessary-disclosure metrics, both computable from existing runner output; the primary
  metric is exact per-level proportions plus the exceedance distribution
  (`P(exposure >= PSEUDONYMIZE)`, `P(exposure >= GENERALIZE)`, `P(exposure >= PRESERVE)`),
  never a mean of ranks. The binary secondary metric shares the first threshold's numerator but
  uses all `NOT_REQUIRED` spans as its denominator; ordinal coverage and blocked/unscorable
  counts make the difference explicit —
  a mean of `level_rank` may still be reported, but only as an explicitly-caveated secondary
  descriptive statistic, never as the primary metric;
- interpretation of `PSEUDONYMIZE` relative to representation exposure — the primary metric
  reads the existing ordered ladder (`REMOVE < PSEUDONYMIZE < GENERALIZE < PRESERVE`,
  `experiments/scoring/exposure.py`) rather than redefining it, and preserves that ladder's
  ordinal (not interval) semantics;
- utility-loss and performance/overhead **interpretation rules** (no numeric threshold could
  be justified from pilot-scale evidence without reverse-engineering it from that evidence, so
  none was invented — see the protocol's §6.4/§7.5);
- primary B3→B4 contextual comparison procedure — the five `hr-v2`/`hr-v3` matrix cells
  (`purpose_salary`, `requester_role_salary`, `requester_role_department`,
  `provider_class_employee_name`, `policy_version_compensation_review`) are frozen as primary;
  the main `hr-v1` pairwise is frozen as secondary/historical (protocol §8);
- provider/model/configuration requirements for an authoritative run, plus the no-silent-
  fallback rule (protocol §9);
- development vs held-out/confirmatory labeling, including the Contracts transition gate
  (protocol §1–§2, with T12 stabilization required before the Contracts *confirmatory* freeze
  and T22 proceeding in parallel to both);
- statistical/descriptive analysis plan — paired, descriptive-only at current sample size, no
  significance ritual the corpus size cannot support, and no specific inferential method
  (bootstrap or otherwise) pre-selected for any future round (protocol §10).

T23 did not tune B3/B4, frozen HR policies, the frozen corpus or M2 artifacts to improve pilot
numbers. Two small support additions back the document: a closed protocol-id registry and
validator (`experiments/post_pilot_protocol.py`) whose runner/manifest integration is deferred,
and a regression test pinning that the M2 binary metric
still counts `PSEUDONYMIZE` as transmitted (`tests/test_post_pilot_protocol.py`). The
ordinal/cumulative primary metric's aggregation is specified formally in the protocol but its
implementation in `experiments/aggregation.py` is explicitly deferred to the task that executes
the next confirmatory batch; the runner today reports only the binary rate via
`TreatmentSummary`, plus separate existing rank-based logic
(`aggregation._exposure_rank_sum`) used only for the secondary/historical B3→B4 pairwise's
`exposure_direction`. That legacy rank sum assumes uniform spacing and is not a confirmatory
ordinal claim or this primary metric.

#### T22 / Issue #30 — real provider

Status: **implemented; in validation in an open PR to `develop`**.

An Anthropic Messages API adapter (`providers/anthropic_api.py`, `AnthropicProvider`) now
implements the existing narrow `Provider` protocol, behind a new optional `anthropic`
dependency extra. Operational reference: [`docs/provider-configuration.md`](provider-configuration.md).

Delivered:

- one real adapter on the unchanged `ProviderRequest(payload, task)` boundary, invoked only
  through `invoke_provider`;
- opt-in selection (`ADG_PROVIDER=anthropic`); **`FakeProvider` remains the default
  everywhere** — TDD, CI, offline development, deterministic regression and the
  pilot/development corpora are unaffected. **Fixed under review:** any other non-empty,
  unrecognized value (e.g. a typo) now raises `ProviderConfigurationError` instead of
  silently falling back to `FakeProvider`;
- native transport timeout on the SDK client, with the caller-side deadline
  (`invoke_provider`'s `timeout`) now **derived from it** on the real-provider path
  (`providers.caller_timeout_for_provider`, native timeout + a fixed, documented grace) rather
  than defaulting independently. **Fixed under review:** the default caller-side deadline
  (30s) was previously shorter than the default native transport timeout (60s) on the
  scientific/runner path (`execute_case`/`run_pilot`), so the caller could give up before the
  transport did; the live integration test's manual `+10s` workaround is now the shared,
  versioned helper every real-provider caller uses;
- a model-id allowlist (`settings.SUPPORTED_ANTHROPIC_MODEL_IDS`, currently just
  `claude-opus-5`, the default). **Fixed under review:** `AnthropicProviderConfig` previously
  accepted any `model_id` string, which would have let an unvalidated model silently inherit
  this adapter's "no sampling parameters" provenance claim; a model id outside the allowlist
  now raises `ProviderConfigurationError` at construction;
- `base_url` override **forbidden**. **Fixed under review:** a `base_url_overridden` boolean
  was insufficient provenance (two batches could both say `true` and still have hit different
  backends); any non-`None` `base_url` (including via `ADG_ANTHROPIC_BASE_URL`) now raises
  `ProviderConfigurationError` at construction, and `configuration_record()` states the fixed
  `base_url_policy` instead of a flag;
- no retry (`max_retries=0` pinned by test — the SDK retries twice by default) and no
  fallback of any kind, including the server-side `fallbacks` parameter, which is
  deliberately not enabled because a silent model switch would break the frozen-configuration
  requirement;
- real usage metadata (`input_tokens`, `output_tokens`, cache token counts) carried into the
  runner schema, `None` under FakeProvider so "usage unavailable" stays distinguishable from
  zero;
- `model_snapshot` recorded from the serving model or as the explicit
  `model_snapshot_unavailable` sentinel — never synthesized;
- a freezable configuration record (`AnthropicProvider.configuration_record()`) covering the
  protocol §9.3 fields, shaped for `artifacts.write_pilot_artifacts(reproducibility=...)`;
- runner integration through an optional `provider` argument on `run_pilot` /
  `run_case_for_treatment` — the smallest point that lets one controlled batch use one
  provider configuration.

Known limitation, recorded rather than worked around: `temperature`/`top_p`/`top_k` were
removed on current models and return HTTP 400, so **bit-exact decoding determinism is not
configurable**. `decoding_config` records `temperature: null` plus
`sampling_parameters_supported: false` rather than a fabricated `temperature: 0.0`; what is
frozen is `max_tokens`, thinking mode and `output_config.effort`.

Deliberately not delivered: no cost/pricing table (a report says *cost unavailable*), no
change to scientific scoring, and no reinterpretation of the FakeProvider
information-sufficiency proxy as real-response utility — protocol §6.3/§9.2 keep those
distinct, and resolving that is a later methodological step, not part of T22.

Live smoke test: **pending** — no credential was available in the implementing environment.
Every adapter path is validated offline against a fake SDK client, and the drift tests run
against the really installed SDK (`anthropic` 1.5.0) without network or credential.

Provider/model/scaffolding/decoding configuration must still be frozen under the T23 protocol
before confirmatory comparison; T22 delivers the readiness, not the freeze.

T22 is also consumed by the advisor-facing demo when available. FakeProvider remains sufficient to build/test the demo shell, but a real-provider mode is preferred before sharing the demo broadly with prospective advisors.

#### T12 / Issue #9 — Docling ingestion

Status: **merged into `develop` via PR #55** (merge commit
`776e683a49818db35021bb62315dfc1ed7fb00ab`, validated feature head
`3c93f3297515c99c6fccd4c5e705f1e77cfada78`, real Docling 2.126.0 PDF/DOCX/XLSX validation).
Issue #9 is closed.

Docling is ingestion infrastructure only. Keep a normalized internal document representation independent from Docling APIs and keep parser behavior constant across B0–B4.

Direct normalized text remains the canonical parser-independent control path. The T12 slice
extends the existing `NormalizedContent` ingestion boundary so direct text, UTF-8 text files
and Docling-backed document files all reach the core as project-owned canonical text with
parser/ingestion provenance.

**Delivered:** a generic, parser-independent ingestion/normalization boundary — canonical
`NormalizedContent.text`, project-owned `NormalizedBlock` / `ParsedDocument`, text/heading/table
structure with offsets where reliable, a replaceable `DocumentParser`, Docling isolated in
`application/ingestion.py`, uniform size limits with early rejection, no-leak-sanitized parser
exceptions, and the same normalized representation reused across B0–B4. The boundary also emits
`parser_name` / `parser_version` / `ingestion_version` provenance on `NormalizedContent`;
recording these fields for a comparable scientific batch is already governed by
`docs/research/post-pilot-protocol-v1.md` §13.2's `parser_ingestion_version` requirement, owned
by the task that runs that batch (T24 / Issue #37), not by T12 itself.

**Deliberately NOT delivered:** Contracts-specific semantic interpretation — party/role,
obligations, deadlines, penalties, amounts and the relation-preserving requirements later
scoring needs. That scope was split out to Issue #56 (Contracts domain extensions); T24 / Issue
#37 continues to own the Contracts corpus/oracle and the evaluation evidence.

#### Issue #56 — Contracts domain extensions

Status: **complete** — merged into `develop` via PR #59, merge commit
`5a67c30daab68d06bbd16d1cf06433de97245910`.

Freezes the minimum development-time Contracts domain support needed before the T24 corpus is
inspected at treatment-result level. `NormalizedContent.text` remains canonical and parser
behavior remains constant across B0–B4; Issue #56 does not create or freeze the Contracts v1
corpus itself — that remains T24.

**Freeze artifact:** [`docs/contracts-policy-matrix.md`](contracts-policy-matrix.md), alongside
`configs/policies/contracts-v1.yaml`. This follows the project's existing freeze pattern (a
policy `version:` string plus a prose matrix), the same one `docs/hr-policy-matrix.md` uses for
the HR pilot. It is authoritative for the frozen Contracts category set, detector behaviour,
policy actions, B3 action spaces, generalization strategies, relation semantics and the known
limitations T24 must build its corpus around.

Frozen category set (eight, of which `cnpj` and `cpf` were reused unchanged): `party_name`,
`representative_name`, `cnpj`, `cpf`, `bank_account`, `contract_value`, `penalty_amount`,
`deadline`. `obligation` and `confidential_clause` were deliberately dropped rather than
implemented — see the matrix for why. Obligation *assignment* is preserved structurally by the
detector's role-in-label / identity-in-value split plus the vault's per-value pseudonym
stability; no relation model was added.

Also fixed here: every policy model now rejects unknown keys, so an unimplemented governance
knob can no longer be silently dropped from a policy YAML (it fails the document closed
instead).

**Known non-semantic T24 change (now delivered):** `corpus/models.py` hardcoded an HR-only
category `Literal`, so a Contracts corpus could not be expressed. That was corpus schema work
owned by T24 / Issue #37, not treatment semantics, and was deliberately not implemented by
Issue #56. T24 delivered it as per-domain registries (`corpus-case-schema-v2`).

#### T24 / Issue #37 — Contracts v1 validation corpus

Status: **in validation** — implemented and under review in a PR to `develop`.

T24 is deliberately separate from both T12 and Issue #56 — the three-way split:

- T12 = document ingestion/normalization infrastructure (generic, parser-independent, merged);
- Issue #56 = development-time Contracts domain support (categories/policies/generalization strategies);
- T24 = frozen Contracts corpus/oracle and evaluation evidence.

If Contracts requires new categories/policies/generalization strategies, those extensions must be frozen (Issue #56) before a held-out corpus is inspected at treatment-result level, or the resulting run must remain development evidence.

**Delivered:** `corpus/contracts/v1/` — 12 synthetic cases across six task families, with
`SCHEMA.md` and `README.md` mirroring the HR corpus's structure and freeze rule; the
per-domain corpus schema extension (`corpus-case-schema-v2`); the oracle's new
`obligation_relations` field recording "who owes what to whom" in role terms, scoring-only and
pinned isolated both structurally and behaviorally; `scripts/run_contracts_v1_pilot.py`; and a
controlled B0–B4 execution over the corpus with `FakeProvider`, whose artifacts and freeze
record live under `artifacts/experiments/contracts/v1/`.

**Run classification: `pilot_development`**, decided by the project owner before the corpus
existed and before any B0–B4 Contracts result had been produced or inspected. This corpus is
therefore **not confirmatory evidence**. `contracts/v1` was subsequently authored, run under
B0–B4 and **inspected** — its results were read to validate end-to-end execution and to derive
the findings below. Per `docs/research/post-pilot-protocol-v1.md` §1 (the same rule that makes
`corpus/hr/v1` permanently `pilot_development`), held-out status turns on a dataset's *history*
relative to the treatments/metrics being judged, not on whether its files are currently
immutable — so `contracts/v1` is **permanently ineligible** for `held_out_confirmatory`. The
corpus and oracle are frozen and versioned regardless; that freeze preserves reproducibility
and lets it keep serving as development, regression, documentation and pilot evidence, but it
does not confer held-out eligibility. A future confirmatory Contracts round requires a newly
authored, independently frozen corpus not previously inspected against the evaluated
treatments/metrics.

**Post-hoc wording correction (no result changed).** The committed run manifest's
`reproducibility.run_classification_note` string
(`artifacts/experiments/contracts/v1/954ffae9f6e143d6af45e4842f6daef9/manifest.json`)
originally implied this corpus could still become a future held-out artifact; that wording was
corrected in this same PR to state the permanent-ineligibility position above. Only the note
string changed — the run id, every timestamp, every count, every result and
`run_classification` itself (still `pilot_development`) are byte-identical to the original run;
nothing was re-executed.

**Follow-up, documentation only (not implemented here).** Finding 1 below (the GENERALIZE
decidability gap) needs a *methodological* revision, not a retune of this corpus: a future
`post-pilot-v2` could define utility decidability per generalization type (e.g. a date-aware
rule alongside the existing numeric-band rule). Only after such a protocol revision should a
new, confirmatory-eligible Contracts corpus be authored — per the permanent-ineligibility
position above, it could not reuse `contracts/v1`. Neither `post-pilot-v2` nor a Contracts v2
corpus is created by this PR.

**Resolved by M3 Gate 6 / Issue #38 (`post-pilot-v2`, `docs/research/post-pilot-protocol-v2.md`).**
Finding 1 below is fixed: `score_utility` now routes GENERALIZE on a category in
`DATE_UTILITY_REQUIRED_GRANULARITY` (`deadline`, required to the day) through a dedicated
`classify_generalized_date` rule instead of the numeric-band rule; every other GENERALIZE
category is unaffected. `post-pilot-v1` is not edited — `CURRENT_PROTOCOL_ID` moved to
`post-pilot-v2`, following v1 §11's change procedure exactly. This does not create a new
confirmatory-eligible Contracts corpus (that remains Gate 7); `corpus/contracts/v1` stays
`pilot_development`, and its already-committed run artifact
(`artifacts/experiments/contracts/v1/954ffae9f6e143d6af45e4842f6daef9`) is unchanged on disk —
`docs/research/post-pilot-protocol-v2.md` §4 records, verified by re-scoring, exactly which of
its utility numbers are no longer comparable under the new rule.

**Nothing frozen by Issue #56 changed**: no category, detector rule, policy document, B3 action
space, generalization strategy or treatment definition was touched, and no metric frozen by
`post-pilot-v1` was added or redefined.

**Resolved by M3 / Issue #85 (`post-pilot-v3`, `docs/research/post-pilot-protocol-v3.md`).** The
related, separate defect Gate 6 deliberately left open (`_band_is_decidable` never checked that a
numeric GENERALIZE band actually contains the case's own oracle value — a wrong band could still
score `answerable` whenever no stated reference figure happened to fall inside it, and every band
was vacuously "decidable" with zero references) is fixed: `score_utility` now checks band
**fidelity** (does the band contain the original value at all) before band **sufficiency** (can it
be resolved against a stated reference), via the new `classify_generalized_band` rule. Neither
`post-pilot-v1` nor `post-pilot-v2` is edited — `CURRENT_PROTOCOL_ID` moved to `post-pilot-v3`,
following v1 §11's change procedure exactly, the same way Gate 6 did. `corpus/hr/v1` and
`corpus/contracts/v1` both stay `pilot_development`; re-scoring both committed runs under the new
rule (`docs/research/post-pilot-protocol-v3.md` §9) found **zero** category-, overall- or
B3→B4-level rows change (every numeric oracle span in both corpora already sits inside its own
generated band, by the generator's own pre-existing contract) — this ticket closes the gap without
changing any historical result. A further, separate reference-extraction/sufficiency-semantics
issue (Issue #87) and a separate treatment-behavior defect in the generator's own Brazilian-format
amount parsing (Issue #88) were found during this fix and filed as their own issues rather than
folded into this one; #87 is resolved below (`post-pilot-v4`), and #88 needs its own versioned
decision before it can be fixed and is ordered directly after #87, before Gate 7.

**Resolved by M3 / Issue #87 (`post-pilot-v4`, `docs/research/post-pilot-protocol-v4.md`).** Both
remaining Issue #85 §8 findings are fixed: (a) the free-text reference-extraction mechanism
(`_reference_values`) could not distinguish a strict "greater than" reading of a stated threshold
from a non-strict "at least" one, so a reference sitting exactly on a band's lower bound was
always scored `ambiguous` regardless of which reading the case actually intended; (b) that same
mechanism was category-blind, applying any number found outside a detected span as a candidate
reference for every numeric category a case depends on. `CaseOracle.utility_references` (a new,
purely additive `list[NumericUtilityReference] | None` field, `corpus-case-schema-v3`) replaces
free-text extraction with structured `(category, operator, value)` references for evaluation
purposes only — never reaching a treatment, the detector, a policy or a provider. A new function,
`classify_generalized_band_against_references`, shares fidelity (steps 1–3) byte-for-byte with the
frozen `post-pilot-v3` `classify_generalized_band` and applies a structured, per-operator
sufficiency rule (`docs/research/post-pilot-protocol-v4.md` §4) instead of the old bare-float
comparison. Neither `post-pilot-v1`, `-v2` nor `-v3` is edited — `CURRENT_PROTOCOL_ID` moved to
`post-pilot-v4`, following v1 §11's change procedure exactly. Neither `corpus/hr/v1` nor
`corpus/contracts/v1` is edited to add the field, so **neither frozen corpus can be scored under
`post-pilot-v4` at all** — both remain scored under `protocol_id="post-pilot-v3"` explicitly
(`scripts/run_hr_v1_pilot.py`/`run_contracts_v1_pilot.py`), and no committed artifact changes.
An analytical (non-committed) historical-impact estimate found 16 of 65 numeric-category rows
would move from `ambiguous` to `decidable` under a throwaway structured-reference fixture for the
two corpora (`hr_department_aggregation_001`/`002`, `hr_salary_analysis_001`/`002` × B1–B4;
Contracts: 0) — see `docs/research/post-pilot-protocol-v4.md` §9 for the method and §10 for why
this is not tuning. Item (c) from Issue #85 §8 (no utility-side `MIN_NUMERIC_BAND_WIDTH` check) is
moved to its own new issue, scoped to `scoring/exposure.py` rather than `utility.py` — see
`docs/research/post-pilot-protocol-v4.md` §8. A separate, unreachable finding (the v3 fidelity
regexes' `\d` pattern also matches non-ASCII Unicode digits) is recorded, not fixed, in its own
new issue (`docs/research/post-pilot-protocol-v4.md` §11).

**PR #92 review round 2 (2026-09-21).** Two corrections before merge: (1) the `post-pilot-v3`
compatibility check now refuses any opted-in oracle (`utility_references is not None`, an empty
list `[]` included), not only a non-empty list — `None` (legacy) and `[]` (opted in, explicitly
declares no reference) are distinct and must never be conflated; (2) `docs/research/
post-pilot-protocol-v4.md`'s earlier "no grounding requirement" wording was too strong and is
replaced by a semantic-grounding rule: a reference's value need not match the text lexically, but
every reference must correspond to a condition actually visible to the provider
(`CorpusCaseInput.text`/`task`), audited at Gate 7 authoring time, never invented solely to make a
band decidable. See `docs/research/post-pilot-protocol-v4.md` §3a/§3b and `docs/milestone-3-current-plan.md`'s Gate 7 requirement.

**Resolved by M3 / Issue #93 (`post-pilot-v5`, `docs/research/post-pilot-protocol-v5.md`).** The
pre-Gate-7 numeric-format checkpoint: Issue #88 (`NumericBandStrategy`'s permissive float regex
misread Brazilian-formatted amounts, e.g. `R$ 125.000,00` as `125.0`, and a huge digit string
could overflow float to `inf`/`NaN` and raise `ValueError` instead of failing closed) and Issue
#91 (the frozen v3/v4 fidelity regexes' `\d` also matches non-ASCII Unicode digits, and
`match`+`$` still accepts a trailing newline) are both resolved by a single closed, ASCII-only,
`fullmatch`-only amount grammar (`NUMERIC_AMOUNT_GRAMMAR_ID = "amount-grammar-v1"`) shared in
concept, but independently implemented, by the treatment (`transformations/generalization.py`)
and a new `post-pilot-v5` scorer path (`experiments/scoring/utility.py`). The grammar accepts
dotted-decimal (`R$ 125000.00`) and Brazilian (`R$ 125.000,00`, and, per an explicit
orchestrator decision, ungrouped `R$ 125000,00`) amounts with mandatory cents, NBSP as an
alternate separator, and rejects negatives, leading zeros, cents-less amounts and amounts over
15 integer digits; `NumericBandStrategy` now parses to `Decimal` (never `float`) and bands in
exact integer arithmetic. `post-pilot-v5` is registered as frozen, scorable and current
(`CURRENT_PROTOCOL_ID`); v3/v4 code paths (`classify_generalized_band`,
`classify_generalized_date`, their `\d` regexes) are untouched byte-for-byte, and both
`corpus/hr/v1` and `corpus/contracts/v1` stay refused under v5 (legacy-oracle reason, same as
v4) and remain scored under `protocol_id="post-pilot-v3"`. A new v5-only pre-run check
(`check_corpus_protocol_compatibility` → `UnsupportedOriginalAmountFormatError`) rejects, before
any provider call, any numeric-category oracle span -- blocked cases included -- whose value is
outside the grammar, so a future Gate 7 corpus cannot be authored against an amount format the
treatment/scorer contract does not actually support. Historical impact re-verified directly
against the live implementation: all 33 numeric-category oracle spans across both frozen
corpora parse to the identical band under the new grammar as under the old one, and a full
`post-pilot-v3` run over both corpora (125 case executions) is unaffected. Three further,
narrower findings surfaced during this work and are recorded as their own new issues rather than
fixed here (CRLF trailing `\r` on a detected labeled-line value; manifest code-commit/per-row
treatment provenance for Gate 8; `MonthYearDateStrategy` accepting Unicode digits via
`strptime`) -- see `docs/research/post-pilot-protocol-v5.md` §10/§12.

**Findings recorded, not fixed** (see `corpus/contracts/v1/README.md`):

- ~~`experiments/scoring/utility.py`'s GENERALIZE decidability rule is numeric-band-specific, so
  a month-coarsened deadline (`2026-02`) is parsed as a numeric band and scored `answerable`.~~
  **Resolved in `post-pilot-v2` (Gate 6 / Issue #38)** — see the follow-up note above.
- ~~The same numeric-band rule never checked that a GENERALIZE band actually contains the
  original value.~~ **Resolved in `post-pilot-v3` (Issue #85)** — see the follow-up note above.
  The other findings below remain open.
- `contracts-v1` preserves `deadline` unconditionally, so B4 is nonconformant on the six spans
  where the task does not need it — the documented, identifiable B3→B4 cell in the
  under-studied direction.
- B2's task- and policy-independent map pseudonymizes `cnpj`/`cpf` where `contracts-v1` and the
  oracle both require REMOVE; a measured property of B2 meeting a domain whose identifiers are
  publicly resolvable, and part of the gap B4 closes.
- Detection is 72/72 with no false positives, a property of the corpus's labeled-line format,
  not evidence about detector quality — the same threat to validity `corpus/hr/v1` records.
- All of the above was measured against `FakeProvider`; no real-LLM utility, token or cost claim
  is supported until T22 / Issue #30 lands.

### Milestone 3 closure criterion

M3 closes when:

1. post-pilot metrics/thresholds/comparison/provider rules are frozen on `develop` via PR #53,
   `docs/research/post-pilot-protocol-v1.md`;
2. a real provider is available behind the shared boundary;
3. structured Contracts ingestion is available without becoming a treatment variable ✅ (T12,
   merged via PR #55 — the ingestion/normalization boundary itself; Contracts-specific semantic
   interpretation is tracked separately by Issue #56 and by T24 / Issue #37, not by this criterion);
4. Contracts v1 corpus/oracle is frozen with its run classification decided before result inspection;
5. the next B0–B4 batch can start without post-result treatment/policy/metric tuning.

## Parallel academic track

### T01 — PPGCA line/advisor reevaluation

T01 remains independent from engineering gates.

The completed M2 materially changes the academic discussion: the project can now be presented as an executable research prototype with all B0–B4 treatments, a reproducible pilot, machine-readable metrics and explicit methodological limitations—not only as an architecture proposal.

The advisor-facing demo track is intended to make that prototype directly testable by prospective advisors through a hosted URL, but demo completion is not a prerequisite for T01 conversations.

Current provisional candidates remain:

- Daniel Fernando Pigatto;
- Michel Albonico;
- Luiz Celso Gomes Júnior.

T01 blocks only the final academic framing/line/advisor/submission, not M3 engineering.

## Parallel advisor-facing demo/application track

Tracker: **Issue #41 — Advisor-facing interactive research application**.

Purpose: turn the current Python research implementation into the application used to demonstrate the concept to prospective advisors. The demo exposes the actual implemented core rather than recreating anonymization/policy logic in Next.js.

Target path:

```text
browser -> Next.js -> HTTP API -> Python application/core -> B0–B4 -> provider -> local reconstruction
```

### First-demo rules

- no agentic anonymization/orchestration;
- detector/B3 analyzer/B4 policy logic remain the implemented deterministic mechanisms;
- prepared HR examples are synthetic/controlled;
- free-form input, if enabled, must preserve safe logging/error semantics;
- provider credentials remain server-side;
- UI never becomes a source of treatment/policy/scoring semantics.

### T20 / Issue #28 — application boundary + CLI/HTTP/MCP

Status: **T20 demo integration: in validation** (PR open against `develop`). The earlier vertical slices (application boundary, HTTP API, CLI, comparison surface) are merged; the demo-integration slice described under *Demo-integration slice* below is the one under review.

For the advisor demo, HTTP API is the first required adapter. CLI and MCP should share the same application service but do not need to block the first hosted URL.

The HTTP surface should execute controlled text + task + GovernanceContext + treatment/provider through the real Python core and return safe transformation/policy/provider/reconstruction/result metadata.

#### Delivered so far

- `application/` — the shared use-case boundary (`DisclosureApplicationService.preview`/`.execute`), framework-free and reusable by a later CLI/MCP adapter;
- `pipeline.decide_disclosure` — the detect → sanitize → fail-closed-task-check phase extracted from `run_disclosure_case`, so preview and execute share one implementation instead of two;
- `application/ingestion.py` — the normalization seam (direct text, `.txt`, `.md`) that T12 / Issue #9 plugs PDF/DOCX/XLSX/image into behind the same `NormalizedContent` contract;
- `api/` — a thin FastAPI adapter: `GET /health`, `GET /examples`, `GET /strategies`, `POST /disclosure/preview`, `POST /disclosure/execute`, `POST /disclosure/compare`;
- `cli.py` — a thin `argparse` CLI adapter over the same service (`adg health|examples|strategies|preview|execute|compare`), for local development, controlled runs and debugging. No new dependency, and it never imports the HTTP package, so it runs without FastAPI installed;
- `application/wire.py` — the single allowlisted serialization both adapters use, so CLI `--json` and the HTTP API return identical bodies and one field-allowlist governs both surfaces;
- `application/settings.py` — the shared default-service construction both adapters build from.

The default strategy is the policy-governed one, selected as `"recommended"` so the frontend never needs to know B0–B4 to run the primary flow. `GET /strategies` exposes the five treatments for the optional comparison surface.

#### B0–B4 comparison surface

`POST /disclosure/compare` / `adg compare` run the same content through all five treatments in the canonical order and report what each one *would* disclose.

It is **preview-based and never calls a provider**, for any strategy. B0 — Direct discloses the raw document unchanged, so executing a comparison would send the user's unprotected content to the external provider merely to illustrate the teaching point — actively harmful once T22 wires in a real provider, and worthless today since FakeProvider responses carry no task utility. An execute-based/utility-aware comparison is deferred and would require both T22 and a deliberate decision about whether B0 may ever run against a real provider on user content.

This is an **explanatory surface, not an evaluation surface**: it never touches the oracle, never imports `experiments.scoring`, computes no conformance/exposure/unnecessary-disclosure metric, and ranks nothing. Each entry carries `unsafe_control_baseline`, read from the existing `pipeline.UnsafeControlTreatment` capability marker, so B0 can be labeled honestly rather than presented as a peer option.

#### Adapter status

| Adapter | Status |
| --- | --- |
| HTTP API | delivered |
| CLI | delivered |
| MCP | pending |

#### Demo-integration slice — in validation

The gate Issue #41 calls *Gate A*: connect capabilities that already existed into one contract-analysis flow.

```text
multipart HTTP upload -> T12 normalized ingestion -> NormalizedContent
  -> Contracts governance preset (domain=contracts, policy_version=contracts-v1)
  -> B4 — Policy-governed preview -> server-signed confirmation
  -> confirmed execute (re-uploaded, re-verified) -> configured provider
  -> local reconstruction
```

- `POST /documents/preview` and `POST /documents/execute` — `multipart/form-data` routes taking `file`, `task`, `document_type`, optional `analysis_mode` and optional `strategy`. PDF/DOCX/TXT/MD (and XLSX, which rides the same T12 path) reach the ingestion boundary as bytes; the response schemas are the existing `PreviewResponse`/`ExecuteResponse`, unchanged. `GET /documents/types` exposes the caller-facing vocabulary so a UI never hardcodes it.
- `application/presets.py` — the server-owned allowlist that turns `(document_type, analysis_mode)` into a `GovernanceOverrides`. `document_type` is required on every upload, so an uploaded contract can never fall through to the deployer's HR default; an unregistered document type or an unlisted analysis mode is refused. A preset never sets `provider_class` or any lifecycle identifier.
- `DisclosureApplicationService.build_document_request` — the one entry point an upload adapter uses; it has no `governance` parameter, so an adapter cannot supply a domain/policy version/purpose of its own. The service also takes an injectable `document_parser`, keeping the T12 adapter replaceable and the test suite offline.
- `api/limits.py` — a pure ASGI request-body ceiling (`ADG_MAX_UPLOAD_BYTES`, default 8 MiB) enforced before any route or body parser runs, on both the declared `Content-Length` and the streamed byte count. It is deliberately below `ingestion.MAX_INPUT_BYTES` (10 MiB) so the HTTP boundary is the binding one for an upload.
- `application/settings.build_default_service` — now builds the provider through `providers.build_provider_from_env`, and derives the default `GovernanceContext.provider_class` from that provider. `ADG_PROVIDER=anthropic` therefore works in a deployment without hand-injecting a custom service, with `provider_class = external_llm`; `FakeProvider` stays the default and an unrecognized value fails closed.
- `application/preview_confirmation.py` — the server-signed proof binding one execute to the preview a reviewer approved. Added during review of this slice, which found that `/documents/preview` and `/documents/execute` were two unrelated requests: a client could preview under `recommended`/B4 and execute the same upload under `strategy=b0`, so what reached the provider need not have been what was reviewed. `/documents/execute` now requires the token the matching preview issued, re-computes the approved state from the re-uploaded request, and refuses any divergence before the provider call. HMAC-SHA256 (standard library), stateless — no database, cache, session or stored document — keyed by `ADG_PREVIEW_CONFIRMATION_SECRET`, which a deployment wired to an external provider must configure or it refuses to start. Bound: normalized document, task, document type, resolved analysis mode, resolved governance, strategy/treatment, provider class and the external payload; content is bound as *keyed* digests, so the token itself discloses nothing.
- B0 — Direct is not executable against a provider outside the trust boundary through `/documents/execute`, and fails closed before the provider call. A product/demo-surface rule only: B0's experimental semantics, its role as the unsafe control, and its visibility in preview and comparison are unchanged, and the T10 runner never passes through this surface.

Uploads stay ephemeral: bytes are read into memory, handed to ingestion and never written to disk.

#### Deliberately still out

MCP adapter, execute-based/utility-aware B0–B4 comparison, image/OCR ingestion, authentication and rate limiting, generic provider/model selection.

#### Scientific state unchanged

This slice adds no treatment, policy, corpus, oracle or metric semantics. B0–B4, the frozen HR corpus, `hr-v1`/`hr-v2`/`hr-v3`, `contracts-v1`, the M2 artifacts and every experimental metric are untouched; the application layer never reaches the oracle, and the T10 scoring modules are not imported by it. The demo-integration slice added no policy rule, no detector rule and no corpus material — its Contracts fixtures are the existing synthetic development fixtures under `tests/`, and nothing under `corpus/` was read or modified.

### T21 / Issue #29 — Next.js advisor-facing UI

Status: **fourth vertical slice completed and integrated into `master`** (PR #51 into `develop`, then PR #52 `develop` → `master`) / non-blocking for M3. T21/Issue #29 is **not** complete and stays open — see "Deliberately not in the fourth slice" below.

The UI lets a reviewer select a prepared HR example or controlled text, see what crosses the trust boundary before anything is sent, receive the locally reconstructed answer, see the same content compared across all five B0–B4 strategies as a preview-only teaching surface, inspect a safe technical/operational view of the SAME execution already shown on Resultado, and — as of the fourth slice — do all of that in either pt-BR or English. It consumes T20's real HTTP API — there is no fixture phase.

#### Delivered in the fourth slice

**pt-BR / English localization**, with the user's choice persisted in the browser. This is a presentation-only change: no Python, contract, B0–B4 treatment, policy, corpus, oracle, endpoint, provider, or execution-behavior code changed.

- **Architecture** — `web/lib/copy.ts` keeps its pre-committed design (module docstring), adjusted for the one thing it hadn't anticipated: `ptBR` ends in `as const`, so `typeof ptBR` alone would produce LITERAL string types and force a second locale to contain the identical Portuguese words. `AppCopy` is instead `Widen<typeof ptBR>` — a recursive mapped type that turns every string literal into `string` and every array into a general `readonly Widen<element>[]`, while leaving object keys untouched. `web/lib/copy.en.ts` defines `export const en: AppCopy = {...}` in its own module; a missing key, an extra key, or a wrong-shaped nested value there is a **compile error**, not a runtime gap (verified by deliberately breaking the file during development: both a missing key and an extra key produced a `tsc` error naming the exact field). `web/lib/copy.ts`'s `resolveCopy(locale)` picks between the two tables.
- **Locale module** (`web/i18n/`) — `locales.ts` (`Locale`, `SUPPORTED_LOCALES`, `DEFAULT_LOCALE`, `isSupportedLocale`, `LOCALE_LABELS`), `localeStorage.ts` (read/write, wrapped in try/catch, mirroring `lib/theme.ts`'s posture toward a throwing `localStorage`), `LocaleContext.tsx` + `LocaleProvider.tsx` (state) + `useLocale.ts` (`useLocale`/`useCopy`, the only way a component reads/changes locale or resolved copy — never `localStorage` directly, never a component-local copy of the state). The context's DEFAULT value (used by any component with no `<LocaleProvider>` ancestor) is a fully working pt-BR value, not `undefined` — every screen unit test written before this slice keeps passing unmodified.
- **Storage key** — `adg-locale`, chosen for consistency with the existing sibling `adg-theme-preference` key (Paulo's suggested example, `adaptive-disclosure-gateway.locale`, was offered as an example rather than a requirement).
- **Hydration mismatch** — handled with `useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)` rather than a mount-effect `setState` (an earlier draft used a `useEffect` that called `setState`, which is correct in outcome but tripped `eslint-plugin-react-hooks`'s `set-state-in-effect` rule; `useSyncExternalStore` is the React-native tool for "an external, client-only data source that can differ between server and client render" and needs no such effect). `getServerSnapshot` (`initialLocale()`) always returns `DEFAULT_LOCALE` and never touches storage — pinned directly in isolation, and further pinned by a real `renderToString` + `hydrateRoot` test that stores `en` beforehand, asserts the server markup is pt-BR, hydrates it, and asserts no `console.error` call matches `/hydrat/i`. `<html lang>` follows the same pattern as `lib/theme.ts`'s `data-theme`: the server always renders `lang="pt-BR"` (`app/layout.tsx`), and `LocaleProvider` updates `document.documentElement.lang` from a `useEffect` once the real locale is known client-side — never read from storage during the first render. Same-tab locale switches are propagated through a small in-module listener set (`storage` events fire only in OTHER tabs).
- **Session locale vs. persistence** — `LocaleProvider.tsx` holds an in-memory `volatileLocale` (module state, `null` until the first `setLocale` call this session) that `getSnapshot` checks BEFORE storage: `volatileLocale ?? readStoredLocale() ?? DEFAULT_LOCALE`. `setLocale` sets it unconditionally and only then attempts `storeLocale` — so a `localStorage.setItem` failure (privacy mode, an embed, a storage policy) can no longer prevent the locale from changing for the rest of the session; it only means the choice does not survive a reload. A `storage` event from another tab still updates `readStoredLocale()`'s return value, but this tab's own explicit choice (if any) keeps winning, since `getSnapshot` checks `volatileLocale` first — a deliberate, simpler-than-cross-tab-sync choice for this slice. `resetVolatileLocaleForTests` (test-only) clears that module state between tests in the same file; `renderWithLocale` and the screens' own `beforeEach`s call it so a switch in one test cannot leak into the next.
- **Locale switcher** (`web/components/LocaleSwitcher/`) — a single real `<button>` next to `ThemeToggle` in `GuidedFlow`'s header, keyboard-operable by construction, text-labeled ("Idioma: Português" / "Language: English" — language names are shown in themselves, never a flag/emoji), toggling between the two supported locales without a reload.
- **Screens covered** — Boas-vindas/Novo teste/Revisão/Resultado/Comparação B0–B4/Detalhes técnicos, plus the shell (theme label, language label) and client-side error messages (`lib/api.ts`'s fallback/validation messages now take an `AppCopy` parameter, defaulting to pt-BR for backward compatibility; `GuidedFlow` passes the live `useCopy()` value at the moment of each user-triggered request).
- **Scientific terminology preserved in English** — B0 stays baseline/reference-control language, never "bad"/"wrong"/"worst"; B4 stays "what it does" language, never "best"/"most secure"/"scientifically superior"; `strategyVsTreatmentExplanation` keeps stating that `recommended` is a request-time option that currently resolves STATICALLY to B4 (never "the policy decides"/"automatically"); `timingExplanation` keeps `total_ms` framed as operational-only, explicitly not the scientific latency metric used in the experiments. `web/lib/copy.test.ts` extends the existing pt-BR regression pins to equivalent English patterns and adds a structural scan (over every string leaf reachable from either locale table) rejecting "best strategy"/"winner"/"most secure"/"scientifically superior" and their pt-BR equivalents, plus a narrower B0-only scan for "bad"/"wrong"/"insecure strategy"/"worst".
- **Technical identifiers unchanged** — `b0`–`b4`, `recommended`, `policy_version`, `provider_class`, contract values, category identifiers, treatment codes, ids, hashes and model ids/snapshots stay byte-identical in both locales; only their human presentation (labels/explanations) changes. Pinned per-screen (e.g. `TechnicalDetailsScreen`'s English test still asserts `"recommended"`/`"b4"` render verbatim).
- **No-leak posture unchanged** — the locale context/provider carries presentation state only (`locale`, `setLocale`, `copy` — no response data); switching locale re-runs the existing adversarial marker tests (an `external_payload` marker planted on Revisão and on Detalhes técnicos) and confirms it still never reaches the DOM; switching locale is pinned to never re-call `/disclosure/preview`, `/disclosure/execute` or `/disclosure/compare`, and to leave the already-held `ExecuteResponse`/`CompareResponse` data unchanged.
- **Key-parity** — enforced primarily by `AppCopy`'s structural type (a compile-time guarantee, verified by intentionally breaking `copy.en.ts` during development); a runtime backstop in `copy.test.ts` additionally walks both locale objects' key paths and asserts they match (with a companion test proving that check can itself fail from a real defect).

#### Delivered in the third slice

**Detalhes técnicos** (`Ver detalhes técnicos`), reached as a secondary action from Resultado, alongside `Comparar estratégias`. Pure client-side navigation over the `ExecuteResponse` Resultado already holds — `lib/flow.ts` gained a `technicalDetails` screen and an `OPEN_TECHNICAL_DETAILS` event; it reuses the existing `RETURN_TO_RESULT` event to go back rather than inventing a second one, and (unlike the comparison screen's return) threads `compareError` through unchanged, since opening/closing this screen never touches comparison state. No new request is made: opening or closing this screen never calls `/disclosure/preview`, `/disclosure/execute` or `/disclosure/compare`.

`components/TechnicalDetailsScreen` takes ONLY `execute: ExecuteResponse` as its data prop (never `preview`) — a structural guard, not just a behavioral one, against `PreviewResponse.external_payload` ever reaching this screen. It renders five sections:

- **Execução** — `strategy` (the requested interface/API choice: `"recommended"` OR an explicit `b0`–`b4` code, both legal on `DisclosureStrategy`) and `treatment` (the `b0`–`b4` code actually executed); `_STRATEGY_TO_TREATMENT` is a static mapping, not a decision procedure — every explicit strategy maps to the treatment it names, and only `recommended` currently resolves (a product/UX default, not a scientific claim that B4 dominates every comparison) to Policy-governed/B4. The screen states this distinction and draws no conclusion from either value;
- **Governança** — only `SafeGovernanceView` fields; a null `requester_role` renders as "Não informado", never as an error;
- **Provedor** — only the safe `ProviderStage` fields. `decoding_config` renders as bounded, non-recursive key/value rows (`formatDecodingValue`, capped at 200 chars), never a dump of the whole response. The not-called state shows only a notice; a failed call shows ONLY `failure_kind` (the safe exception-class-name category — see `audit.py`'s `ProviderStage` docstring) and nothing else provider-related;
- **Reconstrução local** — `attempted`, `changed_from_provider_response`, with a brief explanation of what local reconstruction means; never shows pseudonym mappings or attempts to recover original values;
- **Tempo operacional** — `total_ms`, with explicit pt-BR text stating this is an operational measure of the application run and NOT the scientific latency metric used in the experiments. No T10/`experiments/stage_timing.py` metric, percentile or benchmark is imported, recreated or computed; `total_ms` is never turned into a score.

**Hash tension, flagged for Paulo rather than decided silently:** `response_hash`/`reconstructed_hash` are rendered as technical metadata, but only behind their own nested `<details>` disclosure, kept OUT of the React tree (not merely CSS-hidden) until explicitly opened — the same pattern `ComparisonScreen` uses for `external_payload`. This follows CLAUDE.md's no-leak invariant, which treats a public, reproducible digest of low-entropy content as guessable/dictionary-reversible (one of this project's three historical side-channel defects was exactly an unkeyed public SHA-256 in an audit record). Both hashes are actually HMAC-SHA256 digests keyed by a process-local, non-reproducible secret (`audit.py`'s `_content_hash`/`_DEFAULT_AUDIT_HASH_KEY`), not a plain digest — a materially different risk profile than that historical defect — but the PR leaves the keep/truncate/presence-indicator-only decision to Paulo rather than assuming the keying makes it moot.

`external_payload` does not appear anywhere on this screen; neither do the original document, the task, provider raw response text, pseudonym mappings, or any lifecycle id (`requester_id`/`session_id`/`document_id`/`request_id` — excluded structurally, since `SafeGovernanceView`/`ExecuteResponse` never carry them).

#### Delivered in the second slice

**Comparação B0–B4** (`Comparar estratégias`), reached as a secondary action from Resultado, over `POST /disclosure/compare`:

- teaches before showing codes: each strategy's headline is a plain-language treatment name (`copy.treatments`, derived from `docs/experimental-design.md`'s treatment definitions), with the raw `b0`–`b4` code and `treatment` identifier demoted to an expandable technical-details area;
- states explicitly, in pt-BR, that the comparison is a disclosure simulation and that none of the five strategies sends the document to the provider during this step;
- the B0 — Direct warning is derived from `unsafe_control_baseline` only, never from `strategy === "b0"` — pinned by a test with a non-b0 entry carrying the flag and a b0 entry without it;
- `recommended` renders as "Estratégia recomendada para o fluxo demonstrativo" — product configuration, never a ranking, score or "best" claim; no benchmark table exists;
- reuses `CategoryOutcomeRow`/`describeCategoryOutcome`/`describeCategory` unchanged for the per-strategy local-vs-sent split;
- `external_payload` is kept out of the React tree per strategy until its own disclosure is explicitly opened, same pattern as Revisão's payload toggle; the B0 payload additionally states the unsafe-control context before revealing it;
- entries render in exactly the order `POST /disclosure/compare` returns (`CANONICAL_COMPARISON_ORDER`), pinned against the Python source, never re-sorted client-side;
- `lib/flow.ts` gained `comparing`/`comparison` screens and `REQUEST_COMPARISON`/`COMPARE_SUCCEEDED`/`COMPARE_FAILED`/`RETURN_TO_RESULT` events; returning to Resultado preserves the original `preview`/`execute` state without re-fetching.

Runtime validation added in `lib/responseGuards.ts` (`isCompareResponse`): `contract_version`, the `entries` collection, and per entry `strategy`/`treatment`/`recommended`/`unsafe_control_baseline`/`summary`/`external_payload`/`payload_byte_count`, plus `governance`/`provider_mode`. `unsafe_control_baseline` is checked as a real boolean (`typeof === "boolean"`), matching the existing `crosses_trust_boundary`/`failed` posture — a string `"false"` or an absent field both fail closed.

#### Delivered in the first slice

The guided flow from `docs/advisor-demo.md`, steps 1–4:

1. **Boas-vindas / Como funciona** — the three-step concept explanation;
2. **Novo teste** — prepared example, `.txt`/`.md` upload, or pasted text, plus a natural-language task;
3. **Revisão antes do envio** — what was detected, what stays local vs. what will be sent, per-category plain-language outcome and why;
4. **Resultado** — the reconstructed answer, the `Local → Provedor externo → Local` trust-boundary path, and the protections applied.

Supporting structure under `web/`:

- `lib/contracts.ts` — TypeScript mirror of `application/wire.py`, pinned against the Python enum by a test that reads the Python source;
- `lib/outcomes.ts` — the only place a category summary becomes user-facing text. **Fail-closed**: an outcome the UI does not recognize renders as "unknown — verify", never as protected/local. The local-vs-sent split is read from `crosses_trust_boundary`, never re-derived;
- `lib/copy.ts` — all pt-BR copy in one module, structured so a second locale is an addition rather than a refactor;
- `app/api/**` — thin Next.js proxy routes (`browser → web → API`), forwarding body and status unchanged and never logging either;
- `app/globals.css` — semantic tokens with complete light and dark palettes.

The primary path never requires knowing B0–B4: the UI simply omits `strategy`, so the API's `"recommended"` (policy-governed) default applies. A test pins that the compose screen renders no B0–B4 vocabulary and no treatment selector.

#### Deliberately not in the first slice

`Comparar estratégias` (the B0–B4 screen over `POST /disclosure/compare`), `Ver detalhes técnicos`, the English locale, `Histórico`, `Experimentos` and the `Configurações` area.

#### Deliberately not in the second slice

`Ver detalhes técnicos` (the full technical-details screen — the comparison screen's own per-entry technical disclosure is a small expandable, not that screen), the English locale, `Histórico`, `Experimentos`, `Configurações`, a real provider, auth, rate limiting, and structured PDF/DOCX/XLSX upload.

#### Deliberately not in the third slice

The English locale, `Histórico`, `Experimentos`, `Configurações`, remaining navigation polish, T20's still-pending multipart/binary upload wiring to the now-merged T12 ingestion boundary (PDF/DOCX/XLSX), T22 real provider, and T25 deploy.

#### Deliberately not in the fourth slice

`Histórico`, `Experimentos`, the full `Configurações` area, remaining navigation polish, locale-aware number/date/byte formatting (kept deliberately simple/out of scope for this slice), T20's still-pending multipart/binary upload wiring to the now-merged T12 ingestion boundary (PDF/DOCX/XLSX), T22 real provider, and T25 deploy. **T21/Issue #29 stays open** pending these.

#### Scientific state unchanged

The UI adds no treatment, policy, corpus, oracle or metric semantics. It renders what the API returns and never decides what is safe. The comparison screen imports no scoring/oracle/metric module and computes no aggregate across strategies beyond what each strategy's own preview already reports. The technical-details screen computes no scientific metric either: `total_ms` is operational-only, never a substitute for T10's stage-aware latency metric. The fourth slice (localization) is presentation-only: no treatment, policy, corpus, oracle, endpoint, provider or execution-behavior code changed, and the frozen `b0`–`b4` codes/technical identifiers are never translated in either locale.

### T25 / Issue #42 — containerized demo/deploy infrastructure

Status: **in validation via PR (feat/t25-advisor-demo-deployment -> develop)**. Hosted URL and
live Anthropic smoke through that URL are **pending** -- neither T25 nor the Demo Track (#41)
is complete until both exist.

The current root `compose.yaml` is a development/test harness rather than deploy infrastructure: it mounts the repository and runs tests. T25 owns a distinct deployment-oriented topology, delivered as `compose.demo.yaml` plus `docker/api.Dockerfile` and `web/Dockerfile`.

Delivered in this PR:

- Python API image (`docker/api.Dockerfile`) on Python 3.13.13, multi-stage, CPU-only torch wheels, a build-time Docling model-cache prewarm step, non-root runtime user;
- Next.js image (`web/Dockerfile`) using `output: "standalone"`, multi-stage, non-root runtime user;
- `compose.demo.yaml`: `api` (internal-only, no published port, no volume) and `web` (one published port, depends on `api` being healthy) on a dedicated network, plus an opt-in `tls` profile (Caddy reverse proxy, the stack's only volume);
- health/readiness checks on both services;
- `ADG_PROVIDER` is a required compose interpolation (no silent default either way); every Anthropic/secret variable reaches `api` only, as an interpolation, never a literal;
- `.dockerignore` (root and `web/`) excluding `.env`/`.env.*`, `.git`, `.venv`, `node_modules`, `.next` and the repository's own never-commit paths (`local-data/`, `/vault/`, `artifacts/private/`);
- `tests/test_demo_deployment_config.py` pins the security-relevant shape of the above statically (no Docker required to run it);
- an opt-in E2E smoke test (`tests/test_demo_smoke_e2e.py`, gated on `ADG_DEMO_SMOKE_BASE_URL`) drives the web origin's `/api/documents/{types,preview,execute}` with synthetic PDF/DOCX contracts.

The target is a small research-demo deployment, not desktop distribution, installers, multi-tenant SaaS or production-scale orchestration.

### T26 / Issue #67 — export the disclosed representation with sealed restore handles

Status: **in validation** (open PR to `develop`, reconciled with T25 / Issue #42's merged demo deployment; not demo-critical, not on the scientific critical path).

Lets a caller take a disclosed representation of a document (the same `external_payload` `POST /documents/preview` already returns) outside the gateway and, later, restore its pseudonyms locally through an explicit, sealed restore handle. Design decisions in `docs/adr/0002-deferred-restore-handles.md`.

- `application/restore_handle.py`: stateless AES-256-GCM (via `cryptography`) sealed envelope, key derived with HKDF-SHA256 from `ADG_RESTORE_HANDLE_SECRET`, domain-separated from the preview-confirmation secret. No server-side retention — a handle carries only the `(pseudonym -> original)` entries present in one export, `v`/`iat`/`exp`, padded to a fixed bucket so its length does not reveal exact original lengths.
- `DisclosureApplicationService.export`/`.restore`: `export` runs the same decision phase `preview` runs (never the provider) and refuses a `BLOCK_REQUEST` outcome; `restore` replaces only the pseudonyms a handle recognizes in arbitrary submitted text, reporting `restored_count`/`unresolved_count`, never the mapping.
- No ephemeral-key mode (unlike preview confirmation): an unset `ADG_RESTORE_HANDLE_SECRET` still starts the service and leaves every other route working, but export/restore themselves fail closed (`RestoreUnavailableError`, HTTP 503, non-zero CLI exit).
- HTTP: `POST /documents/export` (multipart, same fields as `/documents/preview`), `POST /documents/restore` (JSON `{text, restore_handle}`). CLI: `adg export`, `adg restore` (handle/text read from a file or stdin, never a plain argv value).
- Not in this PR: any web proxy route or UI (T25 keeps the API internal-only behind the web proxy; export/restore are API/CLI-only until a later UI slice -- see T28 / Issue #70 below, which adds a gated web route and UI action for this same mechanism), PDF/DOCX re-rendering, any change to B2 — Reversible Pseudonymization / B3 — Task-aware / B4 — Policy-governed semantics.
- Reconciled with T25's merged `compose.demo.yaml`: `ADG_RESTORE_HANDLE_SECRET` and `ADG_RESTORE_HANDLE_TTL_SECONDS` reach the `api` service only, both as OPTIONAL interpolations (unset = export/restore disabled with 503, no effect on any other route); `web` carries neither, and a static test pins that the hosted demo has no proxy route or reference to either path (ADR-0002). `docker/api-constraints.txt` was regenerated for `cryptography` as part of this reconciliation. `GET /ready`'s readiness check (T25) does not consult the restore-handle secret, pinned by regression tests added during reconciliation.

### T27 / Issue #69 — transformation inspector for the demo

Status: **in validation (open PR to `develop`, feat/t27-t28-demo-transparency)**.

Adds a gated, additive `inspection` field to `DisclosurePreview` (and the HTTP/CLI preview
contracts) showing a side-by-side original/disclosed view built from the pipeline's own
structured output, plus a collapsed-by-default `DisclosureInspector` panel on the web Review
screen.

- Gated by `ADG_ENABLE_DEMO_TRANSPARENCY` (`application/settings.py`; unset/blank/anything but
  exactly `"1"` after stripping is disabled). `inspection` is `null` on every response when the
  flag is off, matching today's contract exactly; `CONTRACT_VERSION` (`t20-application-api-v1`)
  is unchanged, since the field is additive and nullable.
- `application/inspection.py::build_inspection` derives `segments` from
  `resolve_overlaps(decision.spans)` zipped 1:1 against `decision.result.transformations` --
  never a string diff -- and verifies the segments' concatenated `original`/`disclosed` values
  reproduce the source text / `external_payload` exactly; fails closed
  (`unavailable_reason: "blocked"` or `"alignment_failed"`) rather than emitting a partial or
  best-effort projection. B0 — Direct falls back to one whole-text segment. No offsets on the
  wire, only reconstructed text segments.
- No-leak: `inspection.py` never imports `vault`, opens no OTel span of its own
  (`tests/test_inspection_isolation.py`); the projection itself is the only place a preview
  response widens under this flag.
- Not in this PR: any change to detection/transformation/B0–B4 semantics, any persistence of
  the inspection projection, any endpoint that returns more than one request's own
  transformations.

### T28 / Issue #70 — gated export/restore UI for the demo

Status: **in validation (open PR to `develop`, feat/t27-t28-demo-transparency)**.

Adds a web-facing, gated proxy for T26's export/restore mechanism plus an `ExportRestorePanel`
on the Review screen, so an advisor can run the full export → simulated external use → restore
cycle from the browser instead of the CLI.

- Same `ADG_ENABLE_DEMO_TRANSPARENCY` gate as T27, checked in `web/app/api/documents/export`
  and `.../restore` route handlers *before* anything else -- a disabled flag makes zero
  upstream calls to the api service, and both return a fixed 404
  (`{"detail": "not found", "kind": "DemoTransparencyDisabled"}`) when off. A third route,
  `GET /api/demo/features` (`dynamic = "force-dynamic"`, so a container's runtime value of the
  flag is never baked in at `next build` time), tells the web UI whether to render the panel at
  all.
- `web/lib/demoTransparency.ts` mirrors `application/settings.py`'s parsing rule
  byte-identically; the flag is read server-side at request time and is deliberately never a
  `NEXT_PUBLIC_*` build-time variable.
- `tests/test_demo_deployment_config.py::TestWebExportRestoreIsGated` replaces T26's
  `TestWebDoesNotExposeExportRestore` pin -- the web now has export/restore routes, so the
  invariant worth pinning changed from "the routes do not exist" to "the routes exist but are
  gated and check the flag first."
- Export is upload-only in this panel (T26's HTTP export endpoint is document-only; there is no
  paste-text export path to proxy). The restore handle lives only in React state for the
  lifetime of the tab -- never `localStorage`/`sessionStorage`, never a URL parameter, never
  logged.
- Not in this PR: a Vault Explorer (delivered separately by T29 / Issue #72 below) or any
  endpoint listing/dumping the pseudonym → original mapping; persistence of exported/restored
  content; any change to T26's API/CLI behavior or to B2 — Reversible Pseudonymization
  semantics; enabling this on a public unauthenticated URL (the flag exists precisely so the
  hosted demo can keep it off).

### T29 / Issue #72 — local Vault Explorer for demo/debug

Status: **in validation (open PR to `develop`)**.

Adds a gated, demo-only surface that lets an operator confirm, for one specific preview, exactly
which vault entries back its reversible pseudonymization and that local reconstruction resolves
them -- the one thing neither T27's inspector (shows what changed, never touches the vault) nor
T28's export/restore (proves the durable handle mechanism works, scoped to one sealed handle) by
itself demonstrates.

- Gated by its own `ADG_ENABLE_DEMO_VAULT_EXPLORER` flag (`application/settings.py`,
  `web/lib/demoVaultExplorer.ts`), parsed byte-identically to `ADG_ENABLE_DEMO_TRANSPARENCY`
  (set AND stripped value exactly `"1"`) but fully independent of it -- enabling one never
  enables or requires the other. Must be set on both `api` and `web`; default off on both.
- `application/vault_explorer.py` (`VaultExplorerSealer`): on an allowed preview,
  `issue_reference` seals an opaque `vx1.…` AES-256-GCM reference over that decision's own
  distinct PSEUDONYMIZE `(pseudonym, category)` pairs -- never the originals, which are looked
  up fresh from the live vault only inside `explore` -- plus the resolved `PseudonymScope` and
  its partition key, each pseudonym re-verified against the vault at issuance time. Returns
  `None` (never raises) for a blocked decision, a resolved `PseudonymScope.ORGANIZATION`, a
  missing scope key, or any entry that fails re-verification. The sealing key is a fresh random
  32-byte value generated once per process -- never derived from `ADG_RESTORE_HANDLE_SECRET` or
  `ADG_PREVIEW_CONFIRMATION_SECRET` -- so a reference from one process is unconditionally
  rejected by any other, and a restart invalidates every outstanding token. Fixed 900-second
  (15-minute) TTL, not configurable. This module is the only application/api-layer code besides
  the existing execute path allowed to call `Vault.reconstruct`, pinned by
  `tests/test_vault_explorer_import_isolation.py`.
- `PreviewResponse.vault_explorer_token: str | None` -- additive, nullable; `null` when the flag
  is off, the decision is blocked, or the resolved scope is ORGANIZATION. Issued from the same
  decision `preview()` already computed, never a second one.
- `POST /demo/vault-explorer` (JSON `{token}` -> `{contract_version, scope, entry_count,
  entries: [{category, pseudonym, original | null, present}]}`) resolves each entry via a point
  lookup (`vault.reconstruct(scope, key, pseudonym)`) only -- no enumeration, no change to
  `vault/`. Fixed 404 (`DemoVaultExplorerDisabled`) when the flag is off; fixed 400
  (`VaultExplorerReferenceError`, one message for every rejection reason) for a malformed,
  tampered, expired, or foreign-process token. Every response from this path -- any status --
  carries `Cache-Control: no-store` / `Pragma: no-cache` via a dedicated path-scoped pure ASGI
  middleware (`_NoStoreOnVaultExplorerASGIMiddleware`), not a route-local header, so a future new
  failure mode on this path inherits the header automatically.
- Web: `lib/demoVaultExplorer.ts` (server-only gate, never `NEXT_PUBLIC_*`),
  `app/api/demo/vault-explorer/route.ts` (`force-dynamic`, checks the flag before any upstream
  call, disabled and forwarded responses both carry `no-store`), `GET /api/demo/features` gains
  `demo_vault_explorer_enabled`, and a collapsed-by-default `VaultExplorerPanel` on both the
  Review and Result screens -- fetches only on open, masks originals until an explicit toggle,
  and discards fetched entries on close.
- No-leak: the only OTel spans this feature opens (`vault_explorer.issue`,
  `vault_explorer.explore`) carry counts only (`entry_count`, `present_count`); every parser that
  could otherwise echo attacker- or plaintext-controlled bytes into its own exception message is
  broken from its exception with `raise ... from None`.
- Not in this PR: any change to B0–B4 treatment semantics, the frozen HR/Contracts corpora, the
  T10 oracle, T26's restore-handle mechanism itself, or `vault/`'s own protocol; any list-all or
  enumeration capability; any change to `ADG_ENABLE_DEMO_TRANSPARENCY`'s own behavior.
- Known limitations: a single-process sealing key means references issued by one `api` worker
  fail closed on every other worker or after a load-balancer hop (unusable, not unsafe); the
  15-minute TTL is fixed, not configurable; the demo's default SESSION scope uses a shared
  configured `session_id` (`demo-session`), so enabling this flag on any shared/hosted deployment
  reveals originals of submitted content to whoever can reach the web origin -- keep it off
  outside a controlled local environment, a constraint the application cannot enforce by itself.

### T30 / Issue #82 — guided demo UX with progressive disclosure

Status: **in validation (open PR to `master`, per explicit user direction for this ticket)**.

Reorganizes the Next.js guided flow's information architecture and copy so a first-time visitor
(a prospective advisor) understands problem -> proposal -> trust boundary -> transformation ->
external send -> local reconstruction -> result from the app alone, without first needing
B0-B4/vault/hash/policy vocabulary. Pure information architecture, copy, hierarchy and
progressive-disclosure work -- no new technical capability, no API/contract change, no change to
B0-B4 semantics, no dashboard.

- **Welcome** (`WelcomeScreen`): replaces the thin three-step list with a plain-language problem
  statement, an accessible semantic-HTML trust-boundary flow diagram (Documento original ->
  Gateway local -> Representação divulgada -> LLM externo -> Resposta -> Reconstrução local,
  each step labelled by its own local/external group text so the boundary never depends on color
  alone), a PRESERVE/REMOVE/PSEUDONYMIZE/GENERALIZE explainer with tiny synthetic before/after
  examples, and a closed-by-default "Como funciona a pesquisa?" disclosure -- the only place on
  this screen B0-B4 semantic names/descriptions appear, in canonical B0->B4 order.
- **Review**: the local/sent split still comes only from `category.crosses_trust_boundary`
  (unchanged). The "what will be sent" section is now headed by the prominent
  `copy.review.willBeSentHeading` ("O que será enviado ao LLM externo"), with the existing
  payload `<details>` (still kept out of the DOM until opened) nested under it, and the confirm
  button now states the consequence explicitly ("Confirmar e enviar ao provedor externo"). The
  T27 transformation inspector now sits behind a new Level-2 disclosure ("Entender o que o
  gateway mudou e por quê"); the T28 export/restore panel and T29 Vault Explorer now sit together
  behind one new Level-3 disclosure ("Detalhes técnicos e ferramentas de pesquisa"), collapsed by
  default. No gating condition, feature flag, or the confirmation-token/preview-execute binding
  changed -- only where each already-gated panel mounts in the JSX tree.
- **Result**: adds a data-derived protections summary line ("N itens protegidos; M pseudônimos
  reconstruídos localmente", computed only from `ExecuteResponse.summary.categories.
  occurrence_count` and `reconstruction.attempted`, never invented) directly under the final
  answer. The Local -> Provedor externo -> Local recap now sits behind a new "Entender o que
  aconteceu" disclosure. "Comparar estratégias" is now framed under an explicit research heading
  ("Comparar estratégias experimentais (B0–B4)"); "Ver detalhes técnicos" and `VaultExplorerPanel`
  are framed under a technical/audit heading -- both stay directly clickable (this screen's
  pre-existing "always available, every outcome" contract), the hierarchy is expressed through
  headings/intro copy and visual secondariness rather than an extra required click. The
  provider-mode notice is restyled smaller/muted so it never outcompetes the answer.
- **Comparison / Technical details**: both screens gain a short eyebrow label ("Superfície de
  pesquisa" / "Nível técnico / auditoria") above their heading; no data-semantics change.
- i18n: every new string added to both `copy.ts` and `copy.en.ts`; the existing key-parity test
  (`copy.test.ts`) enforces this stays true.
- Not in this PR: any backend/API change, any change to detection/policy/treatment logic, any
  weakening of no-leak/review-before-provider/confirmation-token/panel-gating invariants.

### Demo completion criterion

The first demo track is complete when a prospective advisor can receive a URL and execute at least the controlled HR B0–B4 concept through the actual Python core without local setup.

T22/real provider improves this substantially and should be enabled when available, but FakeProvider remains valid for deterministic demonstration of the gateway mechanics.

## Deferred unless evidence creates a need

- persistent/shared `SQLiteVault` or equivalent;
- second real provider for robustness;
- Accounting/Finance third domain;
- multi-turn disclosure-history study;
- additional detector categories not required by the next frozen domain;
- full product-grade visual audit platform;
- agentic anonymization as an unversioned replacement for the deterministic B0–B4 path.

## Execution order

### Critical research path

1. M2 / HR pilot ✅
2. **T23 / Issue #36 — freeze post-pilot protocol** ✅
3. **T12 / Issue #9 — Docling ingestion/normalization** ✅
4. **Issue #56 — Contracts domain extensions** ✅ (merged into `develop` via PR #59)
5. **T24 / Issue #37 — Contracts v1 corpus/oracle** (in validation)
6. Verify M3 closure / confirmatory-readiness
7. Launch next frozen B0–B4 validation batch
8. Only then analyze authoritative comparative results under the pre-frozen protocol

**T22 real provider** proceeds in parallel with steps 3–7 (see T22 status above); it gates
authoritative utility/token/cost claims, not the Contracts corpus/oracle freeze itself.

### Parallel academic path

- T01 advisor/line framing.

### Parallel demo/application path

1. **T20 HTTP/application boundary**;
2. **T21 Next.js interactive demo**;
3. **T25 containerized deploy**;
4. consume **T22 real provider** when available.

This ordering is internal to the demo track and does not reorder the scientific critical path.

## References

- Experimental design: `docs/experimental-design.md`
- M2 pilot record: `docs/milestone-2-pilot.md`
- Advisor demo plan: `docs/advisor-demo.md`
- Contracts domain freeze: `docs/contracts-policy-matrix.md`
- Contracts v1 corpus: `corpus/contracts/v1/README.md` (coverage, limitations, freeze rule, freeze record)
- Contracts v1 corpus schema: `corpus/contracts/v1/SCHEMA.md`
- HR policy matrix: `docs/hr-policy-matrix.md`
- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- ADR 0002: `docs/adr/0002-deferred-restore-handles.md`
- M2 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/32
- T23 methodology freeze: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/36
- T22 real provider: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/30
- T12 Docling: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/9
- Contracts domain extensions: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/56
- T24 Contracts corpus: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/37
- M3 tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/38
- Demo tracker: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/41
- T20 CLI/API/MCP: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/28
- T21 Next.js UI: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/29
- T25 demo containers/deploy: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/42
- T26 deferred restore handles: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/67
- T29 local Vault Explorer: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/72
