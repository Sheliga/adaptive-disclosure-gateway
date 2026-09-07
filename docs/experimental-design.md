# Experimental design — B0–B4

This document formalizes the B0–B4 experimental treatments introduced in the
[README](../README.md#experimental-treatments). It closes the two acceptance
criteria of [issue #1](https://github.com/Sheliga/adaptive-disclosure-gateway/issues/1)
not already covered by the README: what is held constant between treatments,
and how each planned metric maps to the comparisons it is meant to answer.

This is a design document. It does not claim any treatment beyond B0–B2 is
implemented. Implementation status is tracked separately in
[`docs/implementation-status.md`](implementation-status.md); at the time of
writing, B0–B2 are the current Milestone 1 work item and B3/B4 are listed
there as Post-Milestone 1.

## Semantic names (T15)

The B0–B4 codes are frozen experimental identifiers and must never change.
The table below is the official mapping between each frozen code and the
semantic name used in this repository's documentation, code and telemetry
(English), alongside the Portuguese name used in the originating Trello
card and research conversation. Both columns name the same treatment; only
the frozen code carries experimental traceability.

| Code | English name (repo) | Portuguese (Trello/conversation) |
| --- | --- | --- |
| B0 | Direct | Direto |
| B1 | Static Sanitization | Sanitização |
| B2 | Reversible Pseudonymization | Pseudonimização |
| B3 | Task-aware | Task-aware |
| B4 | Policy-governed | Governado |

The canonical treatment sequence is **Direct → Static Sanitization →
Reversible Pseudonymization → Task-aware → Policy-governed**, i.e. B0 → B1 →
B2 → B3 → B4.

## Treatment definitions

- **B0 — Direct.** Direct/full external disclosure: the input is sent to the
  external provider unmodified — no detection, no policy gate, no
  transformation. It is the disclosure-control baseline against which every
  other treatment is measured.
- **B1 — Static Sanitization.** Detected sensitive spans are transformed by a
  fixed, task-independent category→action mapping (for example `REMOVE` or
  `GENERALIZE`) before the request leaves the trust boundary. The mapping
  does not consult task, purpose or contextual organizational policy, and the
  transformation is not reversible.
- **B2 — Reversible Pseudonymization.** Static reversible pseudonymization:
  the same detection and the same static, task-independent category→action
  mapping as B1, except that categories eligible for pseudonymization are
  replaced with a locally reversible pseudonym instead of being irreversibly
  removed or generalized. The mapping from pseudonym back to original value
  is kept in a local vault and is never sent externally, which makes
  authorized local reconstruction of the provider's response possible.
- **B3 — Task-aware.** Task-aware minimization without strong contextual
  organizational policy constraints: task relevance is used to choose the
  least-disclosing action that still supports the task, but this choice is
  not bounded by an explicit, policy-defined action space per category —
  unlike the `TASK_DEPENDENT` action's contract in the security model, which
  requires such a space. To isolate task-awareness in B2→B3 and policy
  constraints in B3→B4, B3 retains the same reversible pseudonymization,
  local vault, and authorized reconstruction capability available in B2.
- **B4 — Policy-governed.** Proposed approach: contextual organizational
  policy constraints (fail-closed policy resolution, an explicit
  policy-defined allowed-action space per category) combined with task-aware
  minimization *within* that allowed space, reversible pseudonymization, and
  local reconstruction. Task-awareness may only choose among actions the
  policy already allows; it can never expand what policy permits.

## Pairwise comparisons

Each step in B0→B1→B2→B3→B4 (Direct → Static Sanitization → Reversible
Pseudonymization → Task-aware → Policy-governed) is designed to isolate
exactly one variable so a measured difference can be attributed to that
variable rather than to an uncontrolled confound.

| Comparison | Variable isolated |
| --- | --- |
| B0 — Direct → B1 — Static Sanitization | Presence vs. absence of any local sanitization applied to the payload before it leaves the trust boundary (static sanitization vs. none). |
| B1 — Static Sanitization → B2 — Reversible Pseudonymization | Reversibility of the disclosure transformation: irreversible removal/generalization (B1) vs. reversible pseudonymization with a local vault and reconstruction path (B2). The detection stage and the fact that the mapping is static/task-independent do not change. |
| B2 — Reversible Pseudonymization → B3 — Task-aware | How the disclosure action per category is selected: a fixed, static category→action mapping (B2) vs. a dynamically chosen, task-relevance-driven action (B3). The reversible pseudonymization/vault/reconstruction mechanism is held constant; only whether task-awareness participates in the choice changes. |
| B3 — Task-aware → B4 — Policy-governed | Presence vs. absence of an explicit, policy-defined, fail-closed action-space constraint bounding what task-awareness may choose. B3 and B4 both retain task-awareness plus reversible pseudonymization/vault/reconstruction; the isolated variable is the contextual organizational policy constraint. |

## Held constant across treatments

The README states that "all treatments must use compatible request/result
contracts so they can run against the same cases." The items below expand
that requirement. None of them are asserted as already implemented; each is
stated as a requirement the experiment runner must satisfy so that a
difference observed between treatments reflects the isolated variable above
and not an incidental difference in setup.

- **Ingestion path.** All treatments in a given comparison must consume the
  same normalized input representation for the same case (for Milestone 1,
  simplified HR direct text input, per the README's "Milestone 1" section).
  Any future ingestion adapter (for example Docling) must produce this same
  representation before it can be used in a treatment comparison.
- **Corpus/cases.** Each case (document/text, governance context, task) must
  be run unmodified through every treatment being compared, per the README's
  compatible-contracts requirement. A treatment must not be evaluated on a
  different sample of cases than the treatment it is being compared against.
- **Provider model, snapshot and decoding configuration.** For Milestone 1,
  B0–B2 must run against the same deterministic `FakeProvider` (per ADR 0001
  and `docs/implementation-status.md`), so that the comparison is not
  confounded by external model variance; this component is not yet
  implemented. For any later experiment that exercises a real external
  provider, the model identity, model snapshot/version and decoding
  parameters (temperature, sampling strategy, max tokens, etc.) must be held
  identical across the treatments being compared — the repository does not
  yet document such a configuration.
- **Prompt scaffolding.** Whatever template or scaffolding is used to present
  the (possibly transformed) payload and task to the provider must be
  identical across treatments; only the disclosure-controlled contents of
  the payload may differ between treatments, per each treatment's definition
  above. The repository does not yet document a concrete prompt template —
  this must be established when the provider-facing request contract is
  implemented.
- **Detector output.** Treatments B1–B4 must consume the same detected spans
  and categories for a given case, produced by the same detection stage
  described in the README's core flow ("local detection/classification"
  precedes policy gates). B0 is not gated by detection by definition, but
  when a case is scored for metrics such as sensitive information exposure,
  the same detector output must be used to identify what B0 discloses. The
  deterministic detector is not yet implemented (tracked in issue #5).
- **Reversible mechanism where applicable.** B2, B3 and B4 must use the same
  pseudonymization, vault and authorized reconstruction implementation for a
  given experiment. B3 must not disable reconstruction or swap to a different
  pseudonym mechanism, because that would confound B2→B3 and B3→B4.
- **Evaluation harness.** Metric computation, scoring and the metadata-only
  audit pipeline described in the README's "Observability and audit" section
  must be shared across treatments so that results are comparable and are
  recorded in the same experiment-oriented format (for example JSONL). The
  experiment runner and full metric collection are listed as Post-Milestone 1
  in `docs/implementation-status.md` and are not yet implemented.

## Metrics mapping

The metrics below are the "Planned metrics" listed in the README. Each is
mapped to the comparison(s) it is intended to answer, and to the direction of
change that would support the research hypothesis that B4 reduces disclosure
relative to B0–B3 without an unacceptable loss of task utility.

| Metric | Comparison(s) it answers | Direction supporting the hypothesis |
| --- | --- | --- |
| Policy violation rate | B3 → B4 (primary); B0 → B1 | Decreases from B0 through B4, with the largest drop at B3 → B4 once an explicit policy-defined action space is enforced; B4 should approach zero. |
| Unnecessary disclosure | B0 → B1; B2 → B3; B3 → B4 | Decreases at each step; B2 → B3 should show a further reduction because task-awareness withholds task-irrelevant content that a static mapping would still disclose; B3 → B4 should not increase it. |
| Sensitive information exposure | B0 → B1 (primary); B1 → B2; B3 → B4 | Sharp decrease from B0 to B1; remains at or below the B1/B2 level through B3 and B4 — task-awareness and policy constraints must not regress exposure of categories such as `medical_data`. |
| Task utility / task success | B1 → B2; B2 → B3 (primary); B3 → B4 | Increases from B1 to B2 (reversible pseudonyms preserve more usable structure than irreversible removal) and from B2 to B3 (task-aware selection retains what the task needs); B3 → B4 should hold utility roughly constant despite the added policy constraint. |
| Reconstruction accuracy | B1 → B2; B2 → B3; B3 → B4 | Defined for B2, B3 and B4 because all three retain the same vault/reconstruction mechanism. High-fidelity round-trip should remain stable across B2→B3→B4; policy/task logic must not degrade reconstruction correctness. |
| Latency | B0 → B1 → B2 → B3 → B4 | Monotonic increase is expected as detection, policy evaluation, task analysis and vault operations are added. No numeric acceptance threshold is fixed yet; the practical bound must be calibrated in the pilot and frozen before the main experiment. |
| CPU and memory usage | B0 → B1 → B2 → B3 → B4 | Monotonic non-decrease is expected. No numeric acceptance threshold is fixed yet; the practical bound must be calibrated in the pilot and frozen before the main experiment. |
| Transmitted tokens/data volume | B0 → B1 (primary); B2 → B3; B3 → B4 | Decreases sharply from B0 to B1; B3/B4 should be at or below B1/B2 when task-aware minimization omits fields a static mapping would still transmit. |
| Estimated external API cost | Same as transmitted tokens/data volume | Decreases together with transmitted volume, B0 through B4. |

## Pilot calibration follow-up

The main experiment must not invent a post-hoc "practical" performance bound.
During the pilot, observed latency/CPU/memory overhead should be used to define
an explicit acceptance or interpretation threshold. That threshold, together
with the measurement procedure, must be frozen before the main experiment is
run so that performance conclusions are not adjusted after seeing the final
results.
