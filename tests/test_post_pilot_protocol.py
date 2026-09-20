"""T23 / issue #36 -- enforcement for the frozen post-pilot protocol.

A protocol document is narrative and cannot, by itself, stop two kinds of
silent drift this ticket is specifically about preventing:

1. the protocol id a future run's manifest claims to follow silently
   diverging from the id the frozen document itself declares (analogous to
   this repo's existing UI-copy-vs-wire-schema drift tests, applied here to
   protocol identity instead);
2. the M2 binary unnecessary-disclosure metric being silently redefined
   (e.g. to stop counting PSEUDONYMIZE as transmitted) after Issue #36
   required it be preserved, unchanged, as a secondary metric for
   historical continuity.

Both are pinned here as real tests that fail from an actual defect: an
unregistered protocol id, a document/code id mismatch, or a changed
unnecessary-disclosure formula would each fail one of these tests.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from adaptive_disclosure_gateway.corpus.models import ExpectedSpan, TaskNecessity
from adaptive_disclosure_gateway.corpus.oracle import CaseOracle
from adaptive_disclosure_gateway.domain import (
    DisclosureAction,
    DisclosureResult,
    PolicyDecision,
    Transformation,
    Treatment,
)
from adaptive_disclosure_gateway.experiments.post_pilot_protocol import (
    CURRENT_PROTOCOL_ID,
    FROZEN_PROTOCOL_IDS,
    UnknownProtocolIdError,
    validate_protocol_id,
)
from adaptive_disclosure_gateway.experiments.scoring.unnecessary_disclosure import (
    score_unnecessary_disclosure,
)

PROTOCOL_DOC = Path(__file__).parents[1] / "docs" / "research" / "post-pilot-protocol-v1.md"


# --- 1. protocol id registry fails closed ---


def test_current_protocol_id_is_registered_as_frozen():
    assert CURRENT_PROTOCOL_ID in FROZEN_PROTOCOL_IDS


def test_validate_protocol_id_accepts_the_frozen_current_id():
    validate_protocol_id(CURRENT_PROTOCOL_ID)  # must not raise


def test_validate_protocol_id_rejects_an_unregistered_id():
    with pytest.raises(UnknownProtocolIdError):
        validate_protocol_id("post-pilot-v2-not-yet-frozen")


def test_validate_protocol_id_rejects_an_empty_id():
    with pytest.raises(UnknownProtocolIdError):
        validate_protocol_id("")


# --- 2. document <-> code drift guard ---


def test_frozen_protocol_document_declares_the_same_protocol_id_as_the_code():
    text = PROTOCOL_DOC.read_text(encoding="utf-8")
    match = re.search(r"^protocol_id:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v1.md must declare protocol_id: <id>"
    assert match.group(1) == CURRENT_PROTOCOL_ID


def test_frozen_protocol_document_status_is_frozen():
    text = PROTOCOL_DOC.read_text(encoding="utf-8")
    match = re.search(r"^status:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v1.md must declare status: <STATUS>"
    assert match.group(1) == "FROZEN"


IMPLEMENTATION_STATUS_DOC = Path(__file__).parents[1] / "docs" / "implementation-status.md"


def test_frozen_protocol_date_is_the_frozen_value():
    """Pins ``frozen_date`` to the immutable value it was corrected to
    (2026-09-11). ``frozen_date`` is immutable by design -- that immutability
    is the freeze itself -- so this test intentionally does NOT compare it
    against anything mutable (e.g. a living status document's own "last
    updated" date): coupling an immutable value to a routinely-changing one
    would fail on every unrelated status edit and make "bump frozen_date to
    match" look like the correct fix, which would silently unfreeze the
    protocol -- precisely what this pin exists to prevent.
    """
    text = PROTOCOL_DOC.read_text(encoding="utf-8")
    match = re.search(r"^frozen_date:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v1.md must declare frozen_date: <DATE>"
    assert match.group(1) == "2026-09-11"


def test_implementation_status_still_references_the_current_protocol_id():
    """Cross-document guard that asserts something actually invariant: the
    living status document (docs/implementation-status.md) must keep citing
    the frozen protocol by its id, so a status rewrite that silently drops
    the reference to post-pilot-v1 (e.g. replacing it with an unversioned
    description of the metrics) is caught. Deliberately asserts nothing about
    either document's own date -- a status update's date changes routinely
    and legitimately, while the protocol_id reference should not disappear.
    """
    status_text = IMPLEMENTATION_STATUS_DOC.read_text(encoding="utf-8")
    assert CURRENT_PROTOCOL_ID in status_text


# --- 3. the historical binary metric must survive unchanged ---


def _oracle_with_one_not_required_span(expected_actions: list[DisclosureAction]) -> CaseOracle:
    return CaseOracle(
        sample_id="synthetic-binary-metric-pin",
        expected_spans=[
            ExpectedSpan(
                category="employee_name",
                value="Jane Doe",
                start=0,
                end=8,
                task_necessity=TaskNecessity.NOT_REQUIRED,
                expected_actions=expected_actions,
            ),
        ],
        expected_block_request=False,
        expected_answer="unrelated",
        answer_depends_on_categories=[],
    )


def test_binary_unnecessary_disclosure_still_counts_pseudonymize_as_transmitted():
    """Pins Issue #36's required preservation of the M2 binary metric
    (docs/research/post-pilot-protocol-v1.md, section 4.2): PSEUDONYMIZE
    must keep counting as transmitted in the numerator. If this is ever
    "improved" to treat an opaque pseudonym as equivalent to REMOVE, this
    test fails -- exactly the silent redefinition Issue #36 forbids.
    """
    oracle = _oracle_with_one_not_required_span([DisclosureAction.PSEUDONYMIZE])
    result = DisclosureResult(
        external_payload="<pseudonym> ...",
        decisions=[
            PolicyDecision(
                category="employee_name",
                action=DisclosureAction.PSEUDONYMIZE,
                reason="x",
                allowed_actions=[DisclosureAction.PSEUDONYMIZE],
            ),
        ],
        transformations=[
            Transformation(
                category="employee_name",
                original="Jane Doe",
                transformed="person_1",
                action=DisclosureAction.PSEUDONYMIZE,
            ),
        ],
        status="allowed",
    )
    score = score_unnecessary_disclosure(oracle, result, Treatment.REVERSIBLE_PSEUDONYMIZATION)

    assert score.not_required_total == 1
    assert score.not_required_transmitted == 1
    assert score.rate == 1.0


def test_binary_unnecessary_disclosure_still_treats_remove_as_not_transmitted():
    """The other half of the same pin: REMOVE must stay the one action the
    binary metric does not count as transmitted -- otherwise the metric
    could not distinguish any treatment from any other.
    """
    oracle = _oracle_with_one_not_required_span([DisclosureAction.REMOVE])
    result = DisclosureResult(
        external_payload="...",
        decisions=[
            PolicyDecision(
                category="employee_name",
                action=DisclosureAction.REMOVE,
                reason="x",
                allowed_actions=[DisclosureAction.REMOVE],
            ),
        ],
        transformations=[
            Transformation(
                category="employee_name",
                original="Jane Doe",
                transformed=None,
                action=DisclosureAction.REMOVE,
            ),
        ],
        status="allowed",
    )
    score = score_unnecessary_disclosure(oracle, result, Treatment.STATIC_SANITIZATION)

    assert score.not_required_total == 1
    assert score.not_required_transmitted == 0
    assert score.rate == 0.0


def test_binary_unnecessary_disclosure_keeps_blocked_span_in_denominator():
    """A blocked NOT_REQUIRED span remains in the historical denominator.

    This pins why the binary rate is not unconditionally identical to the
    ordinal family's first threshold, whose population contains only spans
    with a scorable exposure level.
    """
    oracle = _oracle_with_one_not_required_span([DisclosureAction.BLOCK_REQUEST])
    result = DisclosureResult(
        external_payload="",
        decisions=[],
        transformations=[],
        status="blocked",
    )

    score = score_unnecessary_disclosure(oracle, result, Treatment.POLICY_GOVERNED)

    assert score.not_required_total == 1
    assert score.not_required_transmitted == 0
    assert score.rate == 0.0
