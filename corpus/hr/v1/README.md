# HR pilot corpus — v1

T09 / GitHub Issue #4, Phase A: the controlled HR minicorpus and ground
truth that gate B3 -- Task-aware (T07 / Issue #6) implementation.

## What this is

12 synthetic HR cases (`cases/*.yaml`), each pairing:

- an `input` block: controlled text, task/instruction and
  `GovernanceContext` fields a disclosure treatment may legitimately see;
- an `oracle` block: expected sensitive spans/categories, task-necessity
  labels, acceptable action sets, expected `BLOCK_REQUEST` behavior,
  expected answer/verifiable property, and pseudonym-reconstruction
  expectations -- used only for scoring, never given to a treatment as
  input.

The schema is described in prose in `SCHEMA.md` and enforced in code by
`src/adaptive_disclosure_gateway/corpus/`.

## Domain covered

All cases are in the `hr` domain, against the `hr-v1` policy
(`configs/policies/hr-v1.yaml`), and use only the five HR categories
already frozen in the detector: `employee_name`, `cpf`, `salary`,
`department`, `medical_data`. The corpus covers the four task families
required by docs/experimental-design.md and the linked GitHub Issue:

1. authorized salary analysis (`authorized_salary_analysis`);
2. team summary/description where salary is not required
   (`team_summary_without_salary`);
3. aggregation by department without individual identity
   (`department_aggregation_without_identity`);
4. a request containing medical/prohibited information that must block
   (`medical_or_prohibited_block`).

## Synthetic data notice

Every name, CPF, salary figure, department and medical note in this corpus
is invented for testing. No real employer, employee or organizational data
is used anywhere in this corpus. CPF values match the detector's
punctuated format (`###.###.###-##`) but are not validated check digits --
consistent with `detection/rules.py`, which does not validate CPF/CNPJ
check digits either.

## Freeze rule

**v1 is immutable once merged to `master`.** This includes the schema
(`SCHEMA.md`), every case file under `cases/`, and every annotation inside
them. Any future change -- adding a case, correcting an annotation, adding
a category, changing an offset -- creates a new version directory
(`corpus/hr/v2/`, and so on) rather than editing `v1` in place. This keeps
any pilot run or reported result that cites "HR corpus v1" reproducible
against an unchanging artifact.

If a defect is found in a v1 annotation after it has been used for scoring,
document it (do not silently patch v1) and address it in the next version.
