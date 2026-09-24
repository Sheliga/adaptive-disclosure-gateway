"""T32.3 / issue #103: the three demo capabilities are independent, end to
end, through the app a real deployment actually runs (``create_app()`` with
no injected service, i.e. ``build_default_service`` reading the environment).

- INSPECTION (``ADG_ENABLE_DEMO_INSPECTION``) -> ``preview.inspection``
  populated: a request-scoped explanation of content the caller itself just
  submitted;
- TRANSPARENCY (``ADG_ENABLE_DEMO_TRANSPARENCY``) -> T28 export/restore, gated
  at the web proxy (``web/lib/demoTransparency.ts``); the Python API itself
  no longer reads it;
- VAULT_EXPLORER (``ADG_ENABLE_DEMO_VAULT_EXPLORER``) -> vault explorer token
  + route.

None implies another. The last section pins the PRODUCTION posture by
reading ``compose.prod.yaml``'s own api environment and running the app with
exactly that environment -- so the route gates are tested, not merely the
absence of a button.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from adaptive_disclosure_gateway.api.app import create_app
from tests.api_support import HR_TEXT

_REPO_ROOT = Path(__file__).resolve().parent.parent

_FLAGS = (
    "ADG_ENABLE_DEMO_INSPECTION",
    "ADG_ENABLE_DEMO_TRANSPARENCY",
    "ADG_ENABLE_DEMO_VAULT_EXPLORER",
)

#: Everything build_default_service reads that could change the outcome of
#: these tests; cleared so the ambient environment never leaks in.
_AMBIENT = (
    *_FLAGS,
    "ADG_PROVIDER",
    "ADG_RESTORE_HANDLE_SECRET",
    "ADG_RESTORE_HANDLE_TTL_SECONDS",
    "ADG_PREVIEW_CONFIRMATION_SECRET",
)


def _client(monkeypatch, env: dict[str, str]) -> TestClient:
    for name in _AMBIENT:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return TestClient(create_app())


def _preview(client: TestClient) -> dict:
    response = client.post(
        "/disclosure/preview",
        json={"text": HR_TEXT, "task": "summarize personnel record", "strategy": "b2"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("inspection", "transparency", "vault"),
    list(itertools.product((False, True), repeat=3)),
)
def test_each_capability_is_gated_only_by_its_own_flag(
    monkeypatch, inspection, transparency, vault
):
    env = {
        name: "1" for name, on in zip(_FLAGS, (inspection, transparency, vault), strict=True) if on
    }
    client = _client(monkeypatch, env)

    body = _preview(client)

    assert (body["inspection"] is not None) is inspection
    assert (body["vault_explorer_token"] is not None) is vault
    explorer = client.post("/demo/vault-explorer", json={"token": "not-a-real-token"})
    if not vault:
        assert explorer.status_code == 404


@pytest.mark.parametrize("raw", ["", "0", "true", "yes", "True", "on", "2"])
def test_inspection_stays_off_for_anything_but_exactly_one(monkeypatch, raw):
    client = _client(monkeypatch, {"ADG_ENABLE_DEMO_INSPECTION": raw})

    assert _preview(client)["inspection"] is None


def test_inspection_on_with_transparency_on_does_not_change_the_projection(monkeypatch):
    """Inspection is populated REGARDLESS of transparency: turning
    transparency on must neither add nor remove anything from it.
    """
    alone = _preview(_client(monkeypatch, {"ADG_ENABLE_DEMO_INSPECTION": "1"}))
    both = _preview(
        _client(
            monkeypatch,
            {"ADG_ENABLE_DEMO_INSPECTION": "1", "ADG_ENABLE_DEMO_TRANSPARENCY": "1"},
        )
    )

    def shape(inspection):
        # Pseudonyms are minted per vault (i.e. per app instance), so compare
        # everything but the pseudonymized disclosed text itself.
        return [(seg["action"], seg["category"], seg["original"]) for seg in inspection["segments"]]

    assert alone["inspection"]["available"] is True
    assert both["inspection"]["available"] is True
    assert shape(alone["inspection"]) == shape(both["inspection"])


# --- production posture (compose.prod.yaml) ----------------------------------


def _prod_api_literal_env() -> dict[str, str]:
    """The api service's environment exactly as ``compose.prod.yaml`` states
    it, keeping only LITERAL values: every ``${VAR:-}`` interpolation depends
    on the operator's ``.env`` and is modeled as unset (its documented
    default), which is what these tests assert the file itself enables.
    """
    with (_REPO_ROOT / "compose.prod.yaml").open(encoding="utf-8") as handle:
        compose = yaml.safe_load(handle)
    raw = compose["services"]["api"]["environment"]
    return {
        str(name): str(value)
        for name, value in raw.items()
        if value is not None and not str(value).startswith("${")
    }


def test_production_api_env_enables_inspection_and_nothing_else(monkeypatch):
    client = _client(monkeypatch, _prod_api_literal_env())

    body = _preview(client)

    assert body["inspection"] is not None
    assert body["inspection"]["available"] is True
    assert body["vault_explorer_token"] is None


def test_production_api_env_keeps_the_vault_explorer_route_closed(monkeypatch):
    client = _client(monkeypatch, _prod_api_literal_env())

    response = client.post("/demo/vault-explorer", json={"token": "not-a-real-token"})

    assert response.status_code == 404


def test_production_api_env_keeps_restore_closed_server_side(monkeypatch):
    """With no restore secret configured (``compose.prod.yaml`` never sets
    one), ``/documents/restore`` fails closed at the API itself -- the web
    proxy's own transparency gate is a second, independent wall, pinned in
    ``web/app/api/documents/restore/route.test.ts``.
    """
    client = _client(monkeypatch, _prod_api_literal_env())

    response = client.post(
        "/documents/restore", json={"text": "anything", "restore_handle": "not-a-handle"}
    )

    assert response.status_code == 503
