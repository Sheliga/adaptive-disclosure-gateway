# T23 review status

Last updated: 2026-09-11

This document records the **current review state** of T23 / Issue #36 while PR #53 is still open. It is intentionally separate from `post-pilot-protocol-v1.md`: the protocol candidate is not yet authoritative until the remaining review blockers are resolved and the PR is approved/merged.

## Current state

- PR: #53 — `research/t23-freeze-protocol` → `develop`
- PR is open and mergeable.
- T23 is **in progress / final methodological review**.
- `post-pilot-v1` must **not** yet be treated as the completed M3 protocol-freeze gate.
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

## Remaining blockers before merge

### 1. Binary metric vs first cumulative threshold

The historical binary unnecessary-disclosure metric is **not always mathematically identical** to `P(exposure >= PSEUDONYMIZE)` under the current proposed ordinal/cumulative population definition.

The historical scorer uses every `NOT_REQUIRED` span as its denominator, including blocked or otherwise unscorable spans. `BLOCK_REQUEST`/unscorable spans do not enter the numerator.

The proposed cumulative family currently defines its denominator from scorable `exposure_level` spans only.

Therefore the two values coincide only when the relevant `NOT_REQUIRED` population is fully scorable and unblocked. The protocol, `experimental-design.md`, `implementation-status.md` and PR description must not claim unconditional identity/recoverability unless the denominator definition is deliberately changed and justified without rewriting the historical metric.

Preferred correction: preserve both definitions and state the conditional equivalence explicitly.

### 2. Macro aggregation of ordinal max/median

Per-case proportions and exceedance probabilities can be macro-averaged across cases.

Per-case ordinal `max`/`median` values must **not** be converted to 0/1/2/3 and arithmetically averaged, because that would reintroduce the equal-spacing assumption T23 explicitly removed.

Use an ordinal-safe corpus summary instead, such as:

- distribution/counts of cases by maximum level;
- distribution/counts of cases by median level;
- an ordinal median across per-case levels where appropriate.

### 3. Historical scorer documentation

`src/adaptive_disclosure_gateway/experiments/scoring/unnecessary_disclosure.py` still labels the binary unnecessary-disclosure measure as `Primary metric` in its module docstring.

Update the documentation to reflect the T23 role split while preserving the implementation and historical formula unchanged.

## Scientific order

The current order remains:

`T23 → T12 → Contracts domain extensions → T24 → next B0–B4 batch`

T22 / real provider proceeds in parallel.

Preliminary representation-independent Contracts work may occur before T12 is complete, but the **final confirmatory freeze** of Contracts corpus/oracle/offsets/canonical representation must wait until T12 has stabilized the ingestion/normalization path.

## Completion condition

T23 can be marked complete only after:

1. the three items above are corrected;
2. review confirms the protocol and supporting docs are internally consistent;
3. applicable gates pass;
4. PR #53 is approved and merged into `develop`.

Until then, Issue #36 and the T23 Trello card remain active.