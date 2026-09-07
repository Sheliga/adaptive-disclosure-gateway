# Implementation status

Last updated: 2026-09-07 — PR #27 merged into `master` at `28fe292cf1e7cb1dfccb999c3f04aed1016f5d8e`. The post-merge `master` CI run completed successfully. **Milestone 1 is complete.**

This file tracks **what is implemented now**. Architectural decisions belong in ADRs; experimental definitions belong in `docs/experimental-design.md`; historical PR/Issue descriptions are not rewritten merely to reflect newer terminology.

## Current phase

The project has moved from **building the first functional vertical slice** to **implementing the research treatments and experimental evaluation**.

Milestone 1 established the common execution and security boundary for:

- direct HR text input;
- B0 — Direct;
- B1 — Static Sanitization;
- B2 — Reversible Pseudonymization;
- deterministic `FakeProvider`;
- local vault and authorized reconstruction;
- metadata-only structural audit by default;
- end-to-end execution through one shared pipeline.

The next research-facing work is B3 — Task-aware, B4 — Policy-governed, the controlled corpus/ground truth, and the experiment runner/metrics.

## Milestone 1 — completed on master

### Foundation and experimental contracts

- Milestone 1 architecture frozen in ADR 0001.
- Canonical treatment sequence frozen as **B0 — Direct → B1 — Static Sanitization → B2 — Reversible Pseudonymization → B3 — Task-aware → B4 — Policy-governed**.
- `b0`–`b4` remain frozen experimental identifiers; semantic names are used in human-facing text and code names.
- `DisclosureAction`: `PRESERVE`, `PSEUDONYMIZE`, `GENERALIZE`, `REMOVE`, `BLOCK_REQUEST`, `TASK_DEPENDENT`.
- `GovernanceContext`, versioned YAML policy engine, policy precedence and fail-closed resolution.
- Role/user pseudonym-scope ceilings.
- OpenTelemetry + OTLP foundation with local Jaeger.
- GitHub Actions CI on CPython 3.13.13.

### B0 — Direct

T18 / Issue #25, merged in PR #27.

- `DirectDiscloser` exposes `Treatment.DIRECT`.
- The external payload is exactly `request.text`.
- Detection, policy, vault and task-awareness do not participate in B0's transformation.
- B0 remains intentionally unsafe as the experimental control.
- Shared scoring/detection performed around B0 by the experiment pipeline must not be attributed to B0's own treatment latency.

### B1 — Static Sanitization

T05 / Issue #5 plus security/generalization follow-ups T14 / Issue #17 and T13 / Issue #16.

- Deterministic local detector for the controlled HR slice.
- Static category-to-action behavior independent of task-awareness.
- Shared fail-closed `SensitiveSpan` validation rejects malformed, missing, out-of-range or text-mismatching offsets before slicing.
- Semantic `GENERALIZE` strategies are shared by B1/B2; unconfigured or configured-but-unparseable values fail closed.
- Error messages and telemetry are pinned against sensitive-value leakage.

### B2 — Reversible Pseudonymization

T06 / Issue #3, with T17 / Issue #24 and T16 / Issue #23; core merged in PR #22 and completed by PR #27.

- `Vault` abstraction and `InMemoryVault`.
- `ReversiblePseudonymizer` with local-only mappings and authorized reconstruction.
- Opaque CSPRNG pseudonyms rather than public deterministic digests of originals.
- Collision handling and multi-entity round trip.
- Real pseudonym-scope lifecycle semantics:
  - REQUEST → `request_id`;
  - DOCUMENT → `document_id`;
  - SESSION → `session_id`;
  - ORGANIZATION → organization/domain partition as defined by policy.
- Missing identifiers required by the resolved scope fail closed; there is no fallback to requester identity/role.
- B2 remains task-independent so B2→B3 can isolate task-awareness.

### External-provider boundary

T11 / Issue #12, merged in PR #27.

- Shared `Provider` protocol with `ProviderRequest` / `ProviderResponse`.
- Provider-facing request surface is intentionally narrow: payload + task only.
- Deterministic offline `FakeProvider` for controlled B0/B1/B2 comparisons.
- `provider_class` mismatch is rejected before `provider.generate()` is submitted.
- Errors/timeouts fail closed: no retry and no fallback to B0 — Direct.
- `ProviderError.provider_invoked` records whether `generate()` was actually submitted, so audit state does not claim a provider call that never occurred.
- Sensitive content detected only in `request.task` blocks B1/B2 before the provider boundary; B0 is deliberately exempt as the unsafe control.
- Provider metadata includes model id, snapshot, decoding configuration and transmitted-byte measurement.

Implementation note for future real providers: the current thread-based wrapper bounds caller wait but cannot terminate a Python worker thread already executing. Real network adapters must also use native transport/client timeout or cancellation.

### Shared end-to-end pipeline and audit

T19 / Issue #26, merged in PR #27.

`pipeline.run_disclosure_case(...)` is the shared execution path for B0/B1/B2:

```text
input + GovernanceContext + task
→ detect
→ treatment.sanitize(...)
→ provider boundary when allowed
→ local reconstruction when supported
→ structural AuditRecord
```

The call site does not branch on a specific treatment enum member. Reconstruction and the unsafe-control exemption are capability-based contracts.

`audit.AuditRecord` covers detection, decisions, transformation, provider and reconstruction stages. By default it carries metadata only and never raw input, external payload, provider response, reconstructed response or vault content.

Security properties pinned by tests include:

- `REMOVE` originals are absent from what the provider actually receives;
- `BLOCK_REQUEST` prevents the provider call entirely;
- task/prompt is part of the egress surface and cannot bypass B1/B2 disclosure control;
- vault originals/mappings do not reach provider fields or OTel attributes;
- authorized B2 responses reconstruct locally;
- default audit correlation hashes use locally keyed HMAC-SHA256 rather than public unkeyed SHA-256;
- the audit key is never serialized;
- provider errors/timeouts still produce metadata-only audit outcomes;
- provider exception messages are not stored in the audit;
- `decoding_config` is recorded per successful provider response;
- `audit.provider.called` distinguishes a pre-flight mismatch from a provider call that was actually submitted.

The PR #27 suite reached **170 tests**, and the post-merge CI on `master` completed successfully.

## Milestone 1 exit criteria

All functional exit criteria are met on `master`:

- malformed/invalid span metadata fails closed — **met**;
- `REMOVE` content does not reach the external provider — **met**;
- `BLOCK_REQUEST` stops the external request — **met**;
- pseudonyms respect the real authorized lifecycle of their resolved scope — **met**;
- external pseudonyms are not based on a publicly guessable digest — **met**;
- vault originals/secrets do not reach provider or telemetry — **met**;
- authorized response reconstruction works end to end — **met**;
- audit is metadata-only by default and avoids public guessing-oracle hashes — **met**;
- deterministic `FakeProvider` works through the shared B0/B1/B2 path — **met**;
- provider failures remain fail-closed and auditable — **met**;
- CI on merged `master` is green — **met**.

## Next research implementation

### T07 / Issue #6 — B3 — Task-aware

Not started.

B3 must introduce task-awareness while retaining B2's reversible pseudonymization/vault/reconstruction mechanism. The B2→B3 comparison must isolate the addition of task relevance rather than accidentally changing reversibility or provider behavior.

### T08 / Issue #7 — B4 — Policy-governed

Not started.

B4 is the principal proposed treatment: task-aware minimization operates only inside the action space allowed by explicit contextual organizational policy. The reversible mechanism remains the same as B3 so B3→B4 isolates the policy-governance constraint.

### T09 / Issue #4 — controlled corpus and ground truth

Not started.

Build synthetic/public-derived cases with explicit ground truth for sensitivity, applicable policy, permitted transformations, task necessity and expected answer. HR is the initial slice; Finance and Contracts provide broader validation, with Contracts important for semantic relationships between parties/obligations.

This work can progress in parallel with B3/B4 implementation, but the ground truth must be frozen before authoritative experiment results are produced.

### T10 / Issue #8 — experiment runner and metrics

Not started.

The prerequisite engineering boundary is now complete. Authoritative runs still depend on B3, B4 and the controlled corpus.

Planned metrics include policy violations, unnecessary disclosure/exposure, utility/task success, reconstruction accuracy, latency, CPU/memory, transmitted data/tokens and estimated external API cost.

Measurement rules already fixed by review:

- detector/scoring overhead executed around B0 must not be attributed to B0 treatment latency;
- record timings by stage;
- prompt/task scaffolding held constant across treatments should be separated from the disclosure-controlled payload in volume/cost metrics, while total transmission can be recorded separately when useful.

### T12 / Issue #9 — Docling ingestion

Not started and not required for the controlled text-first experiment slice.

Docling remains infrastructure rather than a claimed research contribution. It should preserve useful document structure while exposing a normalized internal representation independent of Docling APIs.

### T01 — PPGCA line/advisor reevaluation

Independent of implementation. This remains research/program planning rather than a software dependency.

## Deferred / non-blocking engineering

These items are intentionally outside Milestone 1 and do not invalidate its completion:

- `SQLiteVault` or another persistent/shared vault backend;
- a detector rule emitting `birth_date` (the generalization strategy exists but is currently unreachable);
- Hypothesis-based pseudonym property tests;
- real external/Ollama provider adapters with native transport timeout/cancellation;
- visual audit/comparison UI;
- document ingestion via Docling.

They should be promoted into explicit tickets when they become necessary for the experiment or proposal, rather than being treated as hidden Milestone 1 debt.

## Recommended execution order

1. T07 / Issue #6 — B3 — Task-aware.
2. T08 / Issue #7 — B4 — Policy-governed.
3. T09 / Issue #4 — finalize controlled corpus/ground truth (can progress in parallel with 1–2).
4. T10 / Issue #8 — experiment runner and authoritative metrics.
5. T12 / Issue #9 — Docling when document-oriented validation becomes useful.

T01 can proceed independently of this engineering order.

## References

- ADR 0001: `docs/adr/0001-milestone-1-architecture.md`
- Experimental design: `docs/experimental-design.md`
- Foundation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/10
- B0–B4 design PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/13
- Detector/B1 PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/15
- Span offset validation PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/19
- Semantic naming PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/21
- B2 core + semantic GENERALIZE PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/22
- Milestone 1 completion PR: https://github.com/Sheliga/adaptive-disclosure-gateway/pull/27
- B2: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/3
- B3: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/6
- B4: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/7
- Controlled corpus: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/4
- Experiment runner: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/8
- Docling ingestion: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/9
- Provider boundary: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/12
- Semantic GENERALIZE: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/16
- Pseudonym lifecycles: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/23
- Pseudonym guessing resistance: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/24
- B0 — Direct: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/25
- End-to-end path + audit: https://github.com/Sheliga/adaptive-disclosure-gateway/issues/26
