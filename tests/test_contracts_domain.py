"""Frozen Contracts domain support (Issue #56).

Every fixture these tests use is DEVELOPMENT-ONLY synthetic material from
``tests/contracts_fixture.py`` -- read that module's header before reusing
anything here. None of it is corpus/oracle evidence; T24 / Issue #37 owns
the Contracts v1 corpus and no case of it exists yet.

What this module pins, in order:

1. **Registry consistency.** ``configs/policies/contracts-v1.yaml`` is the
   freeze artifact (the project's existing pattern: a ``version:`` string
   plus a prose matrix, ``docs/contracts-policy-matrix.md``). Every category
   it names must be wired across *all* of detection, B1's ``ACTIONS``, B2's
   ``ACTIONS``, B3's ``TASK_AWARE_ACTION_SPACES``, the deterministic
   analyzer's ``CATEGORY_INDICATORS`` and -- wherever GENERALIZE is
   reachable -- ``GENERALIZATION_STRATEGIES``. A category wired into some
   but not all of those is not a harmless gap: it is either a silent,
   unexplained BLOCK_REQUEST (a category with no action-space entry) or a
   category that can never fire at all (no detection rule). This is the test
   that makes a future half-wired Contracts category fail the build.
2. **Detection**, on the synthetic fixture.
3. **Relation preservation across B1 -> B4** -- the "who owes what to whom"
   requirement Issue #56 names. No relation model was added; see below for
   why the existing role-in-label / identity-in-value split plus the vault's
   per-value pseudonym stability already carries it.
4. **Documented limitations**, pinned as tests so they cannot quietly stop
   being true (or quietly stop being documented).
5. **Adversarial no-leak checks** for every new sensitive path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adaptive_disclosure_gateway.detection import Detector
from adaptive_disclosure_gateway.detection.rules import BUILT_IN_RULES
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureRequest,
    GovernanceContext,
)
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.task_analysis.deterministic import CATEGORY_INDICATORS
from adaptive_disclosure_gateway.transformations import (
    PolicyGovernedDiscloser,
    ReversiblePseudonymizer,
    StaticSanitizer,
    TaskAwareDiscloser,
    generalization,
)
from adaptive_disclosure_gateway.transformations import (
    reversible_pseudonymization as b2_module,
)
from adaptive_disclosure_gateway.transformations import static_sanitization as b1_module
from adaptive_disclosure_gateway.transformations import task_aware as b3_module
from adaptive_disclosure_gateway.vault import InMemoryVault
from tests.contracts_fixture import (
    AMENDED_DEADLINE,
    BANK_ACCOUNT,
    CONTRACT_VALUE,
    CONTRACTED_PARTY,
    CONTRACTED_PARTY_CNPJ,
    CONTRACTING_PARTY,
    CONTRACTING_PARTY_CNPJ,
    CONTRACTS_BANK_ACCOUNT_FIXTURE,
    CONTRACTS_COREFERENCE_FIXTURE,
    CONTRACTS_FIXTURE,
    CONTRACTS_FIXTURE_SENSITIVE_VALUES,
    FIRST_DEADLINE,
    PENALTY_AMOUNT,
    REPRESENTATIVE,
    REPRESENTATIVE_CPF,
)
from tests.telemetry_assertions import assert_span_attributes_never_leak

POLICY_DIR = Path(__file__).parents[1] / "configs" / "policies"
CONTRACTS_POLICY = POLICY_DIR / "contracts-v1.yaml"

# The frozen Contracts category set, restated here as a literal on purpose.
# Every other assertion in this module derives its category set from the
# YAML; this one pins the YAML itself, so silently adding or dropping a
# category in the freeze artifact fails the build rather than quietly
# widening or narrowing what T24 may rely on.
FROZEN_CONTRACTS_CATEGORIES = frozenset(
    {
        "party_name",
        "representative_name",
        "cnpj",
        "cpf",
        "bank_account",
        "contract_value",
        "penalty_amount",
        "deadline",
    }
)

# The relevance-bearing task used wherever B3/B4 must actually exercise a
# non-default action. Phrased in the domain's own vocabulary, never against
# any expected outcome.
RELATION_TASK = (
    "Summarize which contracting party owes the contract value to which "
    "counterparty, and state the deadline for each obligation."
)


def _policy_rules() -> dict[str, dict]:
    return yaml.safe_load(CONTRACTS_POLICY.read_text(encoding="utf-8"))["rules"]


def _context(**overrides) -> GovernanceContext:
    values = {
        "domain": "contracts",
        "purpose": "contract_review",
        "policy_version": "contracts-v1",
        "request_id": "req-1",
        "document_id": "doc-1",
        "session_id": "sess-1",
    }
    values.update(overrides)
    return GovernanceContext(**values)


def _request(text: str, task: str = RELATION_TASK, **overrides) -> DisclosureRequest:
    return DisclosureRequest(text=text, task=task, context=_context(**overrides))


def _b1():
    return StaticSanitizer()


def _b2():
    return ReversiblePseudonymizer(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )


def _b3():
    return TaskAwareDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )


def _b4():
    return PolicyGovernedDiscloser(
        vault=InMemoryVault(), policy_repository=PolicyRepository.from_directory(POLICY_DIR)
    )


def _run(discloser, text: str, task: str = RELATION_TASK, **overrides):
    request = _request(text, task, **overrides)
    return discloser.sanitize(request, Detector().detect(request.text))


def _value_after(payload: str, label: str) -> list[str]:
    """Every value following ``label`` in ``payload``, one per line.

    The role word is part of the label, never part of the detected value, so
    this is exactly how a reader recovers "which pseudonym plays which role".
    """
    return [
        line.split(":", 1)[1].strip()
        for line in payload.splitlines()
        if line.startswith(f"{label}:")
    ]


# --- 1. Registry consistency across the frozen category set ---------------


def test_contracts_policy_declares_exactly_the_frozen_category_set():
    assert set(_policy_rules()) == set(FROZEN_CONTRACTS_CATEGORIES)


def test_contracts_policy_document_loads_without_error():
    repository = PolicyRepository.from_directory(POLICY_DIR)

    assert "contracts-v1.yaml" not in repository.load_errors


@pytest.mark.parametrize("category", sorted(FROZEN_CONTRACTS_CATEGORIES))
def test_every_frozen_contracts_category_has_a_detection_rule(category):
    detected = {rule.category for rule in BUILT_IN_RULES}

    assert category in detected, (
        f"{category!r} is governed by contracts-v1 but no detection rule can ever "
        "produce it, so the policy rule is dead configuration"
    )


@pytest.mark.parametrize("category", sorted(FROZEN_CONTRACTS_CATEGORIES))
def test_every_frozen_contracts_category_is_wired_into_b1_b2_and_b3(category):
    assert category in b1_module.ACTIONS, f"{category!r} missing from B1 ACTIONS"
    assert category in b2_module.ACTIONS, f"{category!r} missing from B2 ACTIONS"
    assert category in b3_module.TASK_AWARE_ACTION_SPACES, (
        f"{category!r} missing from B3 TASK_AWARE_ACTION_SPACES"
    )


@pytest.mark.parametrize("category", sorted(FROZEN_CONTRACTS_CATEGORIES))
def test_every_frozen_contracts_category_has_task_analyzer_indicators(category):
    # A category with no indicator table always resolves NOT_RELEVANT, which
    # is safe but silently collapses B3 to "least disclosing action, always"
    # -- i.e. the treatment under test stops varying on the one dimension it
    # exists to vary on.
    assert CATEGORY_INDICATORS.get(category), (
        f"{category!r} has no CATEGORY_INDICATORS entry, so B3/B4 can never read it "
        "as task-relevant"
    )


@pytest.mark.parametrize("category", sorted(FROZEN_CONTRACTS_CATEGORIES))
def test_generalize_is_reachable_only_where_a_strategy_is_registered(category):
    """GENERALIZE without a registered strategy is a silent BLOCK_REQUEST.

    Reachability is checked across every path that can select GENERALIZE for
    a category: B1's and B2's static maps, B3's action space, and the
    policy's own ``allowed_actions``/``purpose_actions`` (which B4 minimizes
    inside).
    """
    rule = _policy_rules()[category]
    policy_actions = set(rule.get("allowed_actions") or [])
    for actions in (rule.get("purpose_actions") or {}).values():
        policy_actions.update(actions)

    reachable = (
        b1_module.ACTIONS[category] is DisclosureAction.GENERALIZE
        or b2_module.ACTIONS[category] is DisclosureAction.GENERALIZE
        or DisclosureAction.GENERALIZE in b3_module.TASK_AWARE_ACTION_SPACES[category]
        or DisclosureAction.GENERALIZE.value in policy_actions
    )

    assert reachable == generalization.is_configured(category), (
        f"{category!r}: GENERALIZE reachable={reachable} but a registered strategy "
        f"exists={generalization.is_configured(category)} -- the two must agree or a "
        "GENERALIZE decision silently becomes BLOCK_REQUEST"
    )


# --- 2. Detection on the development fixture ------------------------------


def test_detector_covers_every_contracts_category_in_the_fixture():
    categories = {span.category for span in Detector().detect(CONTRACTS_FIXTURE)}

    assert categories == FROZEN_CONTRACTS_CATEGORIES - {"bank_account"}


def test_detector_finds_both_parties_and_keeps_their_roles_out_of_the_value():
    spans = [s for s in Detector().detect(CONTRACTS_FIXTURE) if s.category == "party_name"]
    values = [span.value for span in spans]

    # Two parties, each appearing twice (contract + amendment).
    assert values.count(CONTRACTING_PARTY) == 2
    assert values.count(CONTRACTED_PARTY) == 2
    # The role word is never inside the detected span -- that is what keeps
    # it in the payload after the identity is pseudonymized away.
    assert all("party" not in value.lower() for value in values)


def test_detector_finds_the_bank_account_value():
    spans = Detector().detect(CONTRACTS_BANK_ACCOUNT_FIXTURE)

    assert BANK_ACCOUNT in {span.value for span in spans if span.category == "bank_account"}


# --- 3. Relation preservation across B1 -> B4 -----------------------------


def test_b1_removes_party_identities_and_with_them_any_way_to_tell_the_parties_apart():
    """B1 -- Static Sanitization has no vault, so a party name can only be
    removed. The roles survive (they are labels), but the two parties become
    indistinguishable from each other: nothing in the payload says the
    ``Contracting party`` of the amendment is the same company as the
    ``Contracting party`` of the contract. This is the documented B1->B2
    utility gap the experiment measures, recorded here as behaviour rather
    than as prose.
    """
    result = _run(_b1(), CONTRACTS_FIXTURE)

    assert result.status == "allowed"
    assert CONTRACTING_PARTY not in result.external_payload
    assert CONTRACTED_PARTY not in result.external_payload
    assert "Contracting party:" in result.external_payload
    assert _value_after(result.external_payload, "Contracting party") == ["", ""]
    assert _value_after(result.external_payload, "Contracted party") == ["", ""]


@pytest.mark.parametrize("make_discloser", [_b2, _b3, _b4])
def test_party_roles_and_obligation_assignment_survive_pseudonymization(make_discloser):
    """The relation Issue #56 asks about -- "who owes what to whom" -- is
    carried by two existing mechanisms, with no new abstraction:

    - the ROLE is in the label, so it is never part of a detected span and
      is never transformed;
    - the IDENTITY is in the value, and the vault issues one *stable*
      pseudonym per original value within a scope, so the same company reads
      as the same pseudonym in the contract and in the amendment, while the
      two companies never collide.

    Together those two facts mean ``Contracting party: PSEUDO-party_name-a``
    ... ``Contracted party: PSEUDO-party_name-b`` preserves the assignment
    exactly. If either mechanism regresses -- a rule that swallows the label
    into the value, or a vault that stops being stable per value -- this
    fails.
    """
    result = _run(make_discloser(), CONTRACTS_FIXTURE)

    assert result.status == "allowed"
    contracting = _value_after(result.external_payload, "Contracting party")
    contracted = _value_after(result.external_payload, "Contracted party")

    assert len(contracting) == 2 and len(contracted) == 2
    # Stability: the same party reads identically in both blocks.
    assert contracting[0] == contracting[1]
    assert contracted[0] == contracted[1]
    # Distinguishability: the two parties never collapse into one reference.
    assert contracting[0] != contracted[0]
    # And neither pseudonym is the original.
    assert contracting[0].startswith("PSEUDO-party_name-")
    assert contracted[0].startswith("PSEUDO-party_name-")


def test_a_representative_is_pseudonymized_independently_of_the_party_it_signs_for():
    """``representative_name`` is a separate category from ``party_name``
    because the two are different legal objects (a contracting party is
    normally a legal entity; a signatory is a natural person, and therefore
    an LGPD data subject). The separation has to be visible in the output,
    not only in the config: the representative gets its own category-tagged
    pseudonym, so an audit trail can say which of the two was disclosed.
    """
    result = _run(_b2(), CONTRACTS_FIXTURE)

    assert REPRESENTATIVE not in result.external_payload
    representative_values = _value_after(result.external_payload, "Representative")
    assert len(representative_values) == 1
    assert representative_values[0].startswith("PSEUDO-representative_name-")


@pytest.mark.parametrize("make_discloser", [_b2, _b3])
def test_pseudonymized_parties_are_reconstructable_back_to_their_roles(make_discloser):
    discloser = make_discloser()
    request = _request(CONTRACTS_FIXTURE)
    result = discloser.sanitize(request, Detector().detect(request.text))

    restored = discloser.reconstruct(result.external_payload, result, request.context)

    assert f"Contracting party: {CONTRACTING_PARTY}" in restored
    assert f"Contracted party: {CONTRACTED_PARTY}" in restored


def test_monetary_amounts_are_banded_not_disclosed():
    result = _run(_b1(), CONTRACTS_FIXTURE)

    assert CONTRACT_VALUE not in result.external_payload
    assert PENALTY_AMOUNT not in result.external_payload
    # Bands are wide enough that the original is only recoverable as "in
    # this range" -- the contract-value band is deliberately far wider than
    # the penalty band, because the quantities differ by orders of magnitude.
    assert "R$ 2400000-2450000" in result.external_payload
    assert "R$ 10000-15000" in result.external_payload


def test_deadlines_are_coarsened_to_month_and_year_by_the_static_baseline():
    result = _run(_b1(), CONTRACTS_FIXTURE)

    assert FIRST_DEADLINE not in result.external_payload
    assert AMENDED_DEADLINE not in result.external_payload
    assert "Deadline: 2026-03" in result.external_payload
    assert "Deadline: 2026-09" in result.external_payload


def test_policy_preserves_the_exact_deadline_where_b3_would_have_coarsened_it():
    """A legal deadline is the one Contracts quantity where coarsening
    destroys the thing the reader needs: "sometime in March" is not a term
    of a contract. ``contracts-v1`` therefore resolves ``deadline`` to a hard
    PRESERVE, which is *more* disclosing than B3's own choice -- a real,
    identifiable B3->B4 cell in the direction policy is allowed to move.
    """
    b3_result = _run(_b3(), CONTRACTS_FIXTURE)
    b4_result = _run(_b4(), CONTRACTS_FIXTURE)

    assert FIRST_DEADLINE not in b3_result.external_payload
    assert FIRST_DEADLINE in b4_result.external_payload


@pytest.mark.parametrize("make_discloser", [_b1, _b2, _b3, _b4])
def test_a_bank_account_blocks_the_whole_request_in_every_treatment(make_discloser):
    result = _run(make_discloser(), CONTRACTS_BANK_ACCOUNT_FIXTURE)

    assert result.status == "blocked"
    assert result.external_payload == ""
    assert BANK_ACCOUNT not in result.external_payload


# --- 4. Documented limitations, pinned ------------------------------------


def test_a_party_named_in_unlabeled_prose_is_not_detected_and_reaches_the_payload():
    """DOCUMENTED LIMITATION, pinned so it stays visible.

    The detector matches labeled lines; it does not resolve coreference. A
    party named again inside ordinary clause prose ("Aurora ... shall pay
    ...") is not a detected span, so it is neither pseudonymized nor removed
    and it reaches the external payload verbatim -- even though the *same*
    company's labeled mention was pseudonymized two lines above.

    This is a real disclosure gap, not a utility gap, and Issue #56
    deliberately does not close it: coreference resolution is far outside
    this ticket. The consequence is a constraint on T24's corpus, recorded
    in ``docs/contracts-policy-matrix.md``: every party mention must sit on
    its own labeled line, or the case must be classified knowing this.

    If a future change does start linking prose mentions, this test fails --
    which is the point: the limitation must not silently stop being
    documented.
    """
    result = _run(_b2(), CONTRACTS_COREFERENCE_FIXTURE)

    assert result.status == "allowed"
    assert f"Contracting party: {CONTRACTING_PARTY}" not in result.external_payload
    assert f"Clause 4: {CONTRACTING_PARTY} shall pay" in result.external_payload


def test_tax_identifiers_reuse_the_existing_cnpj_and_cpf_categories():
    """No ``tax_id`` synonym category exists: a Brazilian company registry
    number is a ``cnpj`` and a natural person's is a ``cpf``, both already
    detected and already wired into every treatment. Inventing a third name
    for the same information type would have produced a category that looks
    governed but is never detected.
    """
    rules = _policy_rules()

    assert "tax_id" not in rules
    assert rules["cnpj"]["default"] == "remove"
    assert rules["cpf"]["default"] == "remove"


# --- 5. Adversarial no-leak checks ----------------------------------------


@pytest.mark.parametrize("make_discloser", [_b1, _b2, _b3, _b4])
def test_no_original_contracts_value_reaches_the_external_payload(make_discloser):
    result = _run(make_discloser(), CONTRACTS_FIXTURE)

    for value in CONTRACTS_FIXTURE_SENSITIVE_VALUES:
        if value == FIRST_DEADLINE or value == AMENDED_DEADLINE:
            # `deadline` is PRESERVE under contracts-v1 by design (see the
            # B3->B4 test above) -- a deliberate, policy-authored
            # disclosure, not a leak. Every other value must be gone.
            continue
        assert value not in result.external_payload, (
            f"{make_discloser.__name__}: {value!r} reached the external payload"
        )


def test_pseudonymizing_a_party_name_is_not_defeated_by_disclosing_its_cnpj():
    """Adversarial: a CNPJ identifies a company far more precisely than its
    name does. Pseudonymizing ``party_name`` while letting the adjacent
    ``CNPJ:`` line through would make the pseudonym decorative -- the reader
    simply looks the number up in a public registry. ``contracts-v1``
    removes it, and B1/B2/B3 never preserve it either.
    """
    for make_discloser in (_b1, _b2, _b3, _b4):
        payload = _run(make_discloser(), CONTRACTS_FIXTURE).external_payload

        assert CONTRACTING_PARTY_CNPJ not in payload, make_discloser.__name__
        assert CONTRACTED_PARTY_CNPJ not in payload, make_discloser.__name__
        assert REPRESENTATIVE_CPF not in payload, make_discloser.__name__


@pytest.mark.parametrize("make_discloser", [_b1, _b2, _b3, _b4])
def test_contracts_telemetry_never_carries_a_value_or_a_pseudonym(make_discloser, recorded_spans):
    result = _run(make_discloser(), CONTRACTS_FIXTURE)

    pseudonyms = [t.transformed for t in result.transformations if t.transformed]
    assert_span_attributes_never_leak(
        recorded_spans.get_finished_spans(),
        *CONTRACTS_FIXTURE_SENSITIVE_VALUES,
        *pseudonyms,
    )


def test_a_contracts_value_that_cannot_be_generalized_blocks_instead_of_being_disclosed(
    recorded_spans,
):
    """Adversarial: the free-text-amount path. A ``Contract value:`` line
    carrying no parseable number cannot be banded. The requirement is that
    it fails closed *and* that the unparseable text never surfaces in the
    payload, in a decision reason, or in telemetry -- the generalization
    strategy's own parse error is raised ``from None`` precisely so a stdlib
    parser cannot echo its input through ``__context__``.
    """
    text = "Contract value: to be agreed between the parties\n"
    result = _run(_b1(), text)

    assert result.status == "blocked"
    assert result.external_payload == ""
    reasons = " ".join(decision.reason for decision in result.decisions)
    assert "to be agreed" not in reasons
    assert_span_attributes_never_leak(
        recorded_spans.get_finished_spans(), "to be agreed between the parties"
    )


# --- 6. Identifiability of the contracts-v1 governance dimensions ---------
#
# The same safeguard `docs/hr-policy-matrix.md` section 2 puts on the HR
# matrix: each dimension this policy claims to vary on must have at least one
# cell where the resolved action genuinely differs with everything else held
# constant. If a future edit flattens one back to a constant, this fails
# rather than the matrix quietly degenerating.

EXACT_CONTRACT_VALUE_TASK = "Report the exact contract value stated in this agreement."
EXACT_PENALTY_TASK = "Report the exact penalty amount stated in this agreement."


def _b4_actions(task: str, purpose: str) -> dict[str, DisclosureAction]:
    result = _run(_b4(), CONTRACTS_FIXTURE, task, purpose=purpose)
    return {decision.category: decision.action for decision in result.decisions}


def test_purpose_changes_the_resolved_action_for_each_monetary_category():
    contract_review = _b4_actions(EXACT_CONTRACT_VALUE_TASK, "contract_review")
    financial_audit = _b4_actions(EXACT_CONTRACT_VALUE_TASK, "financial_audit")

    assert contract_review["contract_value"] is DisclosureAction.GENERALIZE
    assert financial_audit["contract_value"] is DisclosureAction.PRESERVE

    generic = _b4_actions(EXACT_PENALTY_TASK, "contract_review")
    compliance = _b4_actions(EXACT_PENALTY_TASK, "compliance_review")

    assert generic["penalty_amount"] is DisclosureAction.GENERALIZE
    assert compliance["penalty_amount"] is DisclosureAction.PRESERVE


def test_the_two_monetary_purposes_do_not_unlock_each_others_category():
    """`financial_audit` may preserve the contract value but not the penalty,
    and `compliance_review` the reverse. This is what makes the two
    categories worth keeping apart: a single merged "monetary amount"
    category could not express either restriction.
    """
    financial_audit = _b4_actions(EXACT_PENALTY_TASK, "financial_audit")
    compliance = _b4_actions(EXACT_CONTRACT_VALUE_TASK, "compliance_review")

    assert financial_audit["penalty_amount"] is not DisclosureAction.PRESERVE
    assert compliance["contract_value"] is not DisclosureAction.PRESERVE


def test_a_task_about_the_penalty_does_not_also_disclose_the_contract_value():
    """The other half of the same argument, at the task-awareness layer:
    B3 -- Task-aware can serve "what is the penalty regime?" without
    disclosing what the contract is worth, because the two are separate
    categories with separate indicator tables.
    """
    result = _run(_b3(), CONTRACTS_FIXTURE, EXACT_PENALTY_TASK)
    actions = {decision.category: decision.action for decision in result.decisions}

    assert actions["penalty_amount"] is DisclosureAction.PRESERVE
    assert actions["contract_value"] is DisclosureAction.REMOVE
    assert CONTRACT_VALUE not in result.external_payload


def test_policy_restricts_b3_on_the_contract_value_under_a_generic_purpose():
    """A real, recorded B3->B4 restriction: B3 would PRESERVE an exactly
    requested contract value; `contract_review` does not permit PRESERVE, so
    B4 minimizes inside the policy space instead and flags the restriction.
    """
    b3_result = _run(_b3(), CONTRACTS_FIXTURE, EXACT_CONTRACT_VALUE_TASK)
    b3_actions = {d.category: d.action for d in b3_result.decisions}
    assert b3_actions["contract_value"] is DisclosureAction.PRESERVE

    b4_result = _run(_b4(), CONTRACTS_FIXTURE, EXACT_CONTRACT_VALUE_TASK)
    decision = next(d for d in b4_result.decisions if d.category == "contract_value")

    assert decision.action is DisclosureAction.GENERALIZE
    assert decision.policy_restricted is True
    assert decision.impossible_under_policy is True
