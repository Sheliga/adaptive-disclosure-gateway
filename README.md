# Adaptive Disclosure Gateway

Research prototype for policy-constrained disclosure of organizational data to external LLMs.

The project investigates a local trust boundary that applies explicit organizational policies before data leaves the organization. Within the actions allowed by policy, task relevance can minimize disclosure. Pseudonym mappings remain local and can be used to reconstruct authorized responses after external inference.

## Research status

This repository supports a candidate master's research proposal for UTFPR PPGCA 2027. It is a research prototype, not a finished dissertation implementation and not evidence that B4 outperforms existing approaches.

**Milestone 1 and Milestone 2 are complete on `master`.** The project is now in post-pilot methodology freeze and confirmatory-readiness.

See [`docs/implementation-status.md`](docs/implementation-status.md) for the live execution plan, [`docs/experimental-design.md`](docs/experimental-design.md) for the B0–B4 comparison design and [`docs/milestone-2-pilot.md`](docs/milestone-2-pilot.md) for the factual first-pilot record.

## Current implementation status

Implemented:

- **B0 — Direct**;
- **B1 — Static Sanitization**;
- **B2 — Reversible Pseudonymization**;
- **B3 — Task-aware**;
- **B4 — Policy-governed**;
- deterministic HR detector;
- frozen `corpus/hr/v1` with 13 controlled cases and scoring oracle;
- fail-closed span validation/generalization;
- local vault + authorized reconstruction;
- opaque guessing-resistant pseudonyms;
- REQUEST / DOCUMENT / SESSION / ORGANIZATION pseudonym lifecycles;
- shared provider boundary + deterministic `FakeProvider`;
- metadata-only structural audit by default;
- OpenTelemetry metadata-only observability;
- no-leak security invariants across payload, task/prompt, provider request, exceptions, logs, telemetry, audit and derived identifiers;
- versioned contextual HR policy matrix (`hr-v2` / `hr-v3`);
- reproducible B0–B4 experiment runner;
- machine-readable conformance, exposure, utility, reconstruction, detector, timing, resource and volume metrics;
- B3/B4 implementation provenance and B4 policy/matrix-cell provenance;
- cross-process deterministic result comparison without weakening audit HMAC security.

Milestone 2 closed via PR #35 / merge `027a2baead4a3cee35db23cb8d4b79005a3a75d0`.

## Runtime

Canonical development/CI runtime: **CPython 3.13.13** (`>=3.13,<3.14`).

## Security model

Organizational policy is authoritative. User prompts, ingested documents and model responses are untrusted and cannot change policies, roles, permissions, pseudonym scope or vault state.

Policy/authorization resolution is fail-closed. Missing, invalid or ambiguous rules result in `BLOCK_REQUEST` rather than permissive fallback.

Disclosure actions:

- `PRESERVE`;
- `PSEUDONYMIZE`;
- `GENERALIZE`;
- `REMOVE`;
- `BLOCK_REQUEST`;
- `TASK_DEPENDENT`.

The egress boundary is broader than payload alone. Sensitive values must also be excluded from protected provider-facing task/prompt fields, exception chains/messages, logs, telemetry, audit records and guessable derived identifiers/hashes.

## Core flow

```text
input + GovernanceContext + task
        ↓
local detection/classification
        ↓
disclosure treatment (B0..B4)
        ↓
authorized external request
        ↓
provider boundary
        ↓
provider response
        ↓
local authorized reconstruction
        ↓
structural audit + experiment metrics
```

Document ingestion via Docling is a Milestone 3 infrastructure task. Direct normalized text remains the canonical controlled-experiment path.

## Experimental treatments

- **B0 — Direct** — direct/full external disclosure.
- **B1 — Static Sanitization** — static task-independent sanitization.
- **B2 — Reversible Pseudonymization** — static reversible pseudonymization with local vault/reconstruction.
- **B3 — Task-aware** — deterministic task-aware minimization using a generic fixed action space rather than contextual organizational policy.
- **B4 — Policy-governed** — explicit contextual policy constrains the action space first; task-awareness minimizes only within that space while retaining B3/B2 reversibility.

Pairwise design:

```text
B0 → B1 : local static disclosure control
B1 → B2 : reversibility/reconstruction
B2 → B3 : task-awareness
B3 → B4 : explicit contextual policy governance
```

## Milestone 2 pilot

The first controlled HR run is stored under:

`artifacts/experiments/hr/v1/13198a3b95bd49b88a62f591f3da1224/`

It executed the same 13 frozen HR cases under B0–B4 and produced versioned machine-readable outputs.

The run is classified as **`pilot_development`**, not held-out confirmatory evidence.

Factual highlights include:

- detector: 71 TP / 0 FP / 0 FN on the frozen HR spans;
- known B3 divergence `hr_salary_analysis_003/salary` remains visible rather than tuned away;
- FakeProvider supports deterministic pipeline/metric validation but not authoritative real-LLM utility/token/cost claims.

The pilot also surfaced methodological choices that must be frozen before authoritative analysis; see `docs/milestone-2-pilot.md` and T23 / Issue #36.

## Current research gate — Milestone 3

Milestone 3 tracker: **Issue #38 — Post-pilot protocol freeze and confirmatory-readiness**.

Critical path:

1. **T23 / Issue #36** — freeze post-pilot methodology, metrics, thresholds and confirmatory protocol.
2. In parallel: **T22 / Issue #30** — real provider, and **T12 / Issue #9** — Docling/normalized document ingestion.
3. **T24 / Issue #37** — freeze Contracts v1 second-domain corpus/oracle.
4. Verify confirmatory-readiness.
5. Launch the next frozen B0–B4 validation batch.

The main/confirmatory experiment must not be analyzed under rules selected after its results are seen.

## Post-pilot methodological questions

M2 intentionally leaves three questions for T23 rather than resolving them post hoc:

- how the binary unnecessary-disclosure rate and ordered representation exposure should be treated as primary/secondary metrics, especially for `PSEUDONYMIZE`;
- which frozen contextual `hr-v2/hr-v3` comparison defines the primary B3→B4 governance effect, since the original HR corpus uses `hr-v1`;
- which real provider/model/configuration and provider-class semantics are frozen for authoritative runs.

These are research-design decisions, not reasons to rewrite the completed M2 results.

## Integration/product surfaces

The Python core is planned to expose:

```text
Python application/core
├── CLI
├── HTTP API
└── MCP
```

Tracked in **T20 / Issue #28**. M2 now provides stable safe result concepts that these adapters may reuse. T20 remains non-blocking for Milestone 3.

A simplified **Next.js** audit/experiment UI is tracked in **T21 / Issue #29**. Its fixtures should now be based on the versioned safe T10 artifact schema rather than frontend-defined experiment semantics. It remains non-blocking.

## Provider strategy

`FakeProvider` remains the deterministic default for TDD and offline integration.

At least one real provider/model is required before authoritative claims about real-LLM task utility, provider tokens and external API cost. Real adapters must preserve the existing narrow provider contract, fail-closed behavior, safe error handling and native transport timeout/cancellation.

## Metrics available from the runner

- policy/conformance;
- ordered representation exposure;
- binary unnecessary disclosure;
- detector precision/recall/F1;
- utility information-sufficiency proxy for FakeProvider pilots;
- reconstruction accuracy;
- policy-restricted / impossible-under-policy / hard-block outcomes;
- treatment/provider/total pipeline latency;
- process CPU time / peak Python traced memory;
- disclosure-controlled payload and total provider-request bytes;
- versioned run/provenance metadata.

Real-provider token usage and external API cost remain T22-phase measurements.

## Validation domains

Current order:

1. **Human Resources** — first controlled B0–B4 pilot ✅;
2. **Contracts** — second-domain validation, with T12 ingestion infrastructure separated from T24 evaluation corpus/oracle;
3. **Accounting/Finance** — optional third domain if justified by time/evidence.

Primary datasets are synthetic/public-derived. Confidential employer data is not required and must not be committed.

## Framework independence

The scientific core is deterministic Python with small internal interfaces. LangChain, LangGraph, CrewAI, n8n, Docling, specific provider SDKs, Next.js and MCP are implementation/integration choices, not the scientific contribution.

## Scope

The system does not claim universal anonymization, legal compliance or complete prevention of information leakage. The research question is about experimentally controlling organizational disclosure under explicit policies while preserving useful task performance and local reversibility where authorized.
