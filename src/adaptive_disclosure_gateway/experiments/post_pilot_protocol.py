"""Frozen post-pilot protocol identifiers (T23 / issue #36; M3 Gate 6 /
issue #38).

T23 freezes, in ``docs/research/post-pilot-protocol-v1.md``, the
methodological rules a confirmatory B0-B4 batch must follow before its
results may be inspected. This module is the single place that names which
protocol ids are frozen and known -- mirroring how
``run_identity.RunClassification`` is a closed two-value ``Literal`` rather
than a free string, so a typo or an unregistered protocol version cannot
silently pass as valid provenance.

Gate 6 / issue #38 is the first methodological change under that scheme: the
utility scorer's GENERALIZE decidability rule (numeric-band-only) was a type
error when applied to a month-year date, per the audit recorded in
``docs/research/post-pilot-protocol-v2.md``. That document freezes the fix
as ``post-pilot-v2`` -- ``post-pilot-v1`` is never edited to change its
methodological content or removed once frozen (see that document's own
"Versioning" section), it simply stops being ``CURRENT_PROTOCOL_ID``.

Issue #85 / M3 is the second: the numeric-band GENERALIZE path Gate 6
deliberately left unchanged never checked that the band actually contains
the case's own oracle value, so a wrong band could still score
``answerable`` whenever no stated reference figure happened to fall inside
it. ``docs/research/post-pilot-protocol-v3.md`` freezes the fix (fidelity
checked before sufficiency) as ``post-pilot-v3`` -- again, neither
``post-pilot-v1`` nor ``post-pilot-v2`` is edited; ``CURRENT_PROTOCOL_ID``
simply moves forward.

A later methodological change creates a new protocol document
(``docs/research/post-pilot-protocol-vN.md``) with its own id, added to
``FROZEN_PROTOCOL_IDS`` below -- no id already in that set is ever removed
or reassigned to different content.

This module does not interpret the protocol's content and does not compute
any metric -- it only lets runner/manifest code
(``experiments/execution.py``'s ``RunIdentity.protocol_id``,
``experiments/artifacts.py``'s manifest) fail closed against an
unregistered or misspelled id rather than silently accepting one.

``tests/test_post_pilot_protocol.py`` pins, by reading each frozen protocol
document's own front matter, that ``CURRENT_PROTOCOL_ID`` here can never
silently drift from the id the current document declares, that every
earlier frozen document (``post-pilot-v1``) keeps its own original,
immutable front matter, and separately pins that the historical binary
unnecessary-disclosure metric the protocol requires to be preserved
(docs/research/post-pilot-protocol-v1.md, section 4.2) has not been
redefined.
"""

from __future__ import annotations

# Every post-pilot protocol version ever frozen. Append-only: a later
# methodological change adds a new id here (and a new versioned document
# under docs/research/) -- an existing id is never removed or reassigned to
# different content.
FROZEN_PROTOCOL_IDS: frozenset[str] = frozenset({"post-pilot-v1", "post-pilot-v2", "post-pilot-v3"})

# The protocol version currently in force for any run this codebase
# produces. Confirmatory-run tooling records this value in the run's
# provenance (docs/research/post-pilot-protocol-v3.md, section on
# provenance/version boundary; docs/research/post-pilot-protocol-v1.md,
# section 13).
CURRENT_PROTOCOL_ID = "post-pilot-v3"


class UnknownProtocolIdError(ValueError):
    """Raised when a protocol id is not one of the frozen, registered ids."""


def validate_protocol_id(protocol_id: str) -> None:
    """Fail closed if ``protocol_id`` is not a known, frozen protocol version.

    Never accepts an unregistered or misspelled id merely because it looks
    plausible -- mirrors the fail-closed posture ``RunClassification``
    already gives run classification (a closed set, not a free string).
    """
    if protocol_id not in FROZEN_PROTOCOL_IDS:
        raise UnknownProtocolIdError(
            "protocol_id is not one of the frozen, registered post-pilot protocol ids"
        )
