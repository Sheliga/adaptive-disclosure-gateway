"""Corpus-level coverage invariants for the frozen HR pilot corpus (T09 /
issue #4, Phase A): size within the approved 12-20 range, all four required
task families present, only the five frozen HR categories used (and all
five actually exercised), and every referenced ``policy_version`` resolves
against ``configs/policies/``.

This test does **not** check detector agreement with the corpus -- ground
truth is independent of the detector (CLAUDE.md), and detector
precision/recall against this corpus is a T10 pilot metric, not a T09
invariant.
"""

from __future__ import annotations

from pathlib import Path

from adaptive_disclosure_gateway.corpus import FROZEN_HR_CATEGORIES, TaskFamily, load_corpus
from adaptive_disclosure_gateway.policies import PolicyRepository

REPO_ROOT = Path(__file__).parents[1]
REAL_CORPUS_DIR = REPO_ROOT / "corpus" / "hr" / "v1" / "cases"
POLICIES_DIR = REPO_ROOT / "configs" / "policies"


def test_corpus_size_is_within_the_approved_range():
    cases = load_corpus(REAL_CORPUS_DIR)
    assert 12 <= len(cases) <= 20, f"expected 12-20 cases, found {len(cases)}"


def test_all_four_required_task_families_are_present():
    cases = load_corpus(REAL_CORPUS_DIR)
    families_present = {case.input.task_family for case in cases}

    assert families_present == set(TaskFamily), (
        f"missing task families: {set(TaskFamily) - families_present}"
    )


def test_only_and_all_five_frozen_categories_are_used():
    cases = load_corpus(REAL_CORPUS_DIR)
    categories_used = {span.category for case in cases for span in case.oracle.expected_spans}

    assert categories_used == set(FROZEN_HR_CATEGORIES), (
        f"expected exactly the five frozen categories, got: {categories_used}"
    )


def test_every_referenced_policy_version_exists_and_loads():
    cases = load_corpus(REAL_CORPUS_DIR)
    repository = PolicyRepository.from_directory(POLICIES_DIR)
    assert not repository.load_errors, f"policy directory failed to load: {repository.load_errors}"

    # PolicyRepository has no public "does this version exist" query, but
    # is_reconstruction_authorized() resolves exactly that -- it is True
    # only if the referenced policy_version loaded and its domain matches
    # the case's domain -- so reusing it here checks corpus/policy
    # consistency through the same public resolution path decide() and
    # resolve_pseudonym_scope() use, instead of reaching into
    # PolicyRepository's private state.
    for case in cases:
        context = case.input.to_disclosure_request().context
        assert repository.is_reconstruction_authorized(context), (
            f"{case.input.sample_id} references policy_version "
            f"{case.input.policy_version!r} / domain {case.input.domain!r}, which does "
            "not resolve against configs/policies/"
        )


def test_medical_block_family_always_expects_block_request():
    cases = load_corpus(REAL_CORPUS_DIR)
    medical_cases = [
        case for case in cases if case.input.task_family is TaskFamily.MEDICAL_OR_PROHIBITED_BLOCK
    ]
    assert medical_cases, "expected at least one medical_or_prohibited_block case"

    for case in medical_cases:
        assert case.oracle.expected_block_request is True, (
            f"{case.input.sample_id} is in the medical/prohibited block family but "
            "does not expect BLOCK_REQUEST"
        )
