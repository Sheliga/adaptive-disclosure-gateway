# HR pilot corpus schema (v1)

Frozen for T09 / GitHub Issue #4, Phase A. This document describes the case
file schema in prose. The schema is also enforced in code by
`src/adaptive_disclosure_gateway/corpus/` (`CorpusCaseInput`, `CaseOracle`,
`ExpectedSpan`, `ReconstructionExpectation`, `TaskNecessity`, `TaskFamily`)
and by `tests/test_corpus_schema.py`, `tests/test_corpus_span_consistency.py`,
`tests/test_corpus_coverage.py`, `tests/test_corpus_task_necessity_coherence.py`
and `tests/test_corpus_answer_grounded_in_input.py`. If this document and
the code ever disagree, the code (and its tests) win; update this document
to match.

## File layout

One YAML file per case, at `corpus/hr/v1/cases/<sample_id>.yaml`. The
file's base name **must** equal `input.sample_id` -- this is validated and
enforced by the loader (`CorpusLoadError` on a mismatch), not just a
review/diffing convention. The loader also enforces that `input.sample_id`
must equal `oracle.sample_id` within a file, and that no two files in the
same corpus directory may declare the same `sample_id`
(`tests/test_corpus_schema.py`).

Each file has exactly two top-level keys: `input` and `oracle`. Both are
required. No other top-level key is permitted.

## The input/oracle separation

This is the central methodological invariant the schema exists to enforce
structurally, not by convention (CLAUDE.md's no-leak invariant and
docs/experimental-design.md's "ground truth is an evaluation oracle only"):

- **`input`** is everything a disclosure treatment (B0-B4) may legitimately
  see. It becomes a `DisclosureRequest` via `CorpusCaseInput.to_disclosure_request()`
  -- the *only* method anywhere in `src/adaptive_disclosure_gateway/corpus/`
  that constructs a `DisclosureRequest`.
- **`oracle`** is used only for scoring, by whatever later consumes this
  corpus (T10's runner). `CaseOracle` has no method that builds a
  `DisclosureRequest` and no path into the pipeline. No module under
  `transformations/`, `detection/`, `policies.py` or `pipeline.py` may
  import anything from `adaptive_disclosure_gateway.corpus` --
  `tests/test_corpus_oracle_isolation.py` pins both of these by AST
  inspection.

## `input` fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `sample_id` | string | yes | Non-empty. Must equal the file's base name and `oracle.sample_id`. |
| `task_family` | one of the four task families below | yes | Corpus-coverage metadata; never part of `GovernanceContext`. |
| `text` | string | yes | The controlled input text a treatment sanitizes. Every offset in `oracle.expected_spans` is relative to this exact string. |
| `task` | string | yes | The task/instruction text, held constant across treatments per docs/experimental-design.md. |
| `domain` | string | yes | `GovernanceContext.domain`. Every case in this corpus uses `hr`. |
| `purpose` | string | yes | `GovernanceContext.purpose`. |
| `requester_role` | string or absent | no | `GovernanceContext.requester_role`. |
| `requester_id` | string or absent | no | `GovernanceContext.requester_id`. Not exercised by v1's cases. |
| `provider_class` | string | no (default `external_llm`) | `GovernanceContext.provider_class`. |
| `policy_version` | string | yes | Must name a policy version that actually loads from `configs/policies/` (`hr-v1` for this corpus). |
| `requested_pseudonym_scope` | one of `request`, `document`, `session`, `organization` | no (default `session`) | `GovernanceContext.requested_pseudonym_scope`. |
| `request_id` / `document_id` / `session_id` | string or absent | no | Supply whichever identifier the case's resolved pseudonym scope needs (see `reversible_pseudonymization._scope_key`). |

Any key other than the ones listed above fails schema validation
(`extra="forbid"`).

## `oracle` fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `sample_id` | string | yes | Must equal `input.sample_id`. |
| `expected_spans` | non-empty list of expected-span objects (below) | yes | Every sensitive information unit annotated in `input.text`. |
| `expected_block_request` | boolean | yes | Whether the case must produce `DisclosureResult.status == "blocked"`. |
| `expected_answer` | string or absent | conditionally | **Required** when `expected_block_request` is `false` (the objectively verifiable property/answer a correct treatment's output should satisfy). **Must be absent** when `expected_block_request` is `true` -- a blocked request never produces an answer to score. |
| `answer_depends_on_categories` | list of the five frozen categories, or absent | conditionally | **Required** (non-null) when `expected_block_request` is `false`: every category `expected_answer` actually depends on. **Must be absent** when `expected_block_request` is `true`. The loader validates the values are known categories. See "Task-necessity/answer coherence" below. |
| `reconstruction` | list of reconstruction-expectation objects (below) | no (default empty) | **Must be empty** when `expected_block_request` is `true`. |

### Expected-span object

| Field | Type | Notes |
| --- | --- | --- |
| `category` | one of `employee_name`, `cpf`, `salary`, `department`, `medical_data` | The five categories frozen in the detector today. No other category is permitted in v1. |
| `value` | non-empty string | The exact substring of `input.text` this span names. |
| `start` / `end` | integers, `end > start`, `start >= 0` | Offsets into `input.text`. `input.text[start:end]` must equal `value` exactly -- checked by reusing `transformations/span_validation.py`, not reimplemented (`tests/test_corpus_span_consistency.py`). |
| `task_necessity` | `required` or `not_required` | The **primary, binary** task-necessity oracle (docs/experimental-design.md). No third value is permitted here. |
| `expected_actions` | non-empty list of `DisclosureAction` values (`preserve`, `pseudonymize`, `generalize`, `remove`, `block_request`) | The acceptable action set for this information unit -- a single-element list when only one action is acceptable. |
| `helpful` | boolean (default `false`) | The **auxiliary-only** helpfulness annotation. It is a separate field precisely so it can never be mixed into `task_necessity`'s primary binary oracle -- docs/experimental-design.md permits `HELPFUL` only as an auxiliary annotation until an objective scoring criterion is frozen. |

A case may list the same `category` more than once (e.g. two employee
records in one aggregation case): each occurrence is its own expected span
with its own offsets.

### Reconstruction-expectation object

| Field | Type | Notes |
| --- | --- | --- |
| `category` | one of the five frozen categories | Which category's pseudonym is expected to be reconstructable. |
| `expected_reconstructable` | boolean | Whether, under the case's governance context, a pseudonym produced for this category is expected to reconstruct back to its original value. |

## Task-necessity labels

Primary oracle, binary only:

- `required` -- the information unit is necessary for the task to succeed
  at an acceptable level of utility (in some representation: full value,
  generalized value, or a reconstructable pseudonym the task can operate on
  without needing the literal original).
- `not_required` -- disclosing the information unit (in any readable form)
  is not necessary for the task. Any span labeled `not_required` that a
  treatment nonetheless transmits counts as unnecessary disclosure under
  docs/experimental-design.md's primary metric.

`helpful` (see above) is never a third value of `task_necessity` and must
never be read as part of it.

## Task-necessity/answer coherence

A span may only be annotated `task_necessity: required` if the case's own
`expected_answer` actually depends on that category -- otherwise the
`required` label is unfalsifiable annotation drift, not a real oracle. This
is enforced two ways:

- schema level: `oracle.answer_depends_on_categories` lists every category
  `expected_answer` depends on, and is required exactly when
  `expected_answer` is (never present on a blocked case);
- corpus level: `tests/test_corpus_task_necessity_coherence.py` checks, for
  every non-blocked case, that the set of categories with at least one
  `required` span equals `answer_depends_on_categories` exactly. A
  mismatch fails the suite.

`oracle.expected_answer` itself must also be checkable purely from
`input.text` -- never from a compensation band, department policy or wage
floor known only to a scoring model or to
`transformations/generalization.py`'s bucket configuration, since neither
is input common to every treatment B0-B4. When a task requires comparing
against such a reference, the case's `input.text` states that reference
explicitly (as an appended line that the detector does not match against
any of the five frozen categories); `tests/test_corpus_answer_grounded_in_input.py`
pins that every monetary figure an `expected_answer` cites is a verbatim
substring of `input.text`.

## Task families

Every case's `task_family` is one of:

1. `authorized_salary_analysis` -- an authorized salary analysis or
   compensation review where the salary figure is `required`.
2. `team_summary_without_salary` -- a team/role summary or directory
   description where salary is `not_required`.
3. `department_aggregation_without_identity` -- an aggregate,
   department-level analysis where individual identity (`employee_name`,
   `cpf`) is `not_required`.
4. `medical_or_prohibited_block` -- a request whose input contains
   `medical_data`, which hr-v1 blocks unconditionally; `expected_block_request`
   is always `true` in this family.

The corpus must include at least one case in each family
(`tests/test_corpus_coverage.py`).

## Freeze rule

See `README.md` in this directory: once this corpus (schema + cases +
annotations) merges to `master`, v1 is immutable. Any change to the schema,
an existing case's text/offsets/labels, or the set of cases requires a new
`corpus/hr/v1+1/` (e.g. `v2`) version, never an in-place edit of `v1`.
