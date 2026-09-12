"""The server-signed preview confirmation that binds one ``/documents/execute``
to the exact ``/documents/preview`` a reviewer approved (T20 / issue #28's
demo-integration slice; issue #41 gate A).

What these tests exist to catch -- every one of them is a real defect this
mechanism could plausibly have:

- a bound field silently dropped from the fingerprint, so changing it after
  the review no longer invalidates the approval (the parametrized mutation
  test below derives its cases from ``dataclasses.fields``, so a field added
  to the state and forgotten in the fingerprint fails immediately);
- a client-forgeable token: one signed by a different secret, or one whose
  MAC was edited, being accepted;
- an old token reinterpreted under a new fingerprint rule because nothing
  identifies which semantics produced it;
- the token itself becoming a disclosure channel for the document, the task,
  the external payload or the signing secret (CLAUDE.md's no-leak
  invariant -- a token is an output boundary like any other);
- a malformed token being echoed back through the message of the stdlib
  parser that choked on it (``json``'s own ``JSONDecodeError`` embeds the
  document it failed to parse);
- an order-incidental canonicalisation, which would make two logically
  identical states produce two different fingerprints.

Everything here injects its own secret and its own clock. Nothing reads the
environment, so no test depends on a deployment secret being present or
absent.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import traceback

import pytest

from adaptive_disclosure_gateway.application.preview_confirmation import (
    CONFIRMATION_SEMANTICS_VERSION,
    DEFAULT_CONFIRMATION_TTL_SECONDS,
    PreviewConfirmationConfigurationError,
    PreviewConfirmationError,
    PreviewConfirmationSigner,
    PreviewConfirmationState,
    canonical_json,
)

SECRET = "a-test-only-preview-confirmation-secret-value"
OTHER_SECRET = "a-different-test-only-preview-confirmation-secret"

# Marker strings standing in for the three genuinely sensitive inputs. They
# are deliberately distinctive so a substring scan over the token proves
# something.
DOCUMENT_MARKER = "Contracting party: Aurora Servicos Digitais Ltda"
TASK_MARKER = "Summarize the obligations of Aurora Servicos Digitais Ltda"
PAYLOAD_MARKER = "Contracting party: PSEUDO-party_name-0001"


def _state(**overrides) -> PreviewConfirmationState:
    values = {
        "normalized_document": DOCUMENT_MARKER,
        "task": TASK_MARKER,
        "document_type": "contract",
        "analysis_mode": "contract_summary",
        "domain": "contracts",
        "policy_version": "contracts-v1",
        "purpose": "contract_summary",
        "requester_role": "contract_analyst",
        "requested_pseudonym_scope": "request",
        "governance_provider_class": "fake",
        "provider_class": "fake",
        "strategy": "recommended",
        "treatment": "b4",
        "external_payload": PAYLOAD_MARKER,
    }
    values.update(overrides)
    return PreviewConfirmationState(**values)


class _FrozenClock:
    """An injectable clock, so expiry is testable without sleeping."""

    def __init__(self, now: float = 1_700_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _signer(secret: str = SECRET, clock=None, **kwargs) -> PreviewConfirmationSigner:
    return PreviewConfirmationSigner(
        secret=secret, clock=clock if clock is not None else _FrozenClock(), **kwargs
    )


# --- canonicalisation --------------------------------------------------------


def test_canonicalisation_is_key_order_independent():
    """Two logically identical states must produce one fingerprint. A
    ``str(dict)``/insertion-ordered serialization would make the approval
    depend on the order the server happened to build its mapping in.
    """
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert canonical_json({"a": 2, "b": 1}) == '{"a":2,"b":1}'


def test_canonicalisation_uses_compact_separators_and_preserves_non_ascii():
    """``ensure_ascii=True`` would re-encode the same character two ways
    depending on the serializer's configuration; compact separators keep the
    encoding independent of pretty-printing defaults.
    """
    rendered = canonical_json({"purpose": "revisão", "count": 2})

    assert rendered == '{"count":2,"purpose":"revisão"}'
    assert "\\u" not in rendered


def test_canonicalisation_distinguishes_values_that_str_would_collapse():
    assert canonical_json({"a": "1"}) != canonical_json({"a": 1})


# --- issuing and verifying ---------------------------------------------------


def test_a_token_verifies_against_the_state_it_was_issued_for():
    signer = _signer()
    state = _state()

    signer.verify(signer.issue(state), state)


def test_a_token_names_the_semantics_that_produced_it():
    """Without an explicit semantics identifier, a token issued under one
    fingerprint rule could be reinterpreted under a later one.
    """
    token = _signer().issue(_state())

    assert token.split(".")[0] == CONFIRMATION_SEMANTICS_VERSION
    assert CONFIRMATION_SEMANTICS_VERSION == "document-preview-confirmation-v1"


def test_two_tokens_for_the_same_state_verify_interchangeably():
    """Issuing is a pure function of (secret, state, clock) -- it must not
    depend on hidden per-call state, or a second browser tab would break.
    """
    signer = _signer()
    state = _state()

    first = signer.issue(state)
    second = signer.issue(state)

    assert first == second
    signer.verify(second, state)


# --- every bound field actually binds ----------------------------------------

_MUTATIONS = {
    "requester_role": "auditor",
    "requested_pseudonym_scope": "session",
    "strategy": "b0",
    "treatment": "b0",
    "provider_class": "external_llm",
    "governance_provider_class": "external_llm",
    "analysis_mode": "financial_audit",
    "purpose": "financial_audit",
    "document_type": "hr_record",
    "domain": "hr",
    "policy_version": "hr-v1",
}


def _mutated(field_name: str) -> str:
    return _MUTATIONS.get(field_name, f"{field_name}-after-the-review")


@pytest.mark.parametrize(
    "field_name", [field.name for field in dataclasses.fields(PreviewConfirmationState)]
)
def test_changing_any_single_bound_field_invalidates_the_approval(field_name):
    """The central property: an approval authorises exactly one state.

    Parametrized from ``dataclasses.fields`` on purpose -- a field added to
    the state but forgotten in the fingerprint fails here without anyone
    remembering to extend this list.
    """
    signer = _signer()
    approved = _state()
    token = signer.issue(approved)
    executed = dataclasses.replace(approved, **{field_name: _mutated(field_name)})

    assert executed != approved, f"the mutation for {field_name} changed nothing"
    with pytest.raises(PreviewConfirmationError):
        signer.verify(token, executed)


def test_a_token_signed_under_a_different_secret_is_refused():
    """A client cannot mint its own approval, and one deployment's token is
    not valid at another.
    """
    approved = _state()
    token = _signer(secret=OTHER_SECRET).issue(approved)

    with pytest.raises(PreviewConfirmationError):
        _signer().verify(token, approved)


def test_a_client_cannot_recompute_the_fingerprint_from_public_information():
    """The bound content digests are keyed, not public SHA-256: a client that
    knows the document, the task and the payload still cannot produce a
    valid token. A public digest of low-entropy content would also be
    dictionary-reversible (CLAUDE.md).
    """
    import hashlib

    state = _state()
    token = _signer().issue(state)
    public_digests = {
        hashlib.sha256(value.encode("utf-8")).hexdigest()
        for value in (state.normalized_document, state.task, state.external_payload)
    }

    for digest in public_digests:
        assert digest not in token


def test_a_tampered_mac_is_refused():
    signer = _signer()
    state = _state()
    version, claims, mac = signer.issue(state).split(".")
    flipped = ("B" if mac[0] != "B" else "C") + mac[1:]

    with pytest.raises(PreviewConfirmationError):
        signer.verify(f"{version}.{claims}.{flipped}", state)


def test_tampered_claims_are_refused_because_the_mac_covers_them():
    """The validity window is inside the signed document, so extending it
    invalidates the token rather than extending the approval.
    """
    signer = _signer()
    state = _state()
    version, claims, mac = signer.issue(state).split(".")
    decoded = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))
    decoded["expires_at"] += 10_000_000
    forged = base64.urlsafe_b64encode(canonical_json(decoded).encode("utf-8")).rstrip(b"=").decode()

    with pytest.raises(PreviewConfirmationError):
        signer.verify(f"{version}.{forged}.{mac}", state)


def test_a_token_carrying_an_unknown_semantics_version_is_refused():
    signer = _signer()
    state = _state()
    _, claims, mac = signer.issue(state).split(".")

    with pytest.raises(PreviewConfirmationError):
        signer.verify(f"document-preview-confirmation-v2.{claims}.{mac}", state)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-token",
        "a.b",
        "a.b.c.d",
        f"{CONFIRMATION_SEMANTICS_VERSION}.!!!not-base64!!!.abc",
        f"{CONFIRMATION_SEMANTICS_VERSION}.{base64.urlsafe_b64encode(b'not json').decode()}.abc",
    ],
)
def test_a_malformed_token_is_refused(token):
    with pytest.raises(PreviewConfirmationError):
        _signer().verify(token, _state())


# --- expiry ------------------------------------------------------------------


def test_a_token_is_accepted_inside_its_validity_window():
    clock = _FrozenClock()
    signer = _signer(clock=clock, ttl_seconds=900)
    state = _state()
    token = signer.issue(state)

    clock.now += 899

    signer.verify(token, state)


def test_a_token_is_refused_once_its_validity_window_has_passed():
    clock = _FrozenClock()
    signer = _signer(clock=clock, ttl_seconds=900)
    state = _state()
    token = signer.issue(state)

    clock.now += 901

    with pytest.raises(PreviewConfirmationError):
        signer.verify(token, state)


def test_the_default_validity_window_is_short_enough_to_be_a_review_window():
    assert 600 <= DEFAULT_CONFIRMATION_TTL_SECONDS <= 1800


def test_a_non_positive_validity_window_is_refused_at_construction_time():
    with pytest.raises(PreviewConfirmationConfigurationError):
        _signer(ttl_seconds=0)


# --- the token and its errors as a disclosure surface ------------------------


def test_a_token_reveals_neither_the_document_the_task_the_payload_nor_the_secret():
    """A token travels to the browser and back. It is an output boundary,
    so the full no-leak invariant applies to it.
    """
    signer = _signer()
    token = signer.issue(_state())
    decoded_segments = " ".join(
        base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)).decode(
            "utf-8", errors="replace"
        )
        for segment in token.split(".")[1:]
    )
    rendered = f"{token} {decoded_segments}"

    for marker in (DOCUMENT_MARKER, TASK_MARKER, PAYLOAD_MARKER, SECRET):
        assert marker not in rendered
    for fragment in ("Aurora", "PSEUDO", "party_name", "secret"):
        assert fragment not in rendered


def test_the_state_object_renders_no_document_task_or_payload():
    """``PreviewConfirmationState`` is the one place the raw document, task
    and payload sit together. A default dataclass repr would print all three
    into any traceback or log line that touched it.
    """
    rendered = f"{_state()!r} {_state()!s}"

    for marker in (DOCUMENT_MARKER, TASK_MARKER, PAYLOAD_MARKER):
        assert marker not in rendered


def test_the_signer_renders_no_secret():
    rendered = f"{_signer()!r} {_signer()!s}"

    assert SECRET not in rendered


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-token",
        f"{CONFIRMATION_SEMANTICS_VERSION}.{base64.urlsafe_b64encode(DOCUMENT_MARKER.encode()).decode()}.abc",
    ],
)
def test_a_rejection_echoes_neither_the_token_nor_anything_it_carried(token):
    """Checked against a rendered traceback, not only ``str(exc)``: the
    stdlib JSON parser embeds the document it failed to parse in its own
    message, and a chained ``__cause__`` would carry that to any handler
    that renders the exception.
    """
    signer = _signer()

    with pytest.raises(PreviewConfirmationError) as caught:
        signer.verify(token, _state())

    rendered = "".join(
        traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__)
    )

    assert DOCUMENT_MARKER not in rendered
    assert TASK_MARKER not in rendered
    assert PAYLOAD_MARKER not in rendered
    assert SECRET not in rendered
    if token:
        assert token not in rendered


def test_every_rejection_reports_the_same_static_message():
    """Distinct messages per failure mode would be an oracle telling a
    client which half of the approval it got wrong.
    """
    signer = _signer()
    state = _state()
    messages = set()

    for bad_token, bad_state in (
        ("not-a-token", state),
        (_signer(secret=OTHER_SECRET).issue(state), state),
        (signer.issue(state), dataclasses.replace(state, strategy="b0")),
        (f"document-preview-confirmation-v2.{signer.issue(state).split('.', 1)[1]}", state),
    ):
        with pytest.raises(PreviewConfirmationError) as caught:
            signer.verify(bad_token, bad_state)
        messages.add(str(caught.value))

    assert len(messages) == 1
    assert "invalid or no longer matches" in messages.pop()


# --- secret configuration ----------------------------------------------------


def test_a_secret_too_short_to_key_an_hmac_is_refused_at_construction_time():
    with pytest.raises(PreviewConfirmationConfigurationError):
        PreviewConfirmationSigner(secret="short")


def test_the_construction_error_never_echoes_the_rejected_secret():
    with pytest.raises(PreviewConfirmationConfigurationError) as caught:
        PreviewConfirmationSigner(secret="short-but-distinctive-marker")

    assert "short-but-distinctive-marker" not in str(caught.value)


def test_an_ephemeral_signer_still_enforces_confirmation():
    """The development default generates key material rather than disabling
    confirmation -- the same shape ``audit.py`` already uses. A signer that
    accepted anything would be the silent fallback this must never have.
    """
    signer = PreviewConfirmationSigner.with_ephemeral_secret(clock=_FrozenClock())
    state = _state()

    signer.verify(signer.issue(state), state)
    with pytest.raises(PreviewConfirmationError):
        signer.verify(signer.issue(state), dataclasses.replace(state, strategy="b0"))


def test_two_ephemeral_signers_do_not_honour_each_others_tokens():
    state = _state()
    issuing = PreviewConfirmationSigner.with_ephemeral_secret(clock=_FrozenClock())
    verifying = PreviewConfirmationSigner.with_ephemeral_secret(clock=_FrozenClock())

    with pytest.raises(PreviewConfirmationError):
        verifying.verify(issuing.issue(state), state)
