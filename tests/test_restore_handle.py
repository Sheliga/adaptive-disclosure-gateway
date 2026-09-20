"""Adversarial and behavioral tests for the sealed restore handle (T26 /
issue #67, ADR-0002): ``application/restore_handle.py``.

Every test here targets a real defect this mechanism could plausibly have --
CLAUDE.md's no-leak invariant and disclosure-surface rule apply to a restore
handle exactly as they do to any other output boundary: the handle carries
original values forward in time, so it must fail closed on tampering,
truncation, a wrong/rotated key and expiry, must never be a reproducible
digest of its content, must not leak length information finer than its
padding bucket, and must never surface a decrypted value through an
exception message or a span attribute.
"""

from __future__ import annotations

import base64
import re
import traceback

import pytest

from adaptive_disclosure_gateway.application.restore_handle import (
    HANDLE_PREFIX,
    MAX_TTL_SECONDS,
    MIN_SECRET_BYTES,
    IssuedRestoreHandle,
    RestoreHandleConfigurationError,
    RestoreHandleExpiredError,
    RestoreHandleInvalidError,
    RestoreHandleSealer,
    RestoreUnavailableError,
    restore_pseudonyms,
)

SECRET = "a" * MIN_SECRET_BYTES
OTHER_SECRET = "b" * MIN_SECRET_BYTES

ORIGINAL_MARKER = "Aurora Servicos Digitais Ltda -- CONFIDENTIAL ORIGINAL VALUE"
PSEUDONYM = "PSEUDO-party_name-00112233445566778899aabbccddeeff"
OTHER_PSEUDONYM = "PSEUDO-party_name-ffeeddccbbaa99887766554433221100"


class _FrozenClock:
    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _sealer(secret=SECRET, clock=None, **kwargs) -> RestoreHandleSealer:
    return RestoreHandleSealer(
        secret=secret, clock=clock if clock is not None else _FrozenClock(), **kwargs
    )


def _flip_a_ciphertext_byte(handle: str) -> str:
    """Corrupt one byte in the middle of ``handle``'s decoded payload and
    re-encode it.

    Flipping a single character of the base64 *text* is not a reliable
    tamper: base64's final character group can carry bits base64 itself
    never uses (e.g. a 3-character trailing group -- one stripped padding
    slot -- only uses the top 4 of its last character's 6 bits), so some
    single-character edits decode to the exact same bytes and would make an
    adversarial "tampering is rejected" test flaky rather than a reliable
    proof. XOR-ing a full decoded byte away from itself always changes the
    underlying ciphertext, so AES-GCM's tag check is guaranteed to fail.
    """
    prefix, blob = handle.split(".", 1)
    raw = bytearray(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))
    middle = len(raw) // 2
    raw[middle] ^= 0xFF
    tampered_blob = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode("ascii")
    return f"{prefix}.{tampered_blob}"


# --- round trip --------------------------------------------------------------


def test_issue_then_open_round_trips_the_entries():
    sealer = _sealer()
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})

    assert isinstance(issued, IssuedRestoreHandle)
    assert issued.handle.startswith(f"{HANDLE_PREFIX}.")

    entries = sealer.open(issued.handle)
    assert entries == {PSEUDONYM: ORIGINAL_MARKER}


def test_issue_with_no_entries_still_produces_an_openable_handle():
    sealer = _sealer()
    issued = sealer.issue({})
    assert sealer.open(issued.handle) == {}


def test_expires_at_matches_issued_at_plus_ttl():
    sealer = _sealer(ttl_seconds=1234)
    issued = sealer.issue({})
    assert issued.expires_at == int(_FrozenClock().now) + 1234


# --- unavailable (D2: no ephemeral mode) --------------------------------------


def test_unset_secret_refuses_issue_and_open_but_still_constructs():
    sealer = RestoreHandleSealer(secret=None)
    assert sealer.configured is False

    with pytest.raises(RestoreUnavailableError):
        sealer.issue({})
    with pytest.raises(RestoreUnavailableError):
        sealer.open(f"{HANDLE_PREFIX}.whatever")


def test_unavailable_error_names_the_env_var_not_a_value():
    sealer = RestoreHandleSealer(secret=None)
    with pytest.raises(RestoreUnavailableError) as excinfo:
        sealer.issue({"x": "y"})
    assert "ADG_RESTORE_HANDLE_SECRET" in str(excinfo.value)


# --- configuration errors (construction time) ---------------------------------


def test_a_secret_shorter_than_the_minimum_is_rejected_at_construction():
    with pytest.raises(RestoreHandleConfigurationError):
        RestoreHandleSealer(secret="short")


def test_ttl_must_be_positive():
    with pytest.raises(RestoreHandleConfigurationError):
        RestoreHandleSealer(secret=SECRET, ttl_seconds=0)


def test_ttl_must_not_exceed_seven_days():
    with pytest.raises(RestoreHandleConfigurationError):
        RestoreHandleSealer(secret=SECRET, ttl_seconds=MAX_TTL_SECONDS + 1)


def test_ttl_at_the_seven_day_boundary_is_accepted():
    RestoreHandleSealer(secret=SECRET, ttl_seconds=MAX_TTL_SECONDS)


# --- fail-closed opening -------------------------------------------------------


def test_a_tampered_byte_fails_closed_and_reconstructs_nothing():
    sealer = _sealer()
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})
    tampered = _flip_a_ciphertext_byte(issued.handle)

    with pytest.raises(RestoreHandleInvalidError):
        sealer.open(tampered)


def test_a_truncated_handle_fails_closed():
    sealer = _sealer()
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})
    truncated = issued.handle[: len(issued.handle) // 2]

    with pytest.raises(RestoreHandleInvalidError):
        sealer.open(truncated)


def test_a_handle_opened_with_a_different_secret_fails_closed():
    issuer = _sealer(secret=SECRET)
    other = _sealer(secret=OTHER_SECRET)
    issued = issuer.issue({PSEUDONYM: ORIGINAL_MARKER})

    with pytest.raises(RestoreHandleInvalidError):
        other.open(issued.handle)


def test_an_unsupported_version_prefix_fails_closed():
    sealer = _sealer()
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})
    _, blob = issued.handle.split(".", 1)

    with pytest.raises(RestoreHandleInvalidError):
        sealer.open(f"rh99.{blob}")


def test_a_handle_with_no_separator_fails_closed():
    sealer = _sealer()
    with pytest.raises(RestoreHandleInvalidError):
        sealer.open("not-a-handle-at-all")


def test_an_expired_handle_fails_closed_and_reconstructs_nothing():
    clock = _FrozenClock()
    sealer = _sealer(clock=clock, ttl_seconds=10)
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})

    clock.now += 11
    with pytest.raises(RestoreHandleExpiredError):
        sealer.open(issued.handle)


def test_a_handle_still_valid_one_second_before_expiry_opens_successfully():
    clock = _FrozenClock()
    sealer = _sealer(clock=clock, ttl_seconds=10)
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})

    clock.now += 9
    assert sealer.open(issued.handle) == {PSEUDONYM: ORIGINAL_MARKER}


# --- no-leak: encoding, reproducibility, length --------------------------------


def test_raw_decoded_handle_bytes_never_contain_the_original_value():
    sealer = _sealer()
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})
    _, blob = issued.handle.split(".", 1)
    raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))

    assert ORIGINAL_MARKER.encode("utf-8") not in raw
    assert PSEUDONYM.encode("utf-8") not in raw


def test_two_exports_of_identical_content_yield_different_handles():
    sealer = _sealer()
    first = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})
    second = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})

    assert first.handle != second.handle


def test_handles_for_originals_of_different_lengths_in_one_bucket_have_equal_length():
    sealer = _sealer()
    short = sealer.issue({PSEUDONYM: "x"})
    long = sealer.issue({PSEUDONYM: "x" * 50})

    assert len(short.handle) == len(long.handle)


def test_repr_of_the_sealer_never_prints_key_material():
    sealer = _sealer()
    rendered = repr(sealer)
    assert SECRET not in rendered
    assert "key" not in rendered.lower() or "key material" not in rendered.lower()


def test_no_original_pseudonym_or_secret_appears_in_any_open_failure_message_or_chain():
    sealer = _sealer()
    issued = sealer.issue({PSEUDONYM: ORIGINAL_MARKER})
    tampered = _flip_a_ciphertext_byte(issued.handle)

    for attempt, expected_secret in (
        (tampered, SECRET),
        ("rh1.not-valid-base64-at-all!!", SECRET),
    ):
        try:
            sealer.open(attempt)
        except Exception as exc:  # noqa: BLE001 -- inspecting the whole chain deliberately
            rendered = "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            assert ORIGINAL_MARKER not in rendered
            assert PSEUDONYM not in rendered
            assert expected_secret not in rendered
        else:
            pytest.fail("expected an exception")


# --- restore_pseudonyms: cross-scope / unresolved counting ---------------------


def test_restore_pseudonyms_replaces_only_tokens_present_in_the_handle_mapping():
    text = f"See {PSEUDONYM} and {OTHER_PSEUDONYM} in this text."
    restored_text, restored_count, unresolved_count = restore_pseudonyms(
        text, {PSEUDONYM: ORIGINAL_MARKER}
    )

    assert ORIGINAL_MARKER in restored_text
    assert OTHER_PSEUDONYM in restored_text  # left untouched -- no cross-scope oracle
    assert restored_count == 1
    assert unresolved_count == 1


def test_restore_pseudonyms_never_touches_a_pseudonym_absent_from_the_text():
    # The handle knows about a pseudonym that never occurs in the submitted
    # text -- restore must not report it as restored or emit it anywhere.
    restored_text, restored_count, unresolved_count = restore_pseudonyms(
        "Nothing sensitive here.", {PSEUDONYM: ORIGINAL_MARKER}
    )
    assert restored_text == "Nothing sensitive here."
    assert restored_count == 0
    assert unresolved_count == 0


def test_restore_pseudonyms_leaves_non_pseudonym_shaped_text_completely_untouched():
    text = "Ordinary prose with no pseudonym-shaped tokens at all."
    restored_text, restored_count, unresolved_count = restore_pseudonyms(text, {})
    assert restored_text == text
    assert restored_count == 0
    assert unresolved_count == 0


def test_restore_pseudonyms_never_returns_the_mapping_itself():
    # Behavioral guard that the function's return shape cannot carry the
    # mapping wholesale -- only text and two counts.
    result = restore_pseudonyms(f"{PSEUDONYM}", {PSEUDONYM: ORIGINAL_MARKER})
    assert len(result) == 3
    assert isinstance(result[0], str)
    assert isinstance(result[1], int)
    assert isinstance(result[2], int)


def test_pseudonym_token_pattern_does_not_match_unrelated_text():
    from adaptive_disclosure_gateway.application.restore_handle import (
        _PSEUDONYM_TOKEN_PATTERN,
    )

    assert not _PSEUDONYM_TOKEN_PATTERN.search("PSEUDO-party_name-tooshort")
    assert not _PSEUDONYM_TOKEN_PATTERN.search("just some ordinary contract prose")
    assert _PSEUDONYM_TOKEN_PATTERN.search(PSEUDONYM)


def test_pseudonym_token_pattern_is_a_compiled_regex():
    from adaptive_disclosure_gateway.application.restore_handle import (
        _PSEUDONYM_TOKEN_PATTERN,
    )

    assert isinstance(_PSEUDONYM_TOKEN_PATTERN, re.Pattern)
