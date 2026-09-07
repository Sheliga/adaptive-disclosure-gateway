# HR pilot corpus — v1

T09 / GitHub Issue #4, Phase A: the controlled HR minicorpus and ground
truth that gate B3 -- Task-aware (T07 / Issue #6) implementation.

## What this is

13 synthetic HR cases (`cases/*.yaml`), each pairing:

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

1. authorized salary analysis (`authorized_salary_analysis`) -- 3 cases;
2. team summary/description where salary is not required
   (`team_summary_without_salary`) -- 4 cases;
3. aggregation by department without individual identity
   (`department_aggregation_without_identity`) -- 3 cases;
4. a request containing medical/prohibited information that must block
   (`medical_or_prohibited_block`) -- 3 cases.

`hr_team_summary_004` is the fourth `team_summary_without_salary` case and
the only one in the corpus where the employee's identity is genuinely
required by the task (an announcement addressed by name), rather than
suppressed by default. Without it, `employee_name` was `NOT_REQUIRED` in
every one of its occurrences across the corpus, which a constant
identity-suppression strategy would satisfy without any real task
analysis; `tests/test_corpus_necessity_discrimination.py` pins that this
does not recur for any other non-exempt category.

## Synthetic data notice

Every name, CPF, salary figure, department and medical note in this corpus
is invented for testing. No real employer, employee or organizational data
is used anywhere in this corpus. CPF values match the detector's
punctuated format (`###.###.###-##`) but are not validated check digits --
consistent with `detection/rules.py`, which does not validate CPF/CNPJ
check digits either.

## Limitations and threats to validity

### Detection is near-perfect by construction

Every case in v1 presents sensitive values in the same labeled-line format
(`Employee:`, `CPF:`, `Salary:`, `Department:`, `Medical notes:`), and
`detection/rules.py` keys on exactly those labels. Measured against this
corpus, the current detector finds 71 of 71 annotated spans with no false
positives.

That figure is a property of the corpus format, not evidence about detector
quality. It has two consequences, and they pull in opposite directions:

- **It does not confound the treatment comparisons.** Detection is held
  constant across B0-B4, so the adjacent comparisons B0->B1, B1->B2,
  B2->B3 and B3->B4 still isolate their intended variable.
- **It does inflate absolute figures.** Any absolute claim about exposure
  reduction, detector recall or residual sensitive content measured on this
  corpus is optimistic. Such figures must be reported as an upper bound
  obtained under a structured-input assumption, never as a general-case
  detection result.

v1 deliberately contains no free-prose sensitive values: no unlabeled name,
no CPF embedded mid-sentence, no salary stated in natural language.
Robustness to unstructured input is out of scope for the pilot gate and is
deferred to a later corpus version, alongside real document ingestion
(T12 / Issue #9). Under the freeze rule below, that work creates
`corpus/hr/v2/` rather than editing v1 in place.

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
