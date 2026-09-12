# Contracts validation corpus — v1

T24 / GitHub Issue #37: the second-domain validation corpus and frozen oracle
that follow the completed HR pilot, built on the Contracts domain support
frozen by Issue #56 / PR #59.

## What this is

12 synthetic Contracts cases (`cases/*.yaml`), each pairing:

- an `input` block: controlled text, task/instruction and `GovernanceContext`
  fields a disclosure treatment may legitimately see;
- an `oracle` block: expected sensitive spans/categories/offsets,
  task-necessity labels, acceptable action sets, expected `BLOCK_REQUEST`
  behavior, expected answer, pseudonym-reconstruction expectations, and — new
  in this corpus — the **obligation relation** ("who owes what to whom", in
  role terms). Used only for scoring, never given to a treatment as input.

The schema is described in prose in `SCHEMA.md` and enforced in code by
`src/adaptive_disclosure_gateway/corpus/`.

## Run classification — decided in advance

**`pilot_development`.**

This was fixed by the project owner **before this corpus existed** and
**before any B0–B4 Contracts result had been produced or inspected**. It is
not a reaction to what the results turned out to look like, and it is not
revisable on that basis.

What it means concretely:

- this corpus and the run recorded under
  `artifacts/experiments/contracts/v1/` are **not confirmatory evidence**;
- a **held-out confirmatory Contracts run remains a separate future step**,
  governed by `docs/research/post-pilot-protocol-v1.md`;
- the corpus and oracle are nonetheless **frozen and versioned** exactly as
  `corpus/hr/v1` is (see the freeze rule below), precisely so that a future
  confirmatory run has a fixed artifact to be held out *from*, and so that
  nothing in it can be quietly adjusted once results exist.

The classification is recorded in three independent places: here, in
`RunIdentity.run_classification` for every result the runner produces, and in
the run manifest's `reproducibility` mapping (which also records that it was
fixed in advance).

## Domain covered

All cases are in the `contracts` domain, against the `contracts-v1` policy
(`configs/policies/contracts-v1.yaml`), and use only the eight categories
frozen by Issue #56: `party_name`, `representative_name`, `cnpj`, `cpf`,
`bank_account`, `contract_value`, `penalty_amount`, `deadline`. `cnpj` and
`cpf` are the two HR-era categories that freeze reused unchanged;
`obligation` and `confidential_clause` are deliberately not sensitive
categories, and this corpus depends on `obligation` having no detection rule.

Six task families, two cases each — see `SCHEMA.md`'s "Task families" for what
each family exists to make observable:

| Case | What it is for |
| --- | --- |
| `contracts_summary_001` | Value against a stated approval threshold; party identity not needed. Also the first case where `deadline` is annotated `not_required`, which `contracts-v1` preserves anyway. |
| `contracts_summary_002` | Same shape with a signatory (`Representative:` + `CPF:`) and a penalty present but not needed. |
| `contracts_value_audit_001` | `purpose: financial_audit` — the one purpose `contracts-v1` lets preserve `contract_value` exactly. The band contains the reference figure, so `preserve` is the only action carrying the answer. |
| `contracts_value_audit_002` | The same kind of question under `purpose: contract_summary`, with the task explicitly asking for the specific figure. Policy restricts it to `generalize`; the band still answers the question. |
| `contracts_penalty_review_001` | `purpose: compliance_review` — the penalty regime is needed exactly, and the contract value is *not* unlocked by the same purpose. |
| `contracts_penalty_review_002` | The same question under a purpose that does not authorize `preserve`, and phrased without an exactness cue, so B3 and B4 are expected to agree. |
| `contracts_deadline_tracking_001` | An enforceable delivery deadline needed to the day; amounts and identities not needed. |
| `contracts_deadline_tracking_002` | The same, varying `requester_role` and `provider_class` — neither of which `contracts-v1` reads, which is the point. |
| `contracts_payment_block_001` | A `Bank account:` line in a task that genuinely needs the amount and the date. The request blocks anyway. |
| `contracts_payment_block_002` | A block case whose task needs a natural person's name and an enforceable date, so the block is not cost-free. |
| `contracts_obligation_relation_001` | Role-referenced obligation: contracting party owes payment to contracted party. Both party names `required` with `pseudonymize` as the only acceptable action. |
| `contracts_obligation_relation_002` | The obligation runs the other way (contracted party owes the contracting party), and the signatory's name is `required`. |

## Synthetic data notice

Every party name, representative, CNPJ, CPF, bank account, amount and date in
this corpus is invented for this corpus. **No confidential document, no
employer or client contract and no real personal data was used anywhere.**
None of it was copied from `tests/contracts_fixture.py` either: that file is
development-only evidence and its own header forbids reuse as
held-out/confirmatory material, so every case here was authored fresh.

CNPJ/CPF values match the detector's punctuated formats
(`##.###.###/####-##`, `###.###.###-##`) but are not validated check digits —
consistent with `detection/rules.py`, which does not validate them either.

## No parser stage

Every case is hand-authored plain text. No PDF, DOCX, XLSX or Markdown
document is ingested, and **T12's Docling/normalization path is not exercised
by this corpus at all**. There is therefore no parser whose provenance could
vary between treatments and none is recorded: `post-pilot-v1` §13.2's
`parser_ingestion_version` requirement applies "once T12/Docling is in use",
which is not the case here. The manifest records
`parser_ingestion_version: not_applicable_plain_text_corpus` explicitly, so a
reader can tell "no parser ran" apart from "nobody wrote it down". Fabricating
parser/ingestion identifiers for a stage that never executed would be invented
provenance.

A future Contracts corpus version that ingests structured documents must
normalize **once**, record real `parser_name`/`parser_version`/
`ingestion_version` from `NormalizedContent`, and hand the identical
`NormalizedContent.text` to B0–B4.

## Limitations and threats to validity

### Detection is near-perfect by construction

Every case presents sensitive values in the same labeled-line format
(`Contracting party:`, `Contracted party:`, `Representative:`,
`Bank account:`, `Contract value:`, `Penalty:`, `Deadline:`) plus punctuated
CNPJ/CPF, and `detection/rules.py` keys on exactly those. Measured against
this corpus the detector finds 72 of 72 annotated spans with no false
positives.

That figure is a property of the corpus format, not evidence about detector
quality, and it has the same two-sided consequence `corpus/hr/v1/README.md`
records: it does **not** confound the treatment comparisons (detection is held
constant across B0–B4), but it **does** inflate absolute figures. Any absolute
claim about exposure reduction, detector recall or residual sensitive content
measured here must be reported as an upper bound obtained under a
structured-input assumption.

### No coreference resolution — and the corpus is authored around it

`docs/contracts-policy-matrix.md`'s known limitation 1: a party named in
ordinary clause prose is not a detected span and reaches the external payload
verbatim. This corpus therefore places **every party mention on its own
labeled line**, with consistent naming, and states every obligation **by
role** on an `Obligation:` line. That is the only shape relation preservation
is proven for.

This is a deliberate scoping decision, not a claim that the gap is closed. A
real contract states parties in prose constantly, so a corpus that exercised
that shape would measure coreference resolution — which nothing in this
project implements — rather than disclosure control. The limitation was not
patched to suit the corpus, and the corpus does not pretend it is absent.

### The utility scorer's GENERALIZE rule is numeric-band-specific

Discovered while validating this corpus, reported rather than fixed:
`experiments/scoring/utility.py`'s decidability rule parses a generalized
value as a numeric band (`<lower>-<upper>`). Applied to
`MonthYearDateStrategy`'s output (`2026-02`), it reads "2026" as a lower bound
and "02" as an upper bound and reports `generalized_band_decidable` — so B3's
month-coarsened deadline is scored `answerable` even though the day, the only
thing an enforceable deadline needs, is gone.

It is **not** fixed here: `post-pilot-v1` freezes the metric set, and changing
a metric definition while building the corpus that will be scored by it is
exactly the retuning the protocol exists to prevent. The conformance oracle
does catch the same situation (B3 is nonconformant on every `required`
deadline span), so the loss is visible in this corpus's results — it is the
*utility* dimension that reads it optimistically. Closing this needs a
date-aware decidability rule and a protocol version that admits it.

### FakeProvider only

Everything executed against this corpus so far used `FakeProvider`. Per T22 /
Issue #30 — open and parallel — nothing here supports a claim about real LLM
utility, real token counts, real cost or real provider behaviour. Utility is
scored as an information-sufficiency proxy over the disclosure-controlled
payload, exactly as in the HR pilot.

### Small N, single policy version

12 cases, one policy version (`contracts-v1`). There is no second Contracts
policy version, so no `policy_version` contextual comparison is possible and
none is run; `requester_role` and `provider_class` are recorded but read by no
Contracts rule. Only `purpose` produces a governance effect here.

## Freeze rule

**v1 is immutable once merged to `master`.** This includes the schema
(`SCHEMA.md`), every case file under `cases/`, and every annotation inside
them. Any future change — adding a case, correcting an annotation, adding a
category, changing an offset — creates a new version directory
(`corpus/contracts/v2/`, and so on) rather than editing v1 in place. This
keeps any run that cites "Contracts corpus v1" reproducible against an
unchanging artifact.

If a defect is found in a v1 annotation after it has been used for scoring,
document it (do not silently patch v1) and address it in the next version.

## Freeze record

The machine-readable freeze record is the `reproducibility` mapping in each
run's `manifest.json` under `artifacts/experiments/contracts/v1/<run_id>/`,
written by `scripts/run_contracts_v1_pilot.py` through the project's existing
`artifacts.write_pilot_artifacts` mechanism — no new format was invented. It
carries the corpus version, oracle version, corpus schema version, freeze date
and base commit, the Issue #56 domain-freeze commit, the protocol id
(`post-pilot-v1`), the parser/ingestion status, the run classification and the
fact that it was decided in advance, the policy versions available and used,
the frozen B3/B4 treatment commits and the treatment chain, and the provider
identity/decoding configuration.

- Corpus version: `contracts/v1`
- Oracle version: `contracts/v1` (versioned one-to-one with the input today)
- Schema version: `corpus-case-schema-v2`
- Policy version: `contracts-v1`
- Protocol id: `post-pilot-v1`
- Contracts domain freeze (Issue #56 / PR #59): `5a67c30daab68d06bbd16d1cf06433de97245910`
- Corpus freeze date: 2026-09-12
- Corpus freeze base commit: `5a67c30daab68d06bbd16d1cf06433de97245910` (the `develop` commit this corpus was authored on; the corpus's own freeze commit is the commit that merges T24)
- Run classification: `pilot_development`, fixed in advance

## Nothing frozen by Issue #56 was changed

Building this corpus required **no** change to the Contracts categories,
detector rules, policy documents, B3 action spaces, generalization strategies
or the definition of any treatment — which was Issue #56's stated success
criterion. The only schema change was the per-domain corpus vocabulary, which
`docs/contracts-policy-matrix.md` itself flagged in advance as the expected,
non-semantic T24 change.
