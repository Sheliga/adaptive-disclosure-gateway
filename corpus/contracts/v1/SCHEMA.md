# Contracts validation corpus schema (v1)

Frozen for T24 / GitHub Issue #37. This document describes the case-file
schema in prose. The schema is also enforced in code by
`src/adaptive_disclosure_gateway/corpus/` (`CorpusCaseInput`, `CaseOracle`,
`ExpectedSpan`, `ReconstructionExpectation`, `ObligationRelation`,
`TaskNecessity`, `ContractsTaskFamily`) and by
`tests/test_corpus_contracts_schema.py`,
`tests/test_corpus_contracts_coverage.py`,
`tests/test_corpus_obligation_relation.py` and
`tests/test_experiments_contracts_v1.py`. If this document and the code ever
disagree, the code (and its tests) win; update this document to match.

It mirrors `corpus/hr/v1/SCHEMA.md` deliberately. Only the differences are
spelled out at length below; everything the two corpora share is stated once
and cross-referenced, so the two documents cannot drift into describing two
different schemas.

## Relationship to the HR v1 schema

Contracts v1 uses the **same case-file schema** as HR v1, extended in exactly
two ways (`CORPUS_SCHEMA_VERSION = "corpus-case-schema-v2"`):

1. **Per-domain vocabulary registries.** The frozen category tuple and the
   task-family enum are now keyed by domain
   (`FROZEN_CATEGORIES_BY_DOMAIN`, `TASK_FAMILIES_BY_DOMAIN` in
   `corpus/models.py`). A case's `oracle.expected_spans[].category`,
   `oracle.reconstruction[].category`,
   `oracle.answer_depends_on_categories[]`,
   `oracle.obligation_relations[].depends_on_categories[]` and
   `input.task_family` are validated **against its own `input.domain`** at
   load time (`corpus/loader.py`), which is already where every cross-half
   consistency rule lives. An unregistered `domain` fails closed.
2. **`oracle.obligation_relations`** — the relation half of the Contracts
   oracle (see below). Optional, defaults to empty, so every
   `corpus/hr/v1` case file remains valid **byte-for-byte unchanged**.

Both changes are purely additive. No v1 field changed meaning, and the HR
corpus keeps its own `hr/v1` version string.

## File layout

One YAML file per case, at `corpus/contracts/v1/cases/<sample_id>.yaml`. The
file's base name **must** equal `input.sample_id`, `input.sample_id` must
equal `oracle.sample_id`, and no two files in a corpus directory may declare
the same `sample_id` — all enforced by the loader (`CorpusLoadError`), not by
review convention.

Each file has exactly two top-level keys: `input` and `oracle`. Both are
required. No other top-level key is permitted.

## The input/oracle separation

Identical to `corpus/hr/v1/SCHEMA.md`'s section of the same name, and it is
the central methodological invariant this schema exists to enforce
structurally:

- **`input`** is everything a disclosure treatment (B0–B4) may legitimately
  see. It becomes a `DisclosureRequest` via
  `CorpusCaseInput.to_disclosure_request()` — the *only* method anywhere in
  `src/adaptive_disclosure_gateway/corpus/` that constructs one.
- **`oracle`** is used only for scoring. `CaseOracle` has no method that
  builds a `DisclosureRequest` and no path into the pipeline. No module under
  `transformations/`, `detection/`, `task_analysis/`, `policies.py` or
  `pipeline.py` may import anything from `adaptive_disclosure_gateway.corpus`
  (`tests/test_corpus_oracle_isolation.py`, by AST inspection).

**The relation annotation is covered by the same rule, and then some.**
`oracle.obligation_relations` is ground truth about what a correct
transformation must preserve. If it ever reached the detector, the task
analyzer, a treatment, policy or the provider, the experiment would be
measuring a pipeline that had been told the answer.
`tests/test_corpus_obligation_relation.py` pins this structurally (no
production or execution-boundary module may reference `ObligationRelation` or
`obligation_relations`; `CorpusCaseInput` declares no field whose name
contains `obligation` or `relation`) **and** behaviorally (a marker planted in
a relation is run through the real runner for every treatment and must appear
nowhere in the serialized result, the payload or the audit record).

## `input` fields

Identical to `corpus/hr/v1/SCHEMA.md`'s table, with these Contracts values:

| Field | Contracts v1 value |
| --- | --- |
| `domain` | always `contracts` |
| `policy_version` | always `contracts-v1` |
| `task_family` | one of the six Contracts families below |
| `purpose` | varies — this is the one governance dimension `contracts-v1` reads |
| `requester_role` | recorded, but **not read** by `contracts-v1` |
| `provider_class` | recorded, but **not read** by `contracts-v1` |

`requester_role` and `provider_class` are stated on cases anyway, and one case
(`contracts_deadline_tracking_002`) deliberately varies `provider_class`, so
that their documented inertness under `contracts-v1`
(`docs/contracts-policy-matrix.md`'s governance table) is **observable rather
than assumed**. That is not evidence those dimensions are inert in general —
`hr-v2`/`hr-v3` are the policy versions that exercise them.

Any key other than those `CorpusCaseInput` declares fails schema validation
(`extra="forbid"`).

## `oracle` fields

Identical to `corpus/hr/v1/SCHEMA.md`'s table, plus:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `obligation_relations` | list of obligation-relation objects (below) | no (default empty) | **Must be empty** when `expected_block_request` is `true` — a blocked request produces no payload for a relation to survive in or be lost from. |

### Expected-span object

Same fields as HR v1. The permitted `category` values for this corpus are the
**eight Contracts categories frozen by Issue #56 / PR #59**:

`party_name`, `representative_name`, `cnpj`, `cpf`, `bank_account`,
`contract_value`, `penalty_amount`, `deadline`.

`cnpj` and `cpf` are the two HR-era categories Issue #56 reused unchanged
rather than duplicating under a `tax_id` synonym; the per-domain check treats
them as native to both domains. `obligation` and `confidential_clause` are
deliberately **not** sensitive categories — see
`docs/contracts-policy-matrix.md` for why, and note that this corpus depends
on `obligation` having no detection rule (below).

`tests/test_corpus_contracts_coverage.py` pins that this set has not drifted
from the live registries it mirrors: the detector's `LABELED_CONTRACTS_RULES`,
`configs/policies/contracts-v1.yaml`, B1's `ACTIONS`, B2's `ACTIONS` and
`TASK_AWARE_ACTION_SPACES`.

### Obligation-relation object

| Field | Type | Notes |
| --- | --- | --- |
| `obligor_role` | non-empty string | The role that owes, exactly as it appears as a detector label in `input.text` (e.g. `Contracting party`). |
| `obligee_role` | non-empty string | The role it is owed to. Must differ from `obligor_role`. |
| `obligation` | non-empty string | What is owed, in role/reference terms — e.g. `must pay the contract value by the deadline`. Never a literal amount or date. |
| `depends_on_categories` | non-empty list of this domain's frozen categories | Every category the obligation's *content* depends on (the amount it is owed in, the deadline it falls due on). |

**Why the relation is recorded by role, not by identity.** Issue #56 froze the
mechanism this annotation records against: the detector captures only its
`value` group, so the **role lives in the label** (`Contracting party:`) and is
never inside a detected span, while the **identity lives in the value** and is
pseudonymized. An obligation phrased by role therefore survives the disclosure
boundary with its assignment intact and needs no relation model at runtime.
Recording the relation by role is also the only form that is checkable against
a *transformed* payload at all — an identity-phrased relation could only ever
be checked against B0's untransformed output.

Writing a party's actual name into any of these fields would put a raw
sensitive value into the oracle. Three separate corpus-level tests reject it:
no relation field may contain any of its case's own span values, no
`obligation` may restate a literal amount or date, and every role named must
be a labeled line in the case's own `input.text`.

**What relation preservation is proven for, and what it is not.** Only for an
obligation phrased **by role**, on the document's own `Obligation:` line. It is
explicitly **not** proven — and does not hold — for a party named directly in
unlabeled prose: the detector is a labeled-line matcher, so such a name is not
a detected span and reaches the external payload verbatim
(`docs/contracts-policy-matrix.md`, "Known limitations", item 1). This corpus
is authored **around** that frozen limitation, not against it: every party
mention sits on its own labeled line, with consistent naming, and no case
contains a natural-prose party mention. Closing that gap is coreference
resolution and is out of scope for both Issue #56 and this ticket.

## Task-necessity labels, coherence and grounding

Identical rules to `corpus/hr/v1/SCHEMA.md`:

- `task_necessity` is the primary, binary oracle (`required` /
  `not_required`); `helpful` is a separate auxiliary flag and never a third
  value.
- For every non-blocked case, the set of categories with at least one
  `required` span must equal `oracle.answer_depends_on_categories` exactly
  (`tests/test_corpus_contracts_coverage.py`).
- `oracle.expected_answer` must be checkable purely from `input.text`. Every
  monetary figure **and every date** it cites must be a verbatim substring of
  `input.text`; a case that needs a reference threshold states it explicitly
  on a line the detector matches against no frozen category (e.g.
  `Approval threshold for this contract class: R$ 3000000.00`). The date check
  is Contracts-specific — a deadline is this domain's second kind of citable
  reference figure.
- Every category annotated anywhere must discriminate (appear at least once as
  `required` and once as `not_required`), except a documented exemption set:
  `cnpj`, `cpf` and `bank_account`. A registry number is never what a contract
  task needs, which is exactly why `contracts-v1` removes both; a bank account
  only ever appears in a case that must block. The exemption list is itself
  tested for being exercised rather than merely declared.

## Conformance and utility are independent oracles

Identical to `corpus/hr/v1/SCHEMA.md`'s section of the same name:
`expected_actions` is the **conformance** oracle, `expected_answer` (with
`answer_depends_on_categories`) is the **utility** oracle, and conformance does
not imply utility. A case's text, offsets, reference values or acceptable
action sets are never adjusted after the fact to make a currently-implemented
transformation's output happen to fit.

Contracts v1 has two standing examples of that, both left in place on purpose:

- **`deadline` where the task does not need it.** Six cases annotate
  `deadline` as `not_required` with `[remove, generalize]`. `contracts-v1`
  resolves `deadline` to a hard PRESERVE — deliberately more disclosing than
  B3 — Task-aware would be on its own, because a legal date coarsened to a
  month cannot be complied with or enforced. B4 — Policy-governed is therefore
  nonconformant on those six spans. That is an identifiable B3→B4 cell in the
  under-studied direction (governance choosing enforceability over
  minimization), not an oracle defect to widen away.
- **`cnpj`/`cpf` under B2 — Reversible Pseudonymization.** B2's static map
  pseudonymizes every identifier, while `contracts-v1` and this oracle both
  say REMOVE, because a CNPJ is publicly resolvable and would make a
  pseudonymized party name decorative. B2 is nonconformant on those spans by
  construction. That is a real, measured property of a task- and
  policy-independent treatment meeting a domain whose identifiers differ in
  kind — the gap B4 closes.

## Task families

Every case's `task_family` is one of six, and each exists to make a specific
treatment or governance difference observable:

1. `contract_summary_without_identity` — the commercial terms matter, party
   identity does not (2 cases).
2. `contract_value_audit` — the contract value figure is needed, under a
   `purpose` that may (`financial_audit`) or may not (`contract_summary`)
   authorize disclosing it exactly. This is the pair that exercises the one
   governance dimension `contracts-v1` actually reads (2 cases).
3. `penalty_compliance_review` — the penalty regime is needed while the
   contract value is not, which is precisely the discrimination the two
   separate monetary categories exist to make possible (2 cases).
4. `deadline_tracking` — an enforceable deadline is needed to the day, so
   `preserve` is the only acceptable action and a month-level generalization
   is not enough (2 cases).
5. `payment_details_block` — a `Bank account:` line is present, so the request
   must block under every treatment above B0, even though the rest of the task
   is perfectly reasonable and genuinely needs information (2 cases).
6. `obligation_relation_preservation` — a role-referenced obligation whose
   "who owes what to whom" must survive the disclosure boundary, stated in
   both directions across the two cases so that a treatment which always bound
   the first-named party to the obligor role would fail one of them (2 cases).

The corpus must include at least one case in each family
(`tests/test_corpus_contracts_coverage.py`).

## Freeze rule

See `README.md` in this directory: once this corpus (schema + cases +
annotations) merges to `master`, v1 is immutable. Any change to the schema, an
existing case's text/offsets/labels, or the set of cases requires a new
`corpus/contracts/v2/`, never an in-place edit of v1.
