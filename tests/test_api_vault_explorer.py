"""T29 / issue #72: the HTTP surface of the demo vault explorer
(``ADG_ENABLE_DEMO_VAULT_EXPLORER`` / ``DisclosureApplicationService``'s
``demo_vault_explorer_enabled``) -- ``PreviewResponse.vault_explorer_token``
and ``POST /demo/vault-explorer``.

Mirrors ``tests/test_api_demo_transparency.py``'s structure and adversarial
sections (span attributes, cross-request isolation, raw HTTP response text)
per CLAUDE.md's no-leak invariant: a change touching sensitive data needs an
adversarial test asking whether a sensitive value can escape through an
alternative path, not just whether the immediate field under test looks
clean.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from adaptive_disclosure_gateway.application.presets import CONTRACT_DOCUMENT_TYPE
from adaptive_disclosure_gateway.vault import InMemoryVault
from tests import telemetry_assertions
from tests.api_support import HR_TEXT, RecordingProvider, build_client, build_service
from tests.test_application_document_presets import StubContractParser

_assert_span_attributes_never_leak = telemetry_assertions.assert_span_attributes_never_leak

SENSITIVE_NAME = "Ana Souza"
SENSITIVE_CPF = "123.456.789-09"
OTHER_NAME = "Carlos Lima"
OTHER_TEXT = f"Employee: {OTHER_NAME}\nCPF: 987.654.321-00\nDepartment: Finance\n"

CONTRACT_TASK = "Summarize the obligations of each party and the deadlines."


@dataclass
class _SpyVault(InMemoryVault):
    reconstruct_calls: list = field(default_factory=list)

    def reconstruct(self, scope, scope_key, pseudonym):
        self.reconstruct_calls.append((scope, scope_key, pseudonym))
        return super().reconstruct(scope, scope_key, pseudonym)


def _preview(client, text=HR_TEXT, strategy="b2", **governance):
    body = {"text": text, "task": "summarize", "strategy": strategy}
    if governance:
        body["governance"] = governance
    return client.post("/disclosure/preview", json=body)


def _explore(client, token):
    return client.post("/demo/vault-explorer", json={"token": token})


# --- default (flag off) vs. enabled --------------------------------------------


def test_vault_explorer_token_is_null_when_flag_is_disabled():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=False))

    response = _preview(client)

    assert response.status_code == 200
    body = response.json()
    assert "vault_explorer_token" in body
    assert body["vault_explorer_token"] is None


def test_documents_preview_vault_explorer_token_is_null_when_disabled():
    service = build_service(
        RecordingProvider(),
        demo_vault_explorer_enabled=False,
        examples_directory=None,
        domain="contracts",
        policy_version="contracts-v1",
    )
    from adaptive_disclosure_gateway.application.service import DisclosureApplicationService

    service = DisclosureApplicationService(
        policy_repository=service._policy_repository,
        provider=service._provider,
        default_context=service._default_context,
        document_parser=StubContractParser(),
        demo_vault_explorer_enabled=False,
    )
    client = build_client(service)

    response = client.post(
        "/documents/preview",
        files={"file": ("contract.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
        data={"task": CONTRACT_TASK, "document_type": CONTRACT_DOCUMENT_TYPE},
    )

    assert response.status_code == 200
    assert response.json()["vault_explorer_token"] is None


def test_route_is_404_with_fixed_body_and_no_store_headers_when_disabled_and_vault_untouched():
    vault = _SpyVault()
    service = build_service(RecordingProvider(), demo_vault_explorer_enabled=False, vault=vault)
    client = build_client(service)

    response = _explore(client, "vx1.anything")

    assert response.status_code == 404
    assert response.json() == {"detail": "not found", "kind": "DemoVaultExplorerDisabled"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert vault.reconstruct_calls == []


def test_health_and_ready_are_unaffected_by_the_vault_explorer_flag():
    from adaptive_disclosure_gateway.providers import FakeProvider

    disabled = build_client(build_service(FakeProvider(), demo_vault_explorer_enabled=False))
    enabled = build_client(build_service(FakeProvider(), demo_vault_explorer_enabled=True))

    assert disabled.get("/health").json() == enabled.get("/health").json()
    disabled_ready = disabled.get("/ready")
    enabled_ready = enabled.get("/ready")
    assert disabled_ready.status_code == enabled_ready.status_code == 200
    assert disabled_ready.json() == enabled_ready.json()


# --- flag on: behavioral ---------------------------------------------------------


def test_explore_returns_exactly_pseudonymize_entries_for_b2():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    preview = _preview(client, strategy="b2")
    token = preview.json()["vault_explorer_token"]
    assert token is not None

    response = _explore(client, token)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["scope"] == "session"
    categories = {e["category"] for e in body["entries"]}
    assert categories == {"employee_name", "cpf"}
    employee = next(e for e in body["entries"] if e["category"] == "employee_name")
    assert employee["original"] == SENSITIVE_NAME
    assert employee["present"] is True
    assert set(employee) == {"category", "pseudonym", "original", "present"}
    assert body["entry_count"] == len(body["entries"])
    assert set(body) == {"contract_version", "scope", "entry_count", "entries"}

    # GENERALIZE (salary)/PRESERVE (department) never appear.
    assert "salary" not in categories
    assert "department" not in categories


def test_explore_has_null_scope_and_no_entries_for_b1_and_b0():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    for strategy in ("b1", "b0"):
        preview = _preview(client, strategy=strategy)
        token = preview.json()["vault_explorer_token"]
        assert token is not None
        response = _explore(client, token)
        body = response.json()
        assert body["scope"] is None
        assert body["entries"] == []
        assert body["entry_count"] == 0


def test_blocked_decision_never_issues_a_token():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))
    text = HR_TEXT + "Medical notes: Reports chronic migraine.\n"

    preview = _preview(client, text=text, strategy="b2")

    assert preview.json()["summary"]["status"] == "blocked"
    assert preview.json()["vault_explorer_token"] is None


def test_organization_scope_never_issues_a_token():
    client = build_client(
        build_service(
            RecordingProvider(), demo_vault_explorer_enabled=True, requester_role="hr_admin"
        )
    )

    preview = _preview(client, strategy="b2", requested_pseudonym_scope="organization")

    assert preview.json()["vault_explorer_token"] is None


# --- validation / malformed body -------------------------------------------------


def test_invalid_json_body_is_422():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    response = client.post("/demo/vault-explorer", json={"unexpected": "field"})

    assert response.status_code == 422


def test_missing_token_field_is_422():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    response = client.post("/demo/vault-explorer", json={})

    assert response.status_code == 422


# --- tamper / forgery / cross-process rejection ----------------------------------


def test_forged_and_malformed_tokens_are_400_with_fixed_body():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))
    preview = _preview(client, strategy="b2")
    token = preview.json()["vault_explorer_token"]

    prefix, blob = token.split(".", 1)
    tampered = f"{prefix}.{blob[:-4]}zzzz"

    candidates = [
        tampered,
        "",
        "garbage",
        "zz9." + blob,
        token[:-10],
        "vx1." + ("A" * 40),
    ]
    for candidate in candidates:
        response = _explore(client, candidate)
        assert response.status_code == 400, candidate
        body = response.json()
        assert body == {
            "detail": (
                "vault explorer reference is invalid, malformed, expired, or was not issued "
                "by this process"
            ),
            "kind": "VaultExplorerReferenceError",
        }
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        assert SENSITIVE_NAME not in response.text
        assert token not in response.text


def test_token_from_a_different_service_instance_is_400():
    """Simulates a restart: a second, independently-built service (its own
    fresh ``VaultExplorerSealer`` with its own random key) must reject a
    token issued by the first.
    """
    client_a = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))
    client_b = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    preview = _preview(client_a, strategy="b2")
    token = preview.json()["vault_explorer_token"]

    response = _explore(client_b, token)
    assert response.status_code == 400


# --- isolation between two references on one shared service ----------------------


def test_two_interleaved_tokens_each_see_only_their_own_entries():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    preview_a = _preview(client, text=HR_TEXT, strategy="b2")
    token_a = preview_a.json()["vault_explorer_token"]

    preview_b = _preview(client, text=OTHER_TEXT, strategy="b2")
    token_b = preview_b.json()["vault_explorer_token"]

    assert token_a != token_b

    view_a = _explore(client, token_a).json()
    view_b = _explore(client, token_b).json()

    originals_a = [e["original"] for e in view_a["entries"]]
    originals_b = [e["original"] for e in view_b["entries"]]
    assert SENSITIVE_NAME in originals_a
    assert OTHER_NAME in originals_b
    assert OTHER_NAME not in originals_a
    assert SENSITIVE_NAME not in originals_b


def test_concurrent_explore_requests_are_isolated():
    from concurrent.futures import ThreadPoolExecutor

    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    pairs = []
    for i in range(6):
        text = f"Employee: Person-{i}\nCPF: 000.000.000-0{i}\nDepartment: Eng\n"
        preview = _preview(client, text=text, strategy="b2")
        token = preview.json()["vault_explorer_token"]
        pairs.append((token, f"Person-{i}"))

    def _check(pair):
        token, expected_name = pair
        body = _explore(client, token).json()
        employee = next(e for e in body["entries"] if e["category"] == "employee_name")
        return employee["original"] == expected_name

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(_check, pairs))

    assert all(results)


# --- adversarial: no mapping travels between requests ----------------------------


def test_no_mapping_travels_between_two_previews_on_a_shared_service_instance():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    first = _preview(client, text=OTHER_TEXT, strategy="b2")
    first_token = first.json()["vault_explorer_token"]
    first_view = _explore(client, first_token).json()
    other_pseudonym = next(
        e["pseudonym"] for e in first_view["entries"] if e["category"] == "employee_name"
    )

    second = _preview(client, text=HR_TEXT, strategy="b2")
    assert OTHER_NAME not in second.text
    assert other_pseudonym not in second.text
    second_token = second.json()["vault_explorer_token"]
    second_view = _explore(client, second_token)
    raw = second_view.text
    assert OTHER_NAME not in raw
    assert other_pseudonym not in raw


def test_vault_explorer_span_attributes_never_leak_sensitive_values(recorded_spans):
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    preview = _preview(client, strategy="b2")
    token = preview.json()["vault_explorer_token"]
    explore = _explore(client, token)
    pseudonym = next(
        e["pseudonym"] for e in explore.json()["entries"] if e["category"] == "employee_name"
    )

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished, SENSITIVE_NAME, SENSITIVE_CPF, "8500", HR_TEXT, pseudonym, token
    )


# --- no-store headers are scoped to the vault explorer path only -----------------


def test_413_on_vault_explorer_still_carries_no_store_headers():
    """The no-store headers must be applied by a middleware that sits
    outside ``RequestBodySizeLimitMiddleware`` on this path -- a 413
    produced upstream of the route handler must still be uncacheable.
    """
    client = build_client(
        build_service(RecordingProvider(), demo_vault_explorer_enabled=True),
        max_upload_bytes=8,
    )

    response = _explore(client, "vx1." + ("A" * 40))

    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_unrelated_route_carries_no_no_store_header():
    client = build_client(build_service(RecordingProvider(), demo_vault_explorer_enabled=True))

    response = client.get("/health")

    assert response.status_code == 200
    assert "cache-control" not in response.headers
    assert "pragma" not in response.headers


def test_no_leak_across_preview_explore_execute(recorded_spans, caplog):
    """End-to-end adversarial pass: preview -> explore -> execute, with the
    vault explorer enabled. Checks caplog (DEBUG), span attributes, and raw
    HTTP response text at every step for the original, its pseudonym, and
    the token itself.

    The "provider request identical flag on vs off" property is checked on
    ONE shared service/vault (flipping the private flag between two
    ``execute()`` calls) rather than two independently constructed
    services: ``InMemoryVault`` issues a fresh random pseudonym per
    instance, so comparing across two separate vaults would fail from
    pseudonym randomness alone, not from anything the flag actually
    changed. On one shared vault, the SAME (scope, key, category, value)
    resolves to the SAME stable pseudonym on both calls (``InMemoryVault``'s
    own stability guarantee), so a real defect -- the flag perturbing the
    decision or provider payload -- is exactly what would make this differ.
    """
    provider = RecordingProvider()
    service = build_service(provider, demo_vault_explorer_enabled=True)
    client = build_client(service)

    with caplog.at_level(logging.DEBUG):
        preview = _preview(client, strategy="b2")
        token = preview.json()["vault_explorer_token"]
        explore = _explore(client, token)
        pseudonym = next(
            e["pseudonym"] for e in explore.json()["entries"] if e["category"] == "employee_name"
        )
        execute_on = client.post(
            "/disclosure/execute", json={"text": HR_TEXT, "task": "summarize", "strategy": "b2"}
        )

        service._demo_vault_explorer_enabled = False
        execute_off = client.post(
            "/disclosure/execute", json={"text": HR_TEXT, "task": "summarize", "strategy": "b2"}
        )

    for record in caplog.records:
        message = record.getMessage()
        assert SENSITIVE_NAME not in message
        assert SENSITIVE_CPF not in message
        assert pseudonym not in message
        assert token not in message

    finished = recorded_spans.get_finished_spans()
    _assert_span_attributes_never_leak(
        finished, SENSITIVE_NAME, SENSITIVE_CPF, HR_TEXT, pseudonym, token
    )

    assert execute_on.status_code == execute_off.status_code == 200
    assert len(provider.received) == 2
    assert provider.received[0].payload == provider.received[1].payload
    assert provider.received[0].task == provider.received[1].task

    assert SENSITIVE_NAME not in execute_on.text
    assert pseudonym not in execute_on.text
    assert token not in execute_on.text
