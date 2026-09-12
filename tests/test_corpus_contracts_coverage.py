"""Corpus-level invariants for the frozen Contracts v1 corpus (T24 / issue #37).

The Contracts counterpart of ``tests/test_corpus_coverage.py``,
``tests/test_corpus_span_consistency.py``,
``tests/test_corpus_task_necessity_coherence.py``,
``tests/test_corpus_answer_grounded_in_input.py`` and
``tests/test_corpus_necessity_discrimination.py``, kept in one file because
the Contracts corpus is one artifact with one freeze rule.

Like its HR counterparts, this file deliberately does **not** check detector
agreement with the corpus: ground truth is independent of the detector
(CLAUDE.md), and detector precision/recall against a corpus is a runner
metric, not a corpus invariant.

What it *does* check that the HR files cannot: that
``FROZEN_CONTRACTS_CATEGORIES`` -- the corpus schema's mirror of the Issue #56
freeze -- has not drifted from the live detector/policy/treatment registries
that freeze actually lives in. A corpus annotating a category the detector no
longer emits, or missing one it does, would silently score against a
vocabulary nothing implements.
"""

from __future__ import annotations

import re
from collections import Counter
from itertools import pairwise
from pathlib import Path

import yaml

from adaptive_disclosure_gateway.corpus import (
    FROZEN_CONTRACTS_CATEGORIES,
    ContractsTaskFamily,
    TaskNecessity,
    load_corpus,
)
from adaptive_disclosure_gateway.detection.rules import LABELED_CONTRACTS_RULES
from adaptive_disclosure_gateway.domain import SensitiveSpan
from adaptive_disclosure_gateway.policies import PolicyRepository
from adaptive_disclosure_gateway.transformations import (
    reversible_pseudonymization,
    static_sanitization,
)
from adaptive_disclosure_gateway.transformations.span_validation import spans_are_valid
from adaptive_disclosure_gateway.transformations.task_aware import TASK_AWARE_ACTION_SPACES

REPO_ROOT = Path(__file__).parents[1]
CORPUS_DIR = REPO_ROOT / "corpus" / "contracts" / "v1" / "cases"
POLICIES_DIR = REPO_ROOT / "configs" / "policies"
CONTRACTS_POLICY = POLICIES_DIR / "contracts-v1.yaml"

# The two structured identifier categories Issue #56 reused unchanged rather
# than duplicating under a `tax_id` synonym. They are matched by pattern, not
# by a Contracts label, so they are not in LABELED_CONTRACTS_RULES.
REUSED_STRUCTURED_CATEGORIES = frozenset({"cnpj", "cpf"})

# Categories permitted to be `not_required` in every one of their
# occurrences. Same documented-exemption mechanism as
# tests/test_corpus_necessity_discrimination.py, with Contracts reasons:
#
# - `cnpj`/`cpf`: a registry number is never what a contract task needs; it
#   identifies a party more precisely than its name does, which is exactly
#   why `contracts-v1` REMOVEs both. Forcing a `required` occurrence would be
#   an artificial, unfalsifiable annotation.
# - `bank_account`: it only ever appears in a case that must BLOCK_REQUEST --
#   the category exists to stop a request, not to serve one -- so a
#   `required` bank account is a case that cannot exist under this policy.
#
# No other category is exempt: party_name, representative_name,
# contract_value, penalty_amount and deadline must each discriminate.
DISCRIMINATION_EXEMPT_CATEGORIES = frozenset({"cnpj", "cpf", "bank_account"})

_MONEY_PATTERN = re.compile(r"R\$\s?\d+(?:\.\d+)?")


def _cases():
    cases = load_corpus(CORPUS_DIR)
    assert cases, "expected at least one Contracts corpus case"
    return cases


def _money_amounts(text: str) -> set[str]:
    return {re.sub(r"\s+", " ", match).strip() for match in _MONEY_PATTERN.findall(text)}


# --- freeze/drift guards -----------------------------------------------------


def test_frozen_contracts_categories_match_the_detector_registry():
    labeled = {rule.category for rule in LABELED_CONTRACTS_RULES}

    assert set(FROZEN_CONTRACTS_CATEGORIES) == labeled | REUSED_STRUCTURED_CATEGORIES


def test_frozen_contracts_categories_match_the_contracts_v1_policy_document():
    document = yaml.safe_load(CONTRACTS_POLICY.read_text(encoding="utf-8"))

    assert document["version"] == "contracts-v1"
    assert document["domain"] == "contracts"
    assert set(document["rules"]) == set(FROZEN_CONTRACTS_CATEGORIES)


def test_every_frozen_contracts_category_is_wired_into_every_treatment_registry():
    missing = []
    for category in FROZEN_CONTRACTS_CATEGORIES:
        if category not in static_sanitization.ACTIONS:
            missing.append(f"{category}: absent from B1 ACTIONS")
        if category not in reversible_pseudonymization.ACTIONS:
            missing.append(f"{category}: absent from B2 ACTIONS")
        if category not in TASK_AWARE_ACTION_SPACES:
            missing.append(f"{category}: absent from TASK_AWARE_ACTION_SPACES")

    assert not missing, (
        "the corpus schema's Contracts category set has drifted from the "
        f"treatment registries Issue #56 froze: {missing}"
    )


# --- corpus composition ------------------------------------------------------


def test_corpus_size_is_within_the_approved_range():
    cases = _cases()
    assert 12 <= len(cases) <= 20, f"expected 12-20 cases, found {len(cases)}"


def test_all_six_contracts_task_families_are_present():
    families = {case.input.task_family for case in _cases()}

    assert families == set(ContractsTaskFamily), (
        f"missing task families: {set(ContractsTaskFamily) - families}"
    )


def test_only_and_all_eight_frozen_contracts_categories_are_used():
    categories = {span.category for case in _cases() for span in case.oracle.expected_spans}

    assert categories == set(FROZEN_CONTRACTS_CATEGORIES), (
        f"expected exactly the eight frozen Contracts categories, got: {categories}"
    )


def test_every_case_declares_the_contracts_domain_and_the_frozen_policy_version():
    for case in _cases():
        assert case.input.domain == "contracts"
        assert case.input.policy_version == "contracts-v1"


def test_every_referenced_policy_version_exists_and_loads():
    repository = PolicyRepository.from_directory(POLICIES_DIR)
    assert not repository.load_errors, f"policy directory failed to load: {repository.load_errors}"

    for case in _cases():
        context = case.input.to_disclosure_request().context
        assert repository.is_reconstruction_authorized(context), (
            f"{case.input.sample_id} references policy_version "
            f"{case.input.policy_version!r} / domain {case.input.domain!r}, which does "
            "not resolve against configs/policies/"
        )


def test_payment_details_block_family_always_expects_block_request():
    blocked = [
        case
        for case in _cases()
        if case.input.task_family is ContractsTaskFamily.PAYMENT_DETAILS_BLOCK
    ]
    assert blocked, "expected at least one payment_details_block case"

    for case in blocked:
        assert case.oracle.expected_block_request is True, (
            f"{case.input.sample_id} is in the payment_details_block family but "
            "does not expect BLOCK_REQUEST"
        )


def test_every_case_containing_a_bank_account_span_expects_a_block():
    """Stronger than the family check above, and independent of it: the
    ``bank_account`` category is BLOCK_REQUEST in every treatment and in
    ``contracts-v1``, so a case annotating one and *not* expecting a block
    would be internally incoherent regardless of which family it declares.
    """
    for case in _cases():
        has_account = any(span.category == "bank_account" for span in case.oracle.expected_spans)
        if has_account:
            assert case.oracle.expected_block_request is True, (
                f"{case.input.sample_id} annotates a bank_account span but does not "
                "expect BLOCK_REQUEST"
            )


def test_the_corpus_varies_purpose_so_the_one_active_governance_dimension_is_exercised():
    """``purpose`` is the only ``GovernanceContext`` dimension ``contracts-v1``
    actually reads (docs/contracts-policy-matrix.md's governance table), and
    it only produces an effect for ``contract_value`` (``financial_audit``)
    and ``penalty_amount`` (``compliance_review``). A corpus that never
    varied it could not observe a single B3->B4 policy effect.
    """
    purposes = {case.input.purpose for case in _cases()}

    assert "financial_audit" in purposes
    assert "compliance_review" in purposes
    assert len(purposes) >= 3, f"expected the corpus to vary purpose, got {sorted(purposes)}"


# --- span/offset self-consistency -------------------------------------------


def test_every_case_has_offsets_valid_against_its_own_text():
    failures = []
    for case in _cases():
        spans = [
            SensitiveSpan(category=span.category, value=span.value, start=span.start, end=span.end)
            for span in case.oracle.expected_spans
        ]
        if not spans_are_valid(spans, case.input.text):
            failures.append(case.input.sample_id)

    assert not failures, f"Contracts cases with inconsistent span offsets: {failures}"


def test_no_two_spans_in_a_case_overlap():
    """A real annotation defect this corpus is more exposed to than HR's: a
    ``Contract value:`` line and a ``Penalty:`` line both carry ``R$ ...``
    amounts, so a copied offset would produce two spans claiming the same
    text.
    """
    failures = []
    for case in _cases():
        ordered = sorted(case.oracle.expected_spans, key=lambda span: span.start)
        for earlier, later in pairwise(ordered):
            if later.start < earlier.end:
                failures.append(f"{case.input.sample_id}: {earlier.category}/{later.category}")

    assert not failures, f"overlapping annotated spans: {failures}"


# --- oracle coherence --------------------------------------------------------


def test_required_categories_match_answer_depends_on_categories_for_every_non_blocked_case():
    non_blocked = [case for case in _cases() if not case.oracle.expected_block_request]
    assert non_blocked, "expected at least one non-blocked Contracts case"

    mismatches = []
    for case in non_blocked:
        required = {
            span.category
            for span in case.oracle.expected_spans
            if span.task_necessity is TaskNecessity.REQUIRED
        }
        declared = set(case.oracle.answer_depends_on_categories or [])
        if required != declared:
            mismatches.append(
                f"{case.input.sample_id}: required={sorted(required)} "
                f"answer_depends_on_categories={sorted(declared)}"
            )

    assert not mismatches, (
        f"task_necessity=required spans do not match answer_depends_on_categories: {mismatches}"
    )


def test_blocked_cases_never_declare_an_answer_or_a_relation():
    blocked = [case for case in _cases() if case.oracle.expected_block_request]
    assert blocked, "expected at least one blocked Contracts case"

    for case in blocked:
        assert case.oracle.expected_answer is None
        assert case.oracle.answer_depends_on_categories is None
        assert case.oracle.reconstruction == []
        assert case.oracle.obligation_relations == []


def test_every_expected_answer_monetary_amount_appears_verbatim_in_input_text():
    failures = []
    for case in _cases():
        if case.oracle.expected_answer is None:
            continue
        missing = _money_amounts(case.oracle.expected_answer) - _money_amounts(case.input.text)
        if missing:
            failures.append(f"{case.input.sample_id}: {sorted(missing)}")

    assert not failures, (
        "expected_answer cites monetary figures absent from input.text -- the "
        "utility oracle would then depend on a reference not derivable from the "
        f"common B0-B4 input: {failures}"
    )


def test_every_expected_answer_date_appears_verbatim_in_input_text():
    """The Contracts analogue of the monetary-grounding check above. A
    deadline is this domain's second kind of citable reference figure, and an
    answer citing a date the input never states would be just as ungrounded
    as one citing an invented band boundary.
    """
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    failures = []
    for case in _cases():
        if case.oracle.expected_answer is None:
            continue
        missing = set(date_pattern.findall(case.oracle.expected_answer)) - set(
            date_pattern.findall(case.input.text)
        )
        if missing:
            failures.append(f"{case.input.sample_id}: {sorted(missing)}")

    assert not failures, f"expected_answer cites dates absent from input.text: {failures}"


def test_grounding_checkers_reject_a_figure_the_input_never_states():
    """Not a check on the real corpus: pins that the extraction/containment
    helpers above actually reject an ungrounded citation, so a passing
    corpus-wide check means something.
    """
    text = "Contract value: R$ 940000.00\nDeadline: 2026-11-30\n"
    answer = "The value (R$ 940000.00) exceeds the R$ 500000.00 floor, due 2026-12-31."

    assert _money_amounts(answer) - _money_amounts(text) == {"R$ 500000.00"}
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    assert set(date_pattern.findall(answer)) - set(date_pattern.findall(text)) == {"2026-12-31"}


def test_every_non_exempt_category_has_at_least_one_required_and_one_not_required_span():
    required_counts: Counter[str] = Counter()
    not_required_counts: Counter[str] = Counter()
    categories_seen: set[str] = set()

    for case in _cases():
        for span in case.oracle.expected_spans:
            categories_seen.add(span.category)
            if span.task_necessity is TaskNecessity.REQUIRED:
                required_counts[span.category] += 1
            else:
                not_required_counts[span.category] += 1

    non_exempt = categories_seen - DISCRIMINATION_EXEMPT_CATEGORIES
    assert non_exempt, "expected at least one non-exempt category to check"

    failures = [
        f"{category}: required={required_counts[category]} "
        f"not_required={not_required_counts[category]}"
        for category in sorted(non_exempt)
        if required_counts[category] == 0 or not_required_counts[category] == 0
    ]

    assert not failures, (
        "category never discriminates task_necessity across the Contracts corpus "
        "(a constant-suppression or constant-preserve strategy would satisfy it "
        "perfectly, so it cannot distinguish real task-awareness from blind "
        "action on this category): " + "; ".join(failures)
    )


def test_the_exemption_set_is_actually_exercised_and_not_merely_declared():
    """A documented exemption that no case triggers is dead weight that
    silently widens the invariant above. Each exempt category must really be
    present in the corpus and really be ``not_required`` throughout -- the
    moment one of them becomes task-necessary somewhere, the exemption must
    be re-argued rather than kept out of habit.
    """
    seen: dict[str, set[str]] = {}
    for case in _cases():
        for span in case.oracle.expected_spans:
            if span.category in DISCRIMINATION_EXEMPT_CATEGORIES:
                seen.setdefault(span.category, set()).add(span.task_necessity.value)

    assert set(seen) == set(DISCRIMINATION_EXEMPT_CATEGORIES), (
        f"exempt categories never annotated in the corpus: "
        f"{set(DISCRIMINATION_EXEMPT_CATEGORIES) - set(seen)}"
    )
    for category, necessities in sorted(seen.items()):
        assert necessities == {"not_required"}, (
            f"{category} is on the discrimination exemption list but is annotated "
            f"{sorted(necessities)} -- re-argue the exemption or remove it"
        )
