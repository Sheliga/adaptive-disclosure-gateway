# Adaptive Disclosure Gateway

Research prototype for policy-constrained disclosure of organizational data to external LLMs.

The project investigates a local trust boundary that applies explicit organizational policies before data leaves the organization. Within the actions allowed by policy, task relevance can be used to minimize disclosure. Pseudonym mappings remain local and can be used to reconstruct authorized responses after external inference.

## Research status

This repository supports a **candidate master's research proposal** for UTFPR PPGCA 2027. The proposal is still under evaluation and this codebase must not be interpreted as a finished dissertation implementation or as evidence that the proposed method outperforms existing approaches.

## Core flow

```text
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
configs/policies/
datasets/synthetic/
experiments/
tests/
docs/
```

## Scope and safety

The primary validation uses controlled synthetic/public-derived data. Real employer or confidential organizational data is not required for the main hypothesis and must not be committed to this repository.

The system is a research prototype. It does not claim universal anonymization, legal compliance, or complete prevention of information leakage.
