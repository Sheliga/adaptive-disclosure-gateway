# Contracts policy matrix — Issue #56

This document is the **freeze point for Contracts domain support**. It
mirrors `docs/hr-policy-matrix.md` and uses the project's existing freeze
mechanism — a policy `version:` string (`contracts-v1`) plus a prose matrix —
rather than inventing a new one.

It records exactly what T24 / Issue #37 may rely on being stable while it
builds the Contracts v1 corpus and oracle: the frozen category set, detector
behaviour, policy actions, B3 — Task-aware action spaces, generalization
strategies, and the relation semantics.

**Nothing here was derived from a Contracts case.** No Contracts corpus,
oracle or case file exists yet, and no B0–B4 Contracts run has been executed
or inspected. Every value in this matrix was authored from the domain itself
and frozen before any evidence could exist to tune it against.

## Artifacts

- `configs/policies/contracts-v1.yaml` — the policy document (this freeze).
- `src/adaptive_disclosure_gateway/detection/rules.py` — `LABELED_CONTRACTS_RULES`.
- `transformations/static_sanitization.py`, `transformations/reversible_pseudonymization.py`,
  `transformations/task_aware.py`, `transformations/generalization.py`,
  `task_analysis/deterministic.py` — the per-treatment wiring.
- `tests/test_contracts_domain.py` — the executable half of this document.
- `tests/contracts_fixture.py` — development-only synthetic fixtures.

## A note on the `contracts-v1` version string

An aspirational `contracts-v1` existed before this ticket. It was never
functional: not one of its nine declared categories had a detection rule, an
entry in any treatment's action map, or a generalization strategy. A
Contracts request under it detected nothing, and any category that had
somehow arrived would have failed closed to `BLOCK_REQUEST` in every
treatment. It also carried a top-level `semantic_constraints:` block
(`preserve_party_roles`, `preserve_obligation_assignment`) that
`PolicyDocument` never declared and Pydantic silently dropped.

Because it was never referenced by any corpus, oracle or experimental run,
there is no evidence depending on its previous contents, and the version
string is kept: **the freeze point for `contracts-v1` is this ticket, not its
former shape.** (Contrast `hr-v1`, which is genuinely frozen because
`corpus/hr/v1` depends on it — it was not touched.)

The silently-dropped-key problem was fixed structurally, not by editing one
YAML: every policy model in `policies.py` now sets `extra="forbid"`, so an
unknown governance key makes the document fail to load and every request
under that version resolves to `BLOCK_REQUEST`. A governance knob that looks
enforced and is ignored is the fail-*open* direction; this makes that
impossible to reintroduce. All five shipped policy documents load cleanly
under the stricter model (pinned in `tests/test_policy_engine.py`).

## The frozen Contracts category set

Eight categories. Two of them already existed and were reused unchanged.

| Category | Origin | Detector label | `contracts-v1` action | B1 | B2 | B3 action space | Generalization strategy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `party_name` | new | `Contracting party:` / `Contracted party:` | `pseudonymize` | `remove` | `pseudonymize` | `(remove, pseudonymize)` | — |
| `representative_name` | new | `Representative:` | `pseudonymize` | `remove` | `pseudonymize` | `(remove, pseudonymize)` | — |
| `cnpj` | **reused** | structured pattern | `remove` | `remove` | `pseudonymize` | `(remove, pseudonymize)` | — |
| `cpf` | **reused** | structured pattern | `remove` | `remove` | `pseudonymize` | `(remove, pseudonymize)` | — |
| `bank_account` | new | `Bank account:` | `block_request` | `block_request` | `block_request` | `(block_request,)` | — |
| `contract_value` | new | `Contract value:` | `task_dependent` | `generalize` | `generalize` | `(remove, generalize, preserve)` | `NumericBandStrategy(50000, "R$ ")` |
| `penalty_amount` | new | `Penalty:` | `task_dependent` | `generalize` | `generalize` | `(remove, generalize, preserve)` | `NumericBandStrategy(5000, "R$ ")` |
| `deadline` | new | `Deadline:` | `preserve` | `generalize` | `generalize` | `(remove, generalize, preserve)` | `MonthYearDateStrategy()` |

`tests/test_contracts_domain.py` asserts, per category, that the set above is
wired **consistently across all of** detection, B1's `ACTIONS`, B2's
`ACTIONS`, `TASK_AWARE_ACTION_SPACES`, `CATEGORY_INDICATORS`,
`GENERALIZATION_STRATEGIES` (exactly where GENERALIZE is reachable) and the
YAML itself. A half-wired category fails the build, which is the point: a
category present in some registries and absent from others is either a silent
`BLOCK_REQUEST` or a rule that can never fire.

### Why each category, and why not the others

**`party_name`, one category with two role labels.** A contract's meaning is
relational, so the role must survive while the identity is transformed. That
falls out of the detector's existing `group="value"` mechanism for free: the
role word lives in the *label*, which is never inside a detected span, so a
pseudonymized payload still reads `Contracting party: PSEUDO-party_name-…` /
`Contracted party: PSEUDO-party_name-…`. Splitting the role into two
categories would have duplicated every policy and action-space entry to
express something document structure already carries.

**`representative_name` kept separate from `party_name`.** They are different
legal objects: a contracting party is normally a legal entity, which is not
an LGPD data subject, while a signatory/legal representative is a natural
person whose name is personal data. They resolve to the same action under
`contracts-v1` today; the separation exists so a policy can move one without
the other, and so the audit trail can say which of the two was disclosed.

**`cnpj` / `cpf` reused instead of a `tax_id` category.** The aspirational
policy named `tax_id`, but that is the same information type the detector
already recognizes under two more precise names, both already wired into
every treatment. Adding a third synonym would have created a category that
looks governed and never fires. Both are `remove` rather than `pseudonymize`
under `contracts-v1`, and that is load-bearing: a CNPJ identifies a company
far more precisely than its name does and is publicly resolvable, so
preserving it next to a pseudonymized `party_name` would make the pseudonym
decorative. Pinned adversarially in `tests/test_contracts_domain.py`.

**`contract_value` and `penalty_amount` as two categories, not one.** The
decisive argument is discrimination, not taxonomy: with a single merged
"monetary amount" category, a task asking about the penalty regime could not
be served without also disclosing what the contract is worth. As two
categories with separate indicator tables, B3 preserves the penalty and
removes the contract value for exactly that task — and `contracts-v1` can let
`financial_audit` preserve the value while `compliance_review` preserves the
penalty, neither unlocking the other. Both behaviours are pinned as tests.

**Band widths differ because the quantities do.** A R$ 5.000 band around a
R$ 2.400.000 contract is a point estimate wearing a range; a R$ 50.000 band
around a R$ 12.000 penalty discloses nothing. Both sit far above
`MIN_NUMERIC_BAND_WIDTH` (R$ 1.000). Neither width was chosen against an
outcome — no outcome exists.

**`deadline` as a hard `preserve`, deliberately more disclosing than B3.**
`MonthYearDateStrategy` *is* registered for it, so GENERALIZE is genuinely
available, and it is in B3's action space — including it is the *less*
disclosing choice, since without an intermediate step any positively
mentioned deadline would jump straight to PRESERVE. But a legal deadline
coarsened to a month is not a term of a contract: "sometime in March" cannot
be complied with or enforced. So the policy resolves it to PRESERVE, which is
a legitimate governance direction (policy may move above B3's own choice;
`policy_restricted` is `False`, not `None`, for such a cell — see
`transformations/policy_governed.py`). This is an identifiable B3→B4 cell in
the under-studied direction.

**`obligation` dropped.** It was in the aspirational policy mapped to
`preserve`. Obligation text is the *task-bearing content* of a contract, not
a sensitive information unit; detecting it would put ordinary clause prose
under disclosure control for no safety gain and considerable utility loss.
The thing that actually matters — that a concrete obligation stays correctly
*attributed* to the right pseudonymized party — is preserved structurally by
the role/value split above and pinned by test, with no relation model added,
but **only for an obligation phrased by role** (e.g. an `Obligation:` line
reading "Contracting party must pay Contracted party ..."). See "Relation
semantics" below for exactly what is and is not proven, and for which
obligation shape.

**`confidential_clause` dropped.** No deterministic detector for it is
possible within this project's stated posture. A `Confidential clause:` label
would not detect a clause; it would detect an author's *classification* of
one — i.e. oracle information reaching the detector at runtime, which the
methodology forbids. Deciding that a clause is confidential is a semantic
judgement, and the detector is explicitly not a semantic component.

## Relation semantics — what T24 may rely on

Issue #56 asks for "who owes what to whom" to survive. It does, through two
mechanisms that already existed. **No relation model was added.** This has
two layers, proven by separate tests, and it matters not to conflate them:

1. **Role in the label, identity in the value.** The detector captures only
   its `value` group, so the role word is never part of a detected span and
   is never removed, banded or pseudonymized.
2. **Stable pseudonyms per value.** `Vault.pseudonymize` returns the same
   pseudonym for the same original value within a `(scope, scope_key)`
   partition, and never the same pseudonym for two different values. So the
   same company reads identically across the contract and its amendments,
   while the two parties never collapse into one reference.

Those two mechanisms, on their own, prove that **party roles survive with
stable, distinguishable pseudonyms** — pinned by
`test_party_roles_survive_pseudonymization_with_stable_distinguishable_pseudonyms`
against `CONTRACTS_FIXTURE`. `CONTRACTS_FIXTURE` states no obligation at all
(no "X must pay Y" sentence anywhere in it), so that test cannot, and does
not, prove that a concrete obligation stays correctly *attributed* to the
right party. That is a separate, stronger claim, proven separately:

**A concrete obligation — "X must pay Y `<amount>` by `<date>`" —
attributed to the right pseudonymized role.** `CONTRACTS_OBLIGATION_FIXTURE`
adds one, and `test_role_referenced_obligation_binds_the_correct_pseudonym_to_each_role`
demonstrates that `ACME must pay Beta R$ X by D` becomes `[party A] must pay
[party B] [banded amount] by [transformed deadline]` — reconstructable from
the transformed payload alone, not merely "two distinguishable pseudonyms
exist somewhere in it".

**This is proven for exactly one obligation shape: phrased BY ROLE**, e.g.
an `Obligation:` line reading "Contracting party must pay Contracted party
the contract value by the deadline". That shape needs no relation model
because it reuses the same two words already used as labels elsewhere in the
document; the sentence itself carries no detected span (`obligation` has no
detection rule — see "obligation dropped" above) and is never itself
transformed, so it reaches the payload unchanged in every treatment. The
amount and deadline it refers to are carried, and transformed, by the
document's existing `Contract value:` / `Deadline:` lines, not restated
inline in the obligation sentence — restating them inline would put literal
figures outside every detection rule and leak them.

**This is explicitly NOT proven for an obligation phrased in natural prose
naming a party directly** (e.g. "Aurora … shall pay the contract value to
Boreal … on the deadline"). `CONTRACTS_COREFERENCE_FIXTURE`'s `Clause 4` IS
exactly this shape, and
`test_a_party_named_in_unlabeled_prose_is_not_detected_and_reaches_the_payload`
shows what actually happens: the raw party name is not inside any detected
span, so it — and with it that specific obligation — reaches the external
payload verbatim, even though the same company's labeled mention two lines
above was pseudonymized. See "Known limitations" below; closing this gap is
coreference resolution, explicitly out of scope for Issue #56.

Consequences by treatment, all pinned as tests:

- **B0 — Direct**: no transformation at all.
- **B1 — Static Sanitization**: roles survive (they are labels) but both
  party values are removed, so the two parties become indistinguishable from
  each other and cross-document identity is lost. This is the B1→B2 utility
  gap the experiment measures, unusually visible in this domain. For a
  role-referenced obligation, the ROLE relation itself ("Contracting party
  must pay Contracted party") still reads intact under B1 — what is lost is
  which real company each role refers to, not the relation between the
  roles.
- **B2 / B3 / B4**: role, stability and distinguishability all preserved, and
  authorized local reconstruction restores `Contracting party: ACME …`. B4
  additionally hard-preserves the exact `deadline` (see the category table
  above), so a role-referenced obligation's deadline is disclosed exactly
  under B4 while its amount is still banded.

## Governance dimensions and their identifiability

| Dimension | Cell demonstrating the effect | Held constant elsewhere |
| --- | --- | --- |
| `purpose` | `contract_value`: `financial_audit` → `[remove, generalize, preserve]` vs. any other purpose → `[remove, generalize]`. `penalty_amount`: the same, for `compliance_review`. | `party_name`, `representative_name`, `cnpj`, `cpf`, `bank_account`, `deadline` never read `purpose`. |
| `requester_role` | Not used by `contracts-v1`. | — |
| `provider_class` | Not used by `contracts-v1`. | — |
| `policy_version` | Not comparable — `contracts-v1` is the only Contracts policy version. | — |

`requester_role`, `provider_class` and a second policy version are
architecturally supported and deliberately unused here: `contracts-v1` is
domain *support*, not the contextual B4 matrix (`hr-v2`/`hr-v3` already play
that role for the pilot). Adding them later changes no category's semantics.

`pseudonym_scope` is likewise omitted, so the model default applies (session
scope, no role ceilings). Pseudonym-scope policy is a separate governance
axis from per-category disclosure action, and the two must not be confounded
— the same separation `hr-v2`/`hr-v3` keep.

## Known limitations — read before building the T24 corpus

**1. No coreference resolution.** The detector matches labeled lines. A party
named again inside ordinary clause prose ("Aurora … shall pay …") is *not* a
detected span, so it is neither pseudonymized nor removed and it reaches the
external payload verbatim — even though the same company's labeled mention
two lines above was pseudonymized. This is a real disclosure gap, not merely
a utility gap. Building coreference resolution is far outside Issue #56.

This is the same gap a natural-prose **obligation** sentence falls into when
it names a party directly instead of referring to it by role: "Aurora …
shall pay the contract value to Boreal … on the deadline" leaks the name and
therefore that specific obligation. "Who owes what to whom" is proven to
survive only for an obligation phrased BY ROLE (an `Obligation:` line reading
"Contracting party must pay Contracted party …" — see "Relation semantics"
above); it is not proven, and does not hold, for a natural-prose obligation
naming a party. T24 cases stating an obligation must use the role-referenced
shape, or be classified knowing this gap.

> **Constraint on T24:** every party mention must sit on its own labeled
> line, using consistent party naming (`ACME Serviços Ltda` everywhere, not
> `ACME` in one line and the full legal name in another). A case that does
> not follow this must be classified knowing the gap. Pinned by
> `test_a_party_named_in_unlabeled_prose_is_not_detected_and_reaches_the_payload`,
> which fails if the behaviour ever changes — so the limitation cannot
> silently stop being documented.

**2. Representative-to-party attachment is positional.** The detector knows a
`Representative:` line exists; it does not know which party it signs for.
T24's cases should place a representative line immediately after its party's
block.

**3. Labels are case-sensitive and English**, matching the existing HR rules
and the frozen HR corpus's own style. This is a fixture-format convention,
not a claim about real Brazilian contract documents.

**4. Corpus schema is still HR-only.** `corpus/models.py` hardcodes
`HrCategory` / `FROZEN_HR_CATEGORIES` as an HR-only `Literal`, so a Contracts
corpus cannot yet be expressed. That is **corpus schema work owned by T24 /
Issue #37**, not treatment semantics — it does not violate Issue #56's "T24
must not need semantic changes" criterion, and it is deliberately not
implemented here. It is an expected, non-semantic T24 change.

## Development fixtures are not evidence

`tests/contracts_fixture.py` is synthetic, invented for this test suite, and
contains no employer, client or confidential data. It lives under `tests/`
and never under `corpus/`, and its header states that it must not be reused
as held-out/confirmatory evidence without an explicit recorded methodological
decision. T24 owns the Contracts v1 corpus; none of it exists yet.
