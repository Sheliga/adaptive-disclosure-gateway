# Adaptive Disclosure Gateway

Research prototype for policy-constrained disclosure of organizational data to external LLMs.

The project investigates a local trust boundary that applies explicit organizational policies before data leaves the organization. Within the actions allowed by policy, task relevance can be used to minimize disclosure. Pseudonym mappings remain local and can be used to reconstruct authorized responses after external inference.

## Research status

This repository supports a **candidate master's research proposal** for UTFPR PPGCA 2027. The proposal is still under evaluation and this codebase must not be interpreted as a finished dissertation implementation or as evidence that the proposed method outperforms existing approaches.

## Current implementation status

**Milestone 1 is complete on `master`.** The first functional vertical slice now includes the architecture foundation, deterministic detector, **B0 — Direct** (`DirectDiscloser`), **B1 — Static Sanitization** (`StaticSanitizer`), **B2 — Reversible Pseudonymization** (`ReversiblePseudonymizer`), real REQUEST/DOCUMENT/SESSION pseudonym-scope lifecycles, opaque offline-guessing-resistant pseudonyms, the shared provider boundary (`providers.invoke_provider` + deterministic `FakeProvider`), the shared B0/B1/B2 execution path (`pipeline.run_disclosure_case`) and the structural metadata-only audit model (`audit.AuditRecord`).

PR #27 completed Milestone 1 and was merged into `master` at `28fe292cf1e7cb1dfccb999c3f04aed1016f5d8e`; the post-merge CI run passed. The project is now moving into **B3 — Task-aware**, **B4 — Policy-governed**, controlled corpus/ground-truth construction and the experiment runner/metrics.

See [`docs/implementation-status.md`](docs/implementation-status.md) for the live engineering status, remaining work and recommended execution order. Architectural decisions are recorded separately in [`docs/adr/0001-milestone-1-architecture.md`](docs/adr/0001-milestone-1-architecture.md).

## Runtime

The canonical development and CI runtime for this prototype is **CPython 3.13.13**. Project metadata intentionally targets the Python 3.13 line (`>=3.13,<3.14`) so local development, CI and experiment reproduction do not silently drift across Python feature versions.

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

The project's no-leak boundary is broader than the external payload. Sensitive values must also be excluded from provider-facing task/prompt fields where disclosure control applies, exception messages/chains, logs, telemetry, audit records and guessable derived identifiers/hashes.

## Core flow

```text
PDF / DOCX / XLSX / image / direct text
        ↓
optional document ingestion (Docling, planned)
        ↓
normalized document structure / direct controlled text
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
provider boundary
        ↓
external LLM / deterministic FakeProvider
        ↓
local authorized reconstruction
        ↓
structural audit + experiment metrics
```

B0 — Direct is the intentionally unsafe control treatment. Its transformation sends the input unchanged and does not consume detection/policy/task-awareness. The shared experiment pipeline may still execute scoring/detection around B0 for comparison purposes; that external overhead must not be attributed to B0's own treatment latency.

## Pseudonym scope authorization

Pseudonym persistence supports `request`, `document`, `session` or `organization` scope. The default is `session`.

Authorization is hierarchical: role defines the maximum scope, an explicit per-user configuration may further define a ceiling, and task/purpose may only narrow the effective scope. A task can never expand the authorization ceiling.

Concrete lifecycle semantics are implemented:

- REQUEST uses `request_id`;
- DOCUMENT uses `document_id`;
- SESSION uses `session_id`;
- ORGANIZATION uses the organization/domain partition defined by the architecture.

If the resolved scope requires an identifier that is absent, B2 fails closed rather than falling back to requester identity or role. Authorized reconstruction recomputes the same partition key from the corresponding context.

## Document ingestion

Docling is planned as an **infrastructure component** for parsing and normalizing document-oriented inputs such as PDF, DOCX, spreadsheets and images while preserving useful structure such as sections, tables and layout-derived relationships.

It is not part of the claimed research contribution. Its role is to avoid coupling the disclosure-control research to custom PDF/Office parsing and to enable realistic document-oriented validation, especially for contracts.

The ingestion layer should expose an internal normalized representation so the rest of the pipeline does not depend directly on Docling APIs. Direct text input remains the canonical path for controlled experiments.

## Initial validation domains

- Human Resources — personal and sensitive employee information.
- Accounting / Finance — financial, banking and commercial confidentiality.
- Contracts — identities, commercial terms, obligations, deadlines and semantic relationships between parties.

Milestone 1 uses a simplified HR slice. Finance and Contracts extend validation after the core disclosure treatments are stable; Contracts are especially useful for testing preservation of semantic relationships.

## Milestone 1 — complete

The first functional milestone is **B0 — Direct + B1 — Static Sanitization + B2 — Reversible Pseudonymization end-to-end over direct HR text using a deterministic FakeProvider**.

Frozen HR categories:

- `employee_name` → `PSEUDONYMIZE`;
- `cpf` → `REMOVE`;
- `medical_data` → `BLOCK_REQUEST`;
- `salary` → `TASK_DEPENDENT` with policy-defined allowed actions;
- `department` → `PRESERVE`.

Milestone 1 now demonstrates through the shared pipeline that malformed spans fail closed, `REMOVE` originals do not reach the provider, `BLOCK_REQUEST` prevents the provider call, B2 pseudonyms respect real lifecycle scopes, authorized responses reconstruct locally, provider failures remain auditable without raw error text, and the default audit trail contains metadata/keyed correlation values rather than sensitive content or public guessing-oracle hashes.

Development follows TDD. The merged Milestone 1 suite reached **170 tests**, and CI is green on the merge commit.

## Experimental treatments

- **B0 — Direct** — direct/full external disclosure.
- **B1 — Static Sanitization** — static sanitization.
- **B2 — Reversible Pseudonymization** — static reversible pseudonymization.
- **B3 — Task-aware** — task-aware minimization without strong contextual organizational policy constraints, retaining the same reversible pseudonymization/vault/reconstruction mechanism used by B2 so the B2→B3 comparison isolates task-awareness rather than reversibility.
- **B4 — Policy-governed** — proposed approach: contextual policy constraints + task-aware minimization + reversible pseudonymization + local reconstruction.

All treatments use compatible request/result contracts so they can run against the same controlled cases. B3 and B4 are the next major implementation steps.

See [`docs/experimental-design.md`](docs/experimental-design.md) for the isolated variable per comparison, what must be held constant, and the mapping from these treatments to the planned metrics below.

## Provider boundary

Every treatment that reaches an external provider goes through the shared provider interface. `ProviderRequest` intentionally exposes only the provider-facing payload and task/instruction; it never exposes policy definitions, vault state, detected spans or the full `GovernanceContext`.

For B1/B2, a sensitive value detected only in `request.task` fails the request closed before the provider call. B0 remains deliberately exempt because it is the unsafe control baseline.

`provider_class` is checked before provider invocation. Errors and timeouts do not retry or degrade to B0, and the audit distinguishes pre-flight rejection from a provider call that was actually submitted.

The current `FakeProvider` is deterministic and offline for controlled experiments. Future real network adapters must add native transport/client timeout or cancellation in addition to the current caller-side deadline mechanism.

## Observability and audit

OpenTelemetry is part of the implementation from the first milestone. Development uses OTLP with a local Jaeger backend.

Traces contain metadata only, never raw documents, reconstructed responses, vault values or other sensitive values. Scientific results remain independent of the observability backend and will be recorded in an experiment-oriented format such as JSONL.

The implemented structural audit model covers:

```text
raw input
→ detected spans
→ policy decisions
→ transformed payload
→ payload delivered to provider
→ provider response
→ locally reconstructed response
```

By default, `AuditRecord` stores metadata, decisions, counts, provider reproducibility information and locally keyed correlation hashes — not raw content. Public unkeyed SHA-256 digests of potentially sensitive payload/response content are not used as the safe default because they can become offline guessing oracles for low-entropy values.

Full raw/reconstructed values may only be captured via the explicit non-default controlled-experiment opt-in. Normal operation remains metadata-only.

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

For performance measurements, shared detector/scoring work executed around B0 for comparability must be measured separately from B0's treatment cost. Prompt/task scaffolding held constant across treatments should also be separated from disclosure-controlled payload volume when estimating treatment-specific transmission effects.

## Next implementation phase

The next engineering/research sequence is:

1. **B3 — Task-aware** (T07 / Issue #6);
2. **B4 — Policy-governed** (T08 / Issue #7);
3. finalize the controlled corpus and ground truth (T09 / Issue #4; this can progress in parallel);
4. implement the experiment runner and authoritative metrics (T10 / Issue #8);
5. add Docling ingestion when document-oriented validation becomes useful (T12 / Issue #9).

The PPGCA line/advisor reevaluation (T01) is independent of this engineering sequence.

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

The core is deterministic Python with small internal interfaces. It must not depend rigidly on LangChain, LangGraph, CrewAI, n8n or another orchestration framework. Adapters can be added later without changing the policy and disclosure contracts.

## Scope and safety

The primary validation uses controlled synthetic/public-derived data. Real employer or confidential organizational data is not required for the main hypothesis and must not be committed to this repository.

The system is a research prototype. It does not claim universal anonymization, legal compliance, or complete prevention of information leakage.
