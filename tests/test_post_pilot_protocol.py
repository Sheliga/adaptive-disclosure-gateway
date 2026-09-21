"""T23 / issue #36 -- enforcement for the frozen post-pilot protocol.
M3 Gate 6 / issue #38 extended this for the second frozen version,
``post-pilot-v2``; Issue #85 / M3 extended it again for the third,
``post-pilot-v3`` (numeric-band GENERALIZE fidelity); Issue #87 / M3 extends
it again for the fourth, ``post-pilot-v4`` (structured numeric utility
references).

A protocol document is narrative and cannot, by itself, stop three kinds of
silent drift this ticket is specifically about preventing:

1. the protocol id a future run's manifest claims to follow silently
   diverging from the id the *current* frozen document itself declares
   (analogous to this repo's existing UI-copy-vs-wire-schema drift tests,
   applied here to protocol identity instead);
2. an *earlier* frozen document (``post-pilot-v1``, then ``post-pilot-v2``)
   being edited in place once a later version supersedes it as current --
   each superseded document's own front matter and content must stay
   exactly as frozen even though it is no longer ``CURRENT_PROTOCOL_ID``;
3. the M2 binary unnecessary-disclosure metric being silently redefined
   (e.g. to stop counting PSEUDONYMIZE as transmitted) after Issue #36
   required it be preserved, unchanged, as a secondary metric for
   historical continuity -- neither v2 nor v3 touches this metric at all,
   so this pin continues to guard it.

All three are pinned here as real tests that fail from an actual defect: an
unregistered protocol id, a document/code id mismatch, a rewritten v1/v2
document, or a changed unnecessary-disclosure formula would each fail one of
these tests.
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
    SCORABLE_PROTOCOL_IDS,
    UnknownProtocolIdError,
    UnsupportedScoringProtocolError,
    validate_protocol_id,
    validate_scorable_protocol_id,
)
from adaptive_disclosure_gateway.experiments.scoring.unnecessary_disclosure import (
    score_unnecessary_disclosure,
)

PROTOCOL_DOC_V1 = Path(__file__).parents[1] / "docs" / "research" / "post-pilot-protocol-v1.md"
PROTOCOL_DOC_V2 = Path(__file__).parents[1] / "docs" / "research" / "post-pilot-protocol-v2.md"
PROTOCOL_DOC_V3 = Path(__file__).parents[1] / "docs" / "research" / "post-pilot-protocol-v3.md"
PROTOCOL_DOC_V4 = Path(__file__).parents[1] / "docs" / "research" / "post-pilot-protocol-v4.md"
# Backward-compatible alias: PROTOCOL_DOC always names the document this
# module's older assertions target (v1, whose own frozen content never
# changes regardless of which id is CURRENT_PROTOCOL_ID).
PROTOCOL_DOC = PROTOCOL_DOC_V1


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


def test_frozen_v1_document_still_declares_its_own_original_protocol_id():
    """``post-pilot-v1.md`` is never edited once frozen (v1 section 0) --
    including after a later version supersedes it as ``CURRENT_PROTOCOL_ID``.
    This asserts the literal, historical id, never ``CURRENT_PROTOCOL_ID``,
    so that a future v3 bumping ``CURRENT_PROTOCOL_ID`` again can never make
    this test pass by accident merely because the two constants happen to
    match again.
    """
    text = PROTOCOL_DOC_V1.read_text(encoding="utf-8")
    match = re.search(r"^protocol_id:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v1.md must declare protocol_id: <id>"
    assert match.group(1) == "post-pilot-v1"


def test_frozen_v1_document_status_is_still_frozen():
    text = PROTOCOL_DOC_V1.read_text(encoding="utf-8")
    match = re.search(r"^status:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v1.md must declare status: <STATUS>"
    assert match.group(1) == "FROZEN"


def test_frozen_v2_document_still_declares_its_own_original_protocol_id():
    """``post-pilot-v2.md`` is superseded by ``post-pilot-v3`` (Issue #85)
    but, exactly like v1 above, is never edited in place once superseded --
    its own front matter stays the historical record of what governed every
    run produced under it. Asserts the literal, historical id, never
    ``CURRENT_PROTOCOL_ID``, for the same reason the v1 pin does: a future
    v4 moving ``CURRENT_PROTOCOL_ID`` again must never make this test pass
    by accident merely because the two constants happen to match again.
    """
    text = PROTOCOL_DOC_V2.read_text(encoding="utf-8")
    match = re.search(r"^protocol_id:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v2.md must declare protocol_id: <id>"
    assert match.group(1) == "post-pilot-v2"


def test_frozen_v2_document_status_is_still_frozen():
    text = PROTOCOL_DOC_V2.read_text(encoding="utf-8")
    match = re.search(r"^status:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v2.md must declare status: <STATUS>"
    assert match.group(1) == "FROZEN"


def test_frozen_v2_document_still_declares_it_supersedes_v1():
    text = PROTOCOL_DOC_V2.read_text(encoding="utf-8")
    match = re.search(r"^supersedes:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v2.md must declare supersedes: <id>"
    assert match.group(1) == "post-pilot-v1"


def test_frozen_v3_document_still_declares_its_own_original_protocol_id():
    """``post-pilot-v3.md`` is superseded by ``post-pilot-v4`` (Issue #87)
    but, exactly like v1/v2 above, is never edited in place once superseded.
    Asserts the literal, historical id, never ``CURRENT_PROTOCOL_ID``, for
    the same reason the v1/v2 pins do: a future v5 moving
    ``CURRENT_PROTOCOL_ID`` again must never make this test pass by
    accident merely because the two constants happen to match again.
    """
    text = PROTOCOL_DOC_V3.read_text(encoding="utf-8")
    match = re.search(r"^protocol_id:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v3.md must declare protocol_id: <id>"
    assert match.group(1) == "post-pilot-v3"


def test_frozen_v3_document_status_is_still_frozen():
    text = PROTOCOL_DOC_V3.read_text(encoding="utf-8")
    match = re.search(r"^status:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v3.md must declare status: <STATUS>"
    assert match.group(1) == "FROZEN"


def test_frozen_v3_document_still_declares_it_supersedes_v2():
    text = PROTOCOL_DOC_V3.read_text(encoding="utf-8")
    match = re.search(r"^supersedes:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v3.md must declare supersedes: <id>"
    assert match.group(1) == "post-pilot-v2"


def test_current_protocol_document_declares_the_same_protocol_id_as_the_code():
    """The *current* frozen document (v4, since Issue #87) must declare
    exactly ``CURRENT_PROTOCOL_ID`` -- unlike the version-specific tests
    above, this one is meant to keep tracking whichever document is current
    as new versions are frozen in the future.
    """
    text = PROTOCOL_DOC_V4.read_text(encoding="utf-8")
    match = re.search(r"^protocol_id:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v4.md must declare protocol_id: <id>"
    assert match.group(1) == CURRENT_PROTOCOL_ID


def test_current_protocol_document_status_is_frozen():
    text = PROTOCOL_DOC_V4.read_text(encoding="utf-8")
    match = re.search(r"^status:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v4.md must declare status: <STATUS>"
    assert match.group(1) == "FROZEN"


def test_current_protocol_document_declares_it_supersedes_v3():
    text = PROTOCOL_DOC_V4.read_text(encoding="utf-8")
    match = re.search(r"^supersedes:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v4.md must declare supersedes: <id>"
    assert match.group(1) == "post-pilot-v3"


IMPLEMENTATION_STATUS_DOC = Path(__file__).parents[1] / "docs" / "implementation-status.md"


def test_frozen_protocol_date_is_the_frozen_value():
    """Pins v1's own ``frozen_date`` to the immutable value it was corrected
    to (2026-09-11). ``frozen_date`` is immutable by design -- that
    immutability is the freeze itself -- so this test intentionally does NOT
    compare it against anything mutable (e.g. a living status document's own
    "last updated" date): coupling an immutable value to a routinely-changing
    one would fail on every unrelated status edit and make "bump frozen_date
    to match" look like the correct fix, which would silently unfreeze the
    protocol -- precisely what this pin exists to prevent.
    """
    text = PROTOCOL_DOC_V1.read_text(encoding="utf-8")
    match = re.search(r"^frozen_date:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v1.md must declare frozen_date: <DATE>"
    assert match.group(1) == "2026-09-11"


def test_frozen_v2_document_frozen_date_is_the_gate_6_freeze_date():
    """Same immutability pin as above, applied to v2's own frozen_date
    (2026-09-21, the date Gate 6 froze this document). Immutable regardless
    of v2 no longer being ``CURRENT_PROTOCOL_ID``."""
    text = PROTOCOL_DOC_V2.read_text(encoding="utf-8")
    match = re.search(r"^frozen_date:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v2.md must declare frozen_date: <DATE>"
    assert match.group(1) == "2026-09-21"


def test_frozen_v3_document_frozen_date_is_the_issue_85_freeze_date():
    """Same immutability pin as above, applied to v3's own frozen_date
    (2026-09-21, the date Issue #85's fix froze this document)."""
    text = PROTOCOL_DOC_V3.read_text(encoding="utf-8")
    match = re.search(r"^frozen_date:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v3.md must declare frozen_date: <DATE>"
    assert match.group(1) == "2026-09-21"


def test_current_protocol_frozen_date_is_the_issue_87_freeze_date():
    """Same immutability pin as above, applied to v4's own frozen_date
    (2026-09-21, the date Issue #87's fix froze this document)."""
    text = PROTOCOL_DOC_V4.read_text(encoding="utf-8")
    match = re.search(r"^frozen_date:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match is not None, "post-pilot-protocol-v4.md must declare frozen_date: <DATE>"
    assert match.group(1) == "2026-09-21"


def test_all_frozen_protocol_ids_remain_registered_after_v4_supersedes_v3():
    """v1, v2 and v3 are superseded as ``CURRENT_PROTOCOL_ID`` but must
    never be removed from the registry -- each stays the historical record
    of what governed every run produced under it (v1 section 0's own
    append-only rule).
    """
    assert "post-pilot-v1" in FROZEN_PROTOCOL_IDS
    assert "post-pilot-v2" in FROZEN_PROTOCOL_IDS
    assert "post-pilot-v3" in FROZEN_PROTOCOL_IDS
    assert "post-pilot-v4" in FROZEN_PROTOCOL_IDS
    assert CURRENT_PROTOCOL_ID == "post-pilot-v4"


# --- 2b. scorable-protocol registry (Issue #87 / M3) -------------------------


def test_scorable_protocol_ids_are_a_subset_of_frozen_ids():
    assert SCORABLE_PROTOCOL_IDS <= FROZEN_PROTOCOL_IDS


def test_scorable_protocol_ids_are_exactly_v3_and_v4():
    """Pins the concrete membership, not just the subset relationship: v1
    and v2 are frozen historical record but this codebase's scorer no
    longer implements either of them (their numeric-band rule was replaced
    in place by post-pilot-v3's ``classify_generalized_band``)."""
    assert SCORABLE_PROTOCOL_IDS == {"post-pilot-v3", "post-pilot-v4"}


def test_current_protocol_id_is_scorable():
    assert CURRENT_PROTOCOL_ID in SCORABLE_PROTOCOL_IDS


def test_validate_scorable_protocol_id_accepts_v3_and_v4():
    validate_scorable_protocol_id("post-pilot-v3")  # must not raise
    validate_scorable_protocol_id("post-pilot-v4")  # must not raise


def test_validate_scorable_protocol_id_rejects_frozen_but_unscorable_v1_and_v2():
    for protocol_id in ("post-pilot-v1", "post-pilot-v2"):
        with pytest.raises(UnsupportedScoringProtocolError):
            validate_scorable_protocol_id(protocol_id)


def test_validate_scorable_protocol_id_rejects_an_unregistered_id_as_unknown_not_unsupported():
    """An unregistered id must raise ``UnknownProtocolIdError`` -- not
    ``UnsupportedScoringProtocolError`` -- so a caller can tell "this id
    does not exist" apart from "this id exists but has no scorer anymore".
    """
    with pytest.raises(UnknownProtocolIdError):
        validate_scorable_protocol_id("post-pilot-not-a-real-version")


def test_implementation_status_still_references_the_current_protocol_id():
    """Cross-document guard that asserts something actually invariant: the
    living status document (docs/implementation-status.md) must keep citing
    the frozen protocol by its id, so a status rewrite that silently drops
    the reference to the current protocol (e.g. replacing it with an
    unversioned description of the metrics) is caught. Deliberately asserts
    nothing about either document's own date -- a status update's date
    changes routinely and legitimately, while the protocol_id reference
    should not disappear.
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


# --- 4. PR #92 review, blocker 2: grounding wording ------------------------


def test_current_protocol_document_no_longer_claims_no_grounding_requirement():
    """PR #92 review, blocker 2: an earlier draft of the v4 document claimed
    "no grounding requirement" / "no text-grounding" as if dropping the
    *lexical* match requirement meant no grounding constraint existed at
    all. That claim was too strong -- a reference stating a condition
    absent from anything the provider was ever shown would be privileged
    evaluator information used to grant utility. The corrected document
    must never restate either phrase (case-insensitive), and must state
    the semantic-grounding rule that replaces it.
    """
    text = PROTOCOL_DOC_V4.read_text(encoding="utf-8").lower()
    assert "no grounding requirement" not in text
    assert 'no "grounding" requirement' not in text
    assert "no text-grounding" not in text
    assert "semantic grounding" in text
    assert "provider-visible" in text


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
