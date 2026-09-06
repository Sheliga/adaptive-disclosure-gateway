# ADR 0001 — Milestone 1 architecture

Status: accepted for the first implementation cycle.

## Context

The research prototype needs a small, auditable core that can later compare B0–B4 without coupling scientific behavior to a specific LLM provider or orchestration framework.

## Decisions

1. Organizational policy is authoritative and precedes task-aware decisions.
2. Policy/authorization resolution is fail closed. Missing, invalid or ambiguous resolution produces `BLOCK_REQUEST`.
3. User prompts, ingested documents and model responses are untrusted data. They cannot change policy, roles, permissions, pseudonym scope or vault state.
4. Disclosure actions are `PRESERVE`, `PSEUDONYMIZE`, `GENERALIZE`, `REMOVE`, `BLOCK_REQUEST` and `TASK_DEPENDENT`.
5. `TASK_DEPENDENT` must expose an explicit policy-defined set of allowed actions; task relevance can only choose within that set.
6. Pseudonym scopes are `request`, `document`, `session` and `organization`. Default is `session`. Role defines a maximum scope; explicit user policy may set a ceiling; task/purpose may narrow but never expand it.
7. The first vertical slice is simplified HR with direct text input.
8. Development is TDD-first. B0–B2 with a deterministic FakeProvider define the first functional milestone.
9. Docling enters after the first milestone behind an ingestion interface.
10. The audit model exists from the first milestone, but its UI is postponed until B0–B2 work end-to-end.
11. OpenTelemetry is present from the first cycle. Trace attributes contain metadata only; experiment results remain backend-independent.
12. The core is deterministic Python with internal interfaces and must remain independent of LangChain, LangGraph, CrewAI, n8n or a specific provider SDK.

## Initial HR policy

| Category | Action |
| --- | --- |
| `employee_name` | `PSEUDONYMIZE` |
| `cpf` | `REMOVE` |
| `medical_data` | `BLOCK_REQUEST` |
| `salary` | `TASK_DEPENDENT` |
| `department` | `PRESERVE` |

For `salary`, the default permitted space is `REMOVE`/`GENERALIZE`; `PRESERVE` is additionally available for explicitly authorized purposes such as `salary_analysis` and `compensation_review`.

## Consequences

- Security does not depend on an LLM recognizing prompt injection correctly.
- New frameworks/providers are adapters rather than core dependencies.
- Policies become versioned experimental inputs and can be tested independently.
- Audit/reconstruction work can be added without changing the policy contract.
- Some future domain policies may block until their `TASK_DEPENDENT` action spaces are explicitly specified; this is intentional fail-closed behavior.
