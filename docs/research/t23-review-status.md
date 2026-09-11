# T23 review status

Last updated: 2026-09-11

This document records the **current review state** of T23 / Issue #36 while PR #53 is still open. It is intentionally separate from `post-pilot-protocol-v1.md`: the protocol candidate is not yet authoritative until it is approved/merged.

## Current state

- PR: #53 — `research/t23-freeze-protocol` → `develop`
- PR is open and mergeable.
- T23 is **in progress / final methodological review**.
- `post-pilot-v1` must **not** yet be treated as the completed M3 protocol-freeze gate.
- The previously identified methodological blockers have been corrected in the candidate and
  are awaiting human verification.
- No B3/B4, HR corpus, HR policy or M2 artifact tuning is authorized by this review.

## Accepted corrections already in PR #53

The previous review round was incorporated successfully:

- primary unnecessary-exposure metric changed from arithmetic mean of ordinal ranks to an ordinal/cumulative family;
- T12 is explicitly required before the final confirmatory Contracts freeze;
- T22 remains parallel;
- B0 is a control/reference baseline and only provides a ceiling of information availability under the FakeProvider information-sufficiency proxy, not guaranteed maximum real-provider task utility;
- `frozen_date` corrected to 2026-09-11;
- T21 fourth slice status corrected as integrated through PRs #51/#52 while T21 itself remains open;
- `post-pilot-v1` remains descriptive-only: any future inferential method must be defined in a later protocol version before the relevant batch results are inspected.

## Review corrections now incorporated

### 1. Binary metric vs first cumulative threshold

The candidate now states that the historical binary unnecessary-disclosure metric is **not always mathematically identical** to `P(exposure >= PSEUDONYMIZE)` under the ordinal/cumulative population definition.

The historical scorer uses every `NOT_REQUIRED` span as its denominator, including blocked or otherwise unscorable spans. `BLOCK_REQUEST`/unscorable spans do not enter the numerator.

The proposed cumulative family currently defines its denominator from scorable `exposure_level` spans only.

The protocol preserves both definitions and now formalizes `N = S + B + U`, the common
numerator `T`, binary `T/N`, threshold `T/S`, their coincidence/divergence conditions,
coverage `S/N`, explicit `B`/`U` counts and empty-population behavior.

### 2. Macro aggregation of ordinal max/median

Per-case proportions and exceedance probabilities can be macro-averaged across cases.

Per-case ordinal `max`/`median` values are no longer specified as arithmetic means. The
candidate uses ordinal-safe corpus summaries:

- distribution/counts of cases by maximum level;
- distribution/counts of cases by median level;
- an ordinal median across per-case levels where appropriate.

### 3. Historical scorer documentation

`src/adaptive_disclosure_gateway/experiments/scoring/unnecessary_disclosure.py` now labels the
binary measure as the historical M2 metric preserved as secondary. Its implementation and
formula remain unchanged. A focused regression also pins the blocked-span denominator behavior.

## Scientific order

The current order remains:

`T23 → T12 → Contracts domain extensions → T24 → next B0–B4 batch`

T22 / real provider proceeds in parallel.

Preliminary representation-independent Contracts work may occur before T12 is complete, but the **final confirmatory freeze** of Contracts corpus/oracle/offsets/canonical representation must wait until T12 has stabilized the ingestion/normalization path.

## Completion condition

T23 can be marked complete only after:

1. human review confirms the corrected protocol and supporting docs are internally consistent;
2. applicable gates pass;
3. PR #53 is approved and merged into `develop`.

Until then, Issue #36 and the T23 Trello card remain active.
