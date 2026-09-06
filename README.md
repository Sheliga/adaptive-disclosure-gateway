# Adaptive Disclosure Gateway

Research prototype for policy-constrained disclosure of organizational data to external LLMs.

The project investigates a local trust boundary that applies explicit organizational policies before data leaves the organization. Within the actions allowed by policy, task relevance can be used to minimize disclosure. Pseudonym mappings remain local and can be used to reconstruct authorized responses after external inference.

## Research status

This repository supports a **candidate master's research proposal** for UTFPR PPGCA 2027. The proposal is still under evaluation and this codebase must not be interpreted as a finished dissertation implementation or as evidence that the proposed method outperforms existing approaches.

## Current implementation status

The architecture foundation for Milestone 1 is implemented and merged. The current work item is the deterministic detector + B1 static sanitizer; B2/vault/reconstruction/FakeProvider remain pending before the first end-to-end milestone is complete.

See [`docs/implementation-status.md`](docs/implementation-status.md) for the live engineering status. Architectural decisions are recorded separately in [`docs/adr/0001-milestone-1-architecture.md`](docs/adr/0001-milestone-1-architecture.md).

## Security model

Organizational policy is authoritative. User prompts, ingested documents and model responses are treated as untrusted data and cannot change policies, roles, permissions, pseudonym scope or vault state.

Policy and authorization resolution are **fail closed**: missing, invalid or ambiguous rules result in `BLOCK_REQUEST` rather than silently permitting disclosure. Task-awareness may only choose among actions already allowed by policy.

Disclosure actions are:

- `PRESERVE` — send the original value;
- `PSEUDONYMIZE` — send a locally reversible pseudonym;
- `GENERALIZE` — send a less precise representation;
- `REMOVE` — omit the value while allowing the request to continue;
- `BLOCK_REQUEST` — block the entire external request;
- `TASK_DEPENDENT` — choose the least-disclosing useful action inside an explicit policy-defined action space.

## Core flow

```text
PDF / DOCX / XLSX / image / direct text
        ↓
optional document ingestion (Docling)
        ↓
normalized document structure
        ↓
input + governance context + task
        ↓
local detection/classification
        ↓
organizational policy gates
        ↓
task-aware minimization within allowed actions
        ↓
preserve | pseudonymize | generalize | remove | block_request
        ↓
authorized external payload
        ↓
external LLM
        ↓
local authorized reconstruction
```

## Pseudonym scope authorization

Pseudonym persistence can use `request`, `document`, `session` or `organization` scope. The default is `session`.

Authorization is hierarchical: role defines the maximum scope, an explicit per-user configuration may further define a ceiling, and task/purpose may only narrow the effective scope. A task can never expand the authorization ceiling.

## Document ingestion

Docling is planned as an **infrastructure component** for parsing and normalizing document-oriented inputs such as PDF, DOCX, spreadsheets and images while preserving useful structure such as sections, tables and layout-derived relationships.

It is not part of the claimed research contribution. Its role is to avoid coupling the disclosure-control research to custom PDF/Office parsing and to enable realistic document-oriented validation, especially for contracts.

The ingestion layer should expose an internal normalized representation so the rest of the pipeline does not depend directly on Docling APIs. Direct text input must remain supported for controlled experiments.

## Initial validation domains

- Human Resources — personal and sensitive employee information.
- Accounting / Finance — financial, banking and commercial confidentiality.
- Contracts — identities, commercial terms, obligations, deadlines and semantic relationships between parties.

The first implementation milestone uses a simplified HR slice. Contracts follow after the core flow is stable because they provide the richer semantic validation scenario.

## Milestone 1

The first functional milestone is **B0 + B1 + B2 end-to-end over direct HR text using a deterministic FakeProvider**.

Frozen RH categories:

- `employee_name` → `PSEUDONYMIZE`;
- `cpf` → `REMOVE`;
- `medical_data` → `BLOCK_REQUEST`;
- `salary` → `TASK_DEPENDENT` with policy-defined allowed actions;
- `department` → `PRESERVE`.

Development follows TDD. The audit trail data model is created from the beginning, while the comparison UI is intentionally postponed until B0–B2 are functional.

## Experimental treatments

- **B0** — direct/full external disclosure.
- **B1** — static sanitization.
- **B2** — static reversible pseudonymization.
- **B3** — task-aware minimization without strong contextual organizational policy constraints.
- **B4** — proposed approach: contextual policy constraints + task-aware minimization + reversible pseudonymization + local reconstruction.

All treatments must use compatible request/result contracts so they can run against the same cases.

See [`docs/experimental-design.md`](docs/experimental-design.md) for the isolated variable per comparison, what must be held constant, and the mapping from these treatments to the planned metrics below.

## Observability and audit

OpenTelemetry is part of the implementation from the first milestone. Development uses OTLP with a local Jaeger backend.

Traces must contain metadata only, never raw documents, reconstructed responses, vault values or other sensitive values. Scientific results remain independent of the observability backend and will be recorded in an experiment-oriented format such as JSONL.

The planned audit model keeps the stages necessary to compare:

```text
raw input
→ detected spans
→ policy decisions
→ transformed payload
→ payload delivered to provider
→ provider response
→ locally reconstructed response
```

Full raw/reconstructed values may only be persisted explicitly for controlled synthetic experiments; normal operation should persist metadata, categories, decisions, identifiers/hashes and metrics.

## Planned metrics

- policy violation rate;
- unnecessary disclosure;
- sensitive information exposure;
- task utility / task success;
- reconstruction accuracy;
- latency;
- CPU and memory usage;
- transmitted tokens/data volume;
- estimated external API cost.

## Repository layout

```text
src/adaptive_disclosure_gateway/
├── ingestion/
├── governance/
├── detection/
├── policies/
├── task_analysis/
├── transformations/
├── pseudonymization/
├── vault/
├── providers/
├── reconstruction/
├── audit/
└── evaluation/
configs/policies/
datasets/synthetic/
experiments/
tests/
docs/
```

## Framework independence

The core is initially deterministic Python with small internal interfaces. It must not depend rigidly on LangChain, LangGraph, CrewAI, n8n or another orchestration framework. Adapters can be added later without changing the policy and disclosure contracts.

## Scope and safety

The primary validation uses controlled synthetic/public-derived data. Real employer or confidential organizational data is not required for the main hypothesis and must not be committed to this repository.

The system is a research prototype. It does not claim universal anonymization, legal compliance, or complete prevention of information leakage.
