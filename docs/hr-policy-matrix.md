# HR policy matrix — T08 / issue #7, Phase A

This document freezes the controlled contextual policy matrix the B3→B4
comparison measures against, per `docs/experimental-design.md`'s Phase A
requirement: the matrix must be defined, versioned and justified as
plausible governance *before* B4 results are used as experimental evidence,
and it must not be tuned after observing treatment outcomes.

Three policy documents exist for the `hr` domain:

- `configs/policies/hr-v1.yaml` — the pre-existing, frozen baseline. **Not
  edited by this ticket.** The frozen corpus (`corpus/hr/v1`) and B2/B3's
  behavior both depend on it exactly as it was.
- `configs/policies/hr-v2.yaml` — the new controlled governance matrix,
  added alongside `hr-v1`.
- `configs/policies/hr-v3.yaml` — a small, deliberately documented variant
  of `hr-v2`, differing in one cell, to give the experiment a
  `policy_version` comparison.

## Inventory: what `hr-v1` actually varies (confirmed)

Before designing `hr-v2`/`hr-v3`, this ticket measured `hr-v1`'s actual
behavior against `PolicyRepository.decide()` rather than assuming it from
the YAML alone. The measurement is pinned as executable tests in
`tests/test_hr_policy_matrix.py` (section 1), not just asserted here:

| Dimension | Effect on resolved disclosure action under `hr-v1`? |
| --- | --- |
| `purpose` | **Yes — the only such cell.** `salary`'s `purpose_actions`: `team_summary`/`department_aggregation` (and any purpose absent from `purpose_actions`) resolve `allowed_actions = [remove, generalize]`; `salary_analysis`/`compensation_review` resolve `[remove, generalize, preserve]`. |
| `requester_role` | **No effect on any category's disclosure action.** It only affects pseudonym-scope resolution (`role_max`: `hr_viewer` → `request`, `hr_analyst` → `session`, `hr_admin` → `organization`), a *separate* axis from per-category disclosure action. Without an explicit `requested_pseudonym_scope` in the context, `hr_analyst` and `hr_admin` resolve to the *same* scope (`session`), because `role_max` is a ceiling (`min(requested, ceiling)`) and the default `requested_pseudonym_scope` (`SESSION`) already sits below both roles' own ceiling. |
| `provider_class` | **No effect whatsoever** — not on disclosure action, not on pseudonym scope. `hr-v1` has no rule or override keyed on it at all. |
| `policy_version` | **Not comparable** — `hr-v1` was, before this ticket, the only `hr`-domain policy version in existence. |

This confirms the brief's Phase A inventory exactly: `salary` × `purpose` is
the *only* cell in `hr-v1` that varies the resolved disclosure action space;
`requester_role` and `provider_class` are architecturally supported but
experimentally inert for disclosure action under `hr-v1`.

## The engine trap: `purpose_actions` silently overwrites a matched override

`PolicyRepository.decide()` (`src/adaptive_disclosure_gateway/policies.py`)
resolves a category in two steps:

1. find at most one matching `PolicyOverride` (by `purpose`/`requester_role`/
   `provider_class`, each optional/wildcard); if none matches, fall back to
   the rule's own `default`/`allowed_actions`;
2. **only if the resulting `action` is `TASK_DEPENDENT`**, unconditionally
   replace `allowed_actions` with `rule.purpose_actions.get(context.purpose,
   allowed_actions)`.

Step 2 does not know or care whether step 1 matched an override — it
overwrites whatever `allowed_actions` step 1 produced, including an
override's own `allowed_actions`, whenever the *matched* action happens to
be `TASK_DEPENDENT` and the rule has a `purpose_actions` entry for the
context's purpose. Concretely: an override written as `requester_role:
hr_viewer` with `action: task_dependent, allowed_actions: [remove]`, meant
to cap a viewer to `REMOVE` regardless of purpose, would be silently
replaced by `purpose_actions[purpose]` (e.g. `[remove, generalize,
preserve]` for `salary_analysis`) — the exact opposite of the override's
intent — every time a viewer's purpose happens to have its own
`purpose_actions` entry.

**Resolution taken (design, not an engine change):** every role/provider
override in `hr-v2`/`hr-v3` that is meant to *restrict* uses a **hard**
action (`remove`), never `task_dependent`. A hard action's branch in
`decide()` never reaches step 2 at all (`if action is
DisclosureAction.TASK_DEPENDENT:` guards it), so a hard-action override can
never be overwritten by `purpose_actions`, regardless of which purpose the
request carries. `tests/test_hr_policy_matrix.py::
test_requester_role_override_survives_every_purpose_including_ones_with_purpose_actions`
pins this directly: the `hr_viewer` salary override is checked against
*every* purpose in the matrix, including `salary_analysis` and
`compensation_review` (which both have their own `purpose_actions` entry).

`PolicyRepository.decide()` was **not modified**. `tests/test_policy_engine.py`
passes unmodified and unedited (see Closing results below), which is this
ticket's own bar for "the engine genuinely cannot express this cell" — it
was never reached, because option (a) (design around the trap) was
sufficient for every cell this matrix needs.

## `hr-v2` — the governance matrix, cell by cell

| Category | Rule shape | Governance rationale |
| --- | --- | --- |
| `employee_name` | `default: pseudonymize`; **override** `provider_class: external_llm → remove` (hard) | An external LLM provider is a stricter data boundary than one hosted inside the organization. Data leaving the boundary altogether should not even carry a locally-reversible reference; `internal_llm` (and any other/absent provider_class) keeps the reversible `pseudonymize` behavior `hr-v1` also uses. |
| `cpf` | `default: remove` | Held constant from `hr-v1`; no plausible governance scenario in this matrix relaxes a CPF removal. |
| `medical_data` | `default: block_request` | Held constant from `hr-v1` — hard block, never contextual. |
| `department` | `default: preserve`; **override** `requester_role: hr_viewer → remove` (hard) | A read-only viewer role should not receive even non-financial org-structure detail that an analyst/admin performing legitimate HR review may see. |
| `salary` | `default: task_dependent, allowed_actions: [remove, generalize]`; `purpose_actions`: `salary_analysis`/`compensation_review`/`headcount_planning` variants; **override** `requester_role: hr_viewer → remove` (hard) | Combines two axes on purpose (see "engine trap" above): (1) a compensation-focused purpose may additionally `preserve`, a generic purpose may not; (2) a viewer never receives salary in *any* form, for *any* purpose — the hard override holds regardless of which `purpose_actions` entry would otherwise apply. |

Purposes used: `team_summary`, `department_aggregation` (both fall back to
`salary`'s own `allowed_actions`, no `purpose_actions` entry — same
generic-purpose behavior `hr-v1` already has), `salary_analysis`,
`compensation_review`, `headcount_planning` (new purpose, generic — no
`preserve`, same shape as `team_summary`/`department_aggregation` but
included explicitly so the matrix documents a third, still-restrictive
purpose alongside the two compensation ones).

### Which cells change the action space, and which don't

| Dimension | Cell demonstrating the effect | Held constant elsewhere |
| --- | --- | --- |
| `purpose` | `salary`: `team_summary`/`department_aggregation`/`headcount_planning` → `[remove, generalize]` vs. `salary_analysis`/`compensation_review` → `[remove, generalize, preserve]` (same as `hr-v1`'s own shape, re-declared in `hr-v2`) | `employee_name`, `cpf`, `medical_data`, `department` never read `purpose` at all. |
| `requester_role` | `salary`: `hr_viewer` → hard `remove` vs. `hr_analyst`/`hr_admin` → `task_dependent` (full purpose-keyed space); `department`: `hr_viewer` → hard `remove` vs. others → `preserve` | `cpf`, `medical_data` never read `requester_role`; pseudonym-scope ceilings (a separate axis) are unaffected by this table. |
| `provider_class` | `employee_name`: `external_llm` → `remove` vs. `internal_llm` (or unspecified) → `pseudonymize` | `cpf`, `medical_data`, `department`, `salary` never read `provider_class` in `hr-v2`. |
| `policy_version` | See `hr-v3` below | — |

`requester_id` overrides are intentionally absent from this matrix (out of
scope per the brief). No rule here was derived from `corpus/hr/v1`,
`sample_id`, `task_family`, or any oracle field, and no cell was adjusted
after observing a B4 result — the matrix was designed and frozen before any
B4 code was written (see the TDD test log in the closing PR).

## `hr-v3` — the one documented delta from `hr-v2`

`hr-v3` is byte-for-byte identical to `hr-v2` except one line: `salary`'s
`compensation_review` `purpose_actions` drops `preserve`:

```diff
     purpose_actions:
       salary_analysis:
         - remove
         - generalize
         - preserve
       compensation_review:
         - remove
         - generalize
-        - preserve
       headcount_planning:
         - remove
         - generalize
```

**Governance rationale:** `hr-v3` represents a tightened compensation-review
policy (e.g. adopted after an internal audit) that still allows a
banded/generalized view of compensation for that purpose, but no longer
lets the exact figure leave the boundary. `salary_analysis` is deliberately
left unchanged, so the two purposes — identical under `hr-v2` — diverge from
each other only under `hr-v3`. This gives the experiment a same-case,
same-context `policy_version` comparison
(`tests/test_hr_policy_matrix.py::test_policy_version_dimension_changes_the_resolved_action_space_between_v2_and_v3`)
without also changing anything else in the matrix, keeping the comparison
controlled.

## Identifiability guarantee

`tests/test_hr_policy_matrix.py` section 2 pins, as a real, independently
failing test per dimension, that each of `purpose`, `requester_role`,
`provider_class` and `policy_version` has at least one matrix cell where the
resolved action (or resolved allowed-action space) genuinely differs when
only that one dimension changes and everything else is held constant. If a
future edit flattens any one of these cells back to a constant resolution,
the corresponding test fails — this is the safeguard against the matrix
being silently reduced back to `hr-v1`'s "only `purpose` actually matters"
shape without anyone noticing.

## Pseudonym-scope policy stays a separate axis

`hr-v2`/`hr-v3` reuse `hr-v1`'s `pseudonym_scope` block verbatim (`default:
session`, the same `role_max` ceilings). This is deliberate: the B4
experiment's contextual matrix is about *disclosure-action* policy, not
pseudonym-scope policy, and the two must not be confounded. Changing
pseudonym-scope behavior between `hr-v1`/`hr-v2`/`hr-v3` would make a
`policy_version` comparison ambiguous about which axis actually moved.
