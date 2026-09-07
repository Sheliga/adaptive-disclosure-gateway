# Adaptive Disclosure Gateway

Research prototype for policy-constrained disclosure of organizational data to external LLMs.

The project investigates a local trust boundary that applies explicit organizational policies before data leaves the organization. Within the actions allowed by policy, task relevance can minimize disclosure. Pseudonym mappings remain local and can be used to reconstruct authorized responses after external inference.

## Research status

This repository supports a candidate master's research proposal for UTFPR PPGCA 2027. It is a research prototype, not a finished dissertation implementation and not evidence that B4 outperforms existing approaches.

## Current implementation status

**Milestone 1 is complete on `master`.**

Implemented:

- **B0 — Direct**;
- **B1 — Static Sanitization**;
- **B2 — Reversible Pseudonymization**;
- deterministic HR detector;
- fail-closed span validation/generalization;
- local vault + authorized reconstruction;
- opaque guessing-resistant pseudonyms;
- REQUEST / DOCUMENT / SESSION / ORGANIZATION pseudonym lifecycles;
- shared provider boundary + deterministic `FakeProvider`;
- shared B0/B1/B2 execution path;
- metadata-only structural audit by default;
- OpenTelemetry metadata-only observability;
- no-leak security invariants across payload, task/prompt, provider request, exceptions, logs, telemetry, audit and derived identifiers.

PR #27 completed Milestone 1 and was merged at `28fe292cf1e7cb1dfccb999c3f04aed1016f5d8e`.

See [`docs/implementation-status.md`](docs/implementation-status.md) for the live execution plan and [`docs/experimental-design.md`](docs/experimental-design.md) for the frozen B0–B4 comparison design.

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

Document ingestion via Docling is planned after the first controlled B0–B4 HR pilot. Direct text remains the canonical controlled-experiment input.

## Experimental treatments

- **B0 — Direct** — direct/full external disclosure.
- **B1 — Static Sanitization** — static task-independent sanitization.
- **B2 — Reversible Pseudonymization** — static reversible pseudonymization with local vault/reconstruction.
- **B3 — Task-aware** — deterministic task-aware minimization in the pilot, using a generic fixed action space rather than contextual organizational policy.
- **B4 — Policy-governed** — proposed treatment: explicit contextual policy constrains the action space first; task-awareness minimizes only within that space while retaining B3/B2 reversibility.

Pairwise design:

```text
B0 → B1 : local static disclosure control
B1 → B2 : reversibility/reconstruction
B2 → B3 : task-awareness
B3 → B4 : explicit contextual policy governance
```

## Current engineering gate

The immediate next research task is **T09 / Issue #4**: build and freeze a controlled HR pilot corpus/ground truth of approximately **12–20 cases**.

Primary task-necessity labels are:

- `REQUIRED`;
- `NOT_REQUIRED`.

Ground truth is used only for scoring and must never be privileged treatment input.

Once T09 Phase A is versioned/frozen, **T07/B3** is released.

## Next research path

1. **T09 / Issue #4** — HR pilot corpus + ground truth.
2. **T07 / Issue #6** — B3 Task-aware.
3. **T08 / Issue #7** — B4 Policy-governed.
4. **T10 / Issue #8** — controlled B0–B4 pilot + runner/metrics.
5. Freeze utility/overhead interpretation thresholds from the pilot.
6. **T12 / Issue #9** — Docling + Contracts as second-domain validation.
7. **T22 / Issue #30** — at least one real provider before authoritative utility/token/cost claims.
8. Main experiment.

The PPGCA line/advisor task (**T01**) is a parallel academic track and does **not** block implementation.

## Integration/product surfaces

The Python core is planned to expose:

```text
Python application/core
├── CLI
├── HTTP API
└── MCP
```

Tracked in **T20 / Issue #28**. These adapters must stay thin and must not duplicate policy, task-awareness, pseudonymization, reconstruction or scoring logic.

A simplified **Next.js** audit/experiment UI is tracked in **T21 / Issue #29**. It may start now from versioned synthetic fixtures and later consume the Python HTTP API. The UI is explicitly non-blocking and does not define scientific metrics/treatment semantics.

## Provider strategy

`FakeProvider` remains the deterministic default for TDD and offline integration.

At least one real provider/model is required before authoritative claims about real-LLM task utility, provider tokens and external API cost. Real adapters must preserve the existing narrow provider contract, fail-closed behavior, safe error handling and native transport timeout/cancellation.

## Planned metrics

- policy violation rate;
- unnecessary/sensitive disclosure;
- detector precision/recall/F1;
- task utility / task success;
- reconstruction accuracy;
- latency;
- CPU/memory;
- transmitted data/tokens;
- estimated external API cost.

Performance measurements are stage-aware. Detector/scoring work around B0 must not be silently attributed to B0 treatment latency. Disclosure-controlled payload volume is reported separately from task/prompt scaffolding.

## Validation domains

Current planned order:

1. **Human Resources** — controlled pilot and first B0–B4 validation;
2. **Contracts** — second priority, especially semantic relationships between parties/obligations;
3. **Accounting/Finance** — optional third domain if the pilot shows it fits the schedule.

Primary datasets are synthetic/public-derived. Confidential employer data is not required and must not be committed.

## Framework independence

The scientific core is deterministic Python with small internal interfaces. LangChain, LangGraph, CrewAI, n8n, Docling, specific provider SDKs, Next.js and MCP are implementation/integration choices, not the scientific contribution.

## Scope

The system does not claim universal anonymization, legal compliance or complete prevention of information leakage. The research question is about experimentally controlling organizational disclosure under explicit policies while preserving useful task performance and local reversibility where authorized.
