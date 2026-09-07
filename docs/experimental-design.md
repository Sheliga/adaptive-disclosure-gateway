# Experimental design — B0–B4

This document defines the controlled comparison across the frozen treatment sequence:

**B0 — Direct → B1 — Static Sanitization → B2 — Reversible Pseudonymization → B3 — Task-aware → B4 — Policy-governed.**

The identifiers `b0`–`b4` are frozen. Implementation status is tracked in [`implementation-status.md`](implementation-status.md).

## Treatment definitions

### B0 — Direct

Unsafe control treatment. The original input is sent without disclosure-control transformation. Detection/scoring may still be executed externally by the evaluation harness for outcome comparison, but that work is not part of B0 treatment latency.

### B1 — Static Sanitization

Detected sensitive information is transformed by a fixed, task-independent static mapping. No task-awareness participates in action selection.

### B2 — Reversible Pseudonymization

Retains B1's task-independent/static behavior while adding reversible local pseudonymization, vault isolation and authorized reconstruction. Pseudonym/vault/reconstruction behavior is the reference mechanism reused by B3/B4.

### B3 — Task-aware

Adds task-aware minimization while retaining B2's reversible mechanism.

For the pilot:

- task analysis is deterministic and implemented behind a replaceable interface;
- the analyzer receives only the case/task, never ground-truth labels;
- B3 uses a **generic fixed action space per category/type**;
- that generic action space is independent of `domain`, `purpose`, `requester_role`, `provider_class` and contextual `policy_version`;
- task relevance chooses the least-disclosing useful action inside that generic space.

This design allows B2→B3 to isolate task-awareness.

### B4 — Policy-governed

Proposed treatment. B4 retains B3's task analyzer, reversible pseudonymization, vault, reconstruction and provider boundary, but adds explicit contextual organizational policy constraints.

Policy resolves the permitted action space first. Task-awareness may then minimize only within that space and can never expand permission.

Primary contextual dimensions varied by the experiment are:

- `domain`;
- `purpose`;
- `requester_role`;
- `provider_class`;
- `policy_version`.

Requester-specific overrides remain supported by the architecture but are outside the initial primary matrix. Pseudonym scope remains governed separately.

## Pairwise causal comparisons

| Comparison | Variable isolated |
| --- | --- |
| B0 → B1 | Presence of static local disclosure control vs. direct disclosure. |
| B1 → B2 | Reversibility/local reconstruction while static task-independent behavior is otherwise retained. |
| B2 → B3 | Addition of task-aware action selection while the reversible mechanism remains constant. |
| B3 → B4 | Addition of explicit contextual organizational policy constraints while task-awareness/reversibility remain constant. |

## Controlled corpus and ground truth

### Phase A — HR pilot

Before B3 implementation, version and freeze an HR pilot corpus of approximately **12–20 cases**.

Each case must contain at least:

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

### Task necessity oracle

Primary labels:

- `REQUIRED`;
- `NOT_REQUIRED`.

`HELPFUL` may be stored only as auxiliary annotation initially. It must not be mixed into the primary unnecessary-disclosure metric unless an objective criterion is later frozen.

Ground truth is strictly an evaluation oracle. Treatments do not receive it as privileged input.

### Minimum HR task families

The pilot must include at least:

1. authorized salary analysis;
2. team summary/description where salary is not required;
3. aggregation by department without individual identity;
4. a request containing medical/prohibited information that should block.

Each family must use a response or property that can be scored without relying only on subjective judgment whenever feasible.

### Phase B — broader validation

After the first B0–B4 HR pilot:

1. **Contracts** is the second priority domain, especially for party-role, obligation, deadline, penalty and semantic-relation preservation;
2. **Accounting/Finance** is an optional third domain if the pilot indicates it fits the schedule.

Docling/document parsing is not introduced before the first controlled HR pilot.

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

### Authoritative utility/token/cost results

At least one real provider/model is required before making authoritative claims about:

- task utility with an actual LLM;
- provider tokens;
- external API cost.

For comparable B0–B4 batches, freeze and record:

- provider/model id;
- snapshot/version when available;
- decoding configuration;
- task/prompt scaffolding;
- date/run metadata;
- transmitted bytes/tokens where measurable.

Real network adapters must use native client/transport timeout or cancellation in addition to the caller-side deadline already present in the shared boundary.

## Metrics

### Policy/conformance

- policy violation rate;
- incorrectly widened permissions;
- correctly blocked impossible-under-policy cases;
- false/excessive blocks where relevant.

A task that cannot be executed externally because required information is forbidden by policy is **not** counted as an ordinary utility failure. It is reported as a separate correctly-blocked/non-executable policy outcome when B4 behaves as specified.

### Exposure

- sensitive information exposure;
- unnecessary disclosure;
- transmitted controlled-content bytes/tokens;
- detector precision/recall/F1.

Primary unnecessary-disclosure metric:

> transmitted sensitive units labeled `NOT_REQUIRED` / total sensitive units labeled `NOT_REQUIRED` present in the case.

Also report absolute count and associated bytes/tokens. Exposure must account for representation level (preserved/generalized/pseudonymized/removed), not only binary presence.

### Utility

- task success rate;
- objective accuracy/error metrics where applicable;
- verifiable properties/rubrics for outputs that cannot be reduced to a single scalar automatically.

### Reconstruction

- reconstruction success rate;
- correct pseudonym→original association;
- unresolved references;
- collisions;
- unauthorized reconstruction attempts/outcomes.

### Performance/cost

- treatment latency;
- provider latency;
- total pipeline latency;
- CPU/memory;
- disclosure-controlled transmitted volume;
- total provider-request volume when useful;
- provider tokens;
- estimated API cost.

## Measurement boundaries

### B0 timing

If detector/scoring is run around B0 for comparable exposure measurement, it must be measured outside B0 treatment latency. Shared evaluation overhead must not be silently attributed to Direct.

### Transmission/cost

Report disclosure-controlled payload contribution separately from task/prompt scaffolding. Total provider request volume may also be reported so absolute provider cost is not understated.

### Pilot calibration

No numeric utility-loss or overhead threshold is selected in advance at this stage.

The controlled pilot is used to observe realistic scale and then freeze:

- interpretation/acceptance thresholds;
- measurement procedure;
- any statistical choices that depend on the final design.

Those choices must be fixed **before** the main experiment results are analyzed and must not be tuned post hoc.

## Non-scientific integration surfaces

The following are product/integration surfaces, not experimental treatments:

- CLI;
- HTTP API;
- MCP server;
- simplified Next.js audit/experiment UI.

They must call/consume the same core contracts and cannot define policy logic, treatment semantics or scientific metrics independently. The UI may begin from versioned synthetic fixtures and later consume the HTTP API; no research-core task depends on the UI.

## Current implementation status

Milestone 1 is complete: B0/B1/B2, shared provider boundary, vault/reconstruction, real pseudonym-scope lifecycles, safe audit and end-to-end shared pipeline are on `master`.

The immediate gate is T09/Issue #4 Phase A. Once the HR corpus and ground truth are versioned/frozen, T07/B3 can start. T01 line/advisor selection runs independently as an academic track.
