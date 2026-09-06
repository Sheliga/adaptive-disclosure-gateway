# Adaptive Disclosure Gateway

Research prototype for policy-constrained disclosure of organizational data to external LLMs.

The project investigates a local trust boundary that applies explicit organizational policies before data leaves the organization. Within the actions allowed by policy, task relevance can be used to minimize disclosure. Pseudonym mappings remain local and can be used to reconstruct authorized responses after external inference.

## Research status

This repository supports a **candidate master's research proposal** for UTFPR PPGCA 2027. The proposal is still under evaluation and this codebase must not be interpreted as a finished dissertation implementation or as evidence that the proposed method outperforms existing approaches.

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
preserve | pseudonymize | generalize | remove | deny
        ↓
authorized external payload
        ↓
external LLM
        ↓
local authorized reconstruction
```

## Document ingestion

Docling is planned as an **infrastructure component** for parsing and normalizing document-oriented inputs such as PDF, DOCX, spreadsheets and images while preserving useful structure such as sections, tables and layout-derived relationships.

It is not part of the claimed research contribution. Its role is to avoid coupling the disclosure-control research to custom PDF/Office parsing and to enable realistic document-oriented validation, especially for contracts.

The ingestion layer should expose an internal normalized representation so the rest of the pipeline does not depend directly on Docling APIs. Direct text input must remain supported for controlled experiments.

Potential document-oriented use cases include:

- querying contract collections while protecting party identities and confidential terms;
- analyzing HR documents while suppressing or pseudonymizing employee data;
- processing accounting/financial reports while controlling disclosure of customers, suppliers, bank data, margins and negotiated values.

## Initial validation domains

- Human Resources — personal and sensitive employee information.
- Accounting / Finance — financial, banking and commercial confidentiality.
- Contracts — identities, commercial terms, obligations, deadlines and semantic relationships between parties.

Contracts are especially relevant because disclosure control must preserve semantic roles and obligations after transformation.

## Experimental treatments

- **B0** — direct/full external disclosure.
- **B1** — static sanitization.
- **B2** — static reversible pseudonymization.
- **B3** — task-aware minimization without strong contextual organizational policy constraints.
- **B4** — proposed approach: contextual policy constraints + task-aware minimization + reversible pseudonymization + local reconstruction.

Document ingestion must be held constant when comparing B0–B4 so that parser behavior is not confused with the effect of the disclosure strategy.

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

## Scope and safety

The primary validation uses controlled synthetic/public-derived data. Real employer or confidential organizational data is not required for the main hypothesis and must not be committed to this repository.

The system is a research prototype. It does not claim universal anonymization, legal compliance, or complete prevention of information leakage.
