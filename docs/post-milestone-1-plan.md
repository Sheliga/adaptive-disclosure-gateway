# Post-Milestone 1 plan

Last updated: 2026-09-07.

Milestone 1 is complete. The project is now split into three parallel tracks so product/integration work does not become an accidental prerequisite for the scientific core.

## Track A — scientific critical path

### T09 / Issue #4 — freeze HR minicorpus and ground truth

This is the immediate engineering/methodological gate.

Phase A must version and freeze approximately 12–20 controlled HR cases before B3 implementation starts.

Each case must contain at least:

- `sample_id`;
- controlled input text/document;
- `GovernanceContext`;
- task/instruction;
- expected sensitive spans/categories;
- `policy_version`;
- expected action or acceptable action set per information unit;
- task-necessity oracle;
- expected answer or objectively verifiable property;
- expected `BLOCK_REQUEST` behavior where applicable;
- pseudonym/reconstruction expectations where applicable.

Primary task-necessity labels are `REQUIRED` and `NOT_REQUIRED`. `HELPFUL` may exist only as an auxiliary annotation until an objective scoring rule is frozen.

Ground truth is an evaluation oracle only. Treatments must never receive it as privileged input.

Minimum HR task families:

1. authorized salary analysis;
2. team summary/description where salary is not required;
3. aggregation by department without individual identity;
4. a request containing medical/prohibited information that must block.

Exit criterion: schema + cases + annotations are versioned and frozen.

### T07 / Issue #6 — B3 Task-aware

Starts only after T09 Phase A exit criterion is met.

Pilot implementation uses a deterministic task analyzer behind a replaceable interface. B3 retains B2 pseudonymization, vault, reconstruction and provider behavior. The B2→B3 comparison must isolate task-awareness.

B3 uses a generic fixed action space per category/type, independent of `domain`, `purpose`, `requester_role`, `provider_class` and contextual `policy_version`.

### T08 / Issue #7 — B4 Policy-governed

Starts after B3 exists and reuses the same task analyzer, pseudonymization, vault, reconstruction and provider boundary.

B4 adds explicit contextual policy constraints over:

- `domain`;
- `purpose`;
- `requester_role`;
- `provider_class`;
- `policy_version`.

Requester-specific overrides remain supported by the architecture but outside the initial primary experimental matrix.

The B3→B4 comparison must isolate explicit policy governance.

### T10 / Issue #8 — runner and metrics

Authoritative pilot execution depends on T09 + T07 + T08.

Core measurement rules:

- detector/scoring work around B0 is not B0 treatment latency;
- record timings by stage;
- separate disclosure-controlled payload volume from task/prompt scaffolding;
- score unnecessary disclosure from `REQUIRED`/`NOT_REQUIRED` ground truth;
- report correctly blocked impossible-under-policy cases separately from ordinary utility failures;
- calibrate utility/overhead interpretation thresholds from the pilot and freeze them before the main experiment;
- outputs must be machine-readable and stable for later statistics/UI consumption.

### T22 / Issue #30 — real provider

Does not block T09/B3/B4, but is required before authoritative claims about real-model utility, provider tokens and API cost.

`FakeProvider` remains the default for TDD and deterministic integration.

## Track B — product/integration surfaces (parallel, non-blocking)

### T20 / Issue #28 — CLI + HTTP API + MCP

Expose the same Python application/core through three thin adapters:

```text
Python application/core
├── CLI
├── HTTP API
└── MCP
```

No adapter may reimplement policy resolution, task-awareness, pseudonymization, reconstruction, audit or scoring.

### T21 / Issue #29 — simplified Next.js UI

Build the UI now, but keep it off the scientific critical path.

Phase 1 uses versioned synthetic fixtures/mock JSON.
Phase 2 integrates with the HTTP API from T20.

The UI consumes treatment/audit/result contracts; it must not define scientific metrics or treatment semantics independently.

Safe/default views do not expose raw sensitive values, vault mappings, secrets or private policy content.

## Track C — academic submission (parallel)

### T01 — line/advisor selection

T01 runs independently from Track A and Track B.

It must be resolved before freezing the final PPGCA framing, line, intended advisor and final submission version, but it does not block T09, B3, B4, the pilot, CLI/API/MCP or the UI.

Current provisional advisor shortlist:

1. Daniel Fernando Pigatto;
2. Michel Albonico;
3. Luiz Celso Gomes Júnior.

## Document/domain expansion after the first HR pilot

### T12 / Issue #9 — Docling

Docling starts after the first controlled B0–B4 HR pilot.

Order:

1. HR pilot with direct text;
2. Contracts as second validation domain;
3. Accounting/Finance only if schedule permits.

Docling is infrastructure and must remain constant across treatments.

## Dependency graph

```text
T01 advisor/line ────────────────────────────────→ final academic framing/submission

T09 HR corpus + ground truth
        ↓
T07 B3 Task-aware
        ↓
T08 B4 Policy-governed
        ↓
T10 pilot/runner/metrics ─────→ T22 real-provider authoritative runs
        ↓
Contracts + T12 Docling

T20 CLI/API/MCP ───────────────┐
                               ├─ parallel, non-blocking
T21 Next.js UI (fixtures first)┘
```

## Current gate

The only hard gate before B3 is T09 Phase A: the HR minicorpus schema, cases and ground truth must be versioned/frozen first.
