"""T32.3 / issue #103: ``application/settings.demo_inspection_enabled`` --
the flag-parsing rule for ``ADG_ENABLE_DEMO_INSPECTION``, exercised in
isolation from the rest of ``build_default_service`` (which
``tests/test_demo_capability_matrix.py`` covers end to end, through the
HTTP app).

Until #103 the request-scoped inspection projection (T27 / #69) was gated by
``ADG_ENABLE_DEMO_TRANSPARENCY``, the same variable the web tier uses to gate
the T28 export/restore re-identification proxy -- so a deployment could not
show a before/after without also opening restore. The Python API now reads
only this dedicated flag for inspection; ``ADG_ENABLE_DEMO_TRANSPARENCY``
(and ``ADG_ENABLE_DEMO_VAULT_EXPLORER``) must never imply it.
"""

from __future__ import annotations

import pytest

from adaptive_disclosure_gateway.application import settings
from adaptive_disclosure_gateway.application.settings import (
    DEMO_INSPECTION_ENV_VAR,
    DEMO_VAULT_EXPLORER_ENV_VAR,
    demo_inspection_enabled,
    demo_vault_explorer_enabled,
)

assert DEMO_INSPECTION_ENV_VAR == "ADG_ENABLE_DEMO_INSPECTION"


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, False),  # unset
        ("", False),
        (" ", False),
        ("0", False),
        ("1", True),
        (" 1 ", True),
        ("true", False),
        ("yes", False),
        ("True", False),
        ("on", False),
        ("2", False),
        ("11", False),
    ],
)
def test_demo_inspection_enabled_parsing_table(monkeypatch, raw_value, expected):
    if raw_value is None:
        monkeypatch.delenv(DEMO_INSPECTION_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(DEMO_INSPECTION_ENV_VAR, raw_value)

    assert demo_inspection_enabled() is expected


def test_transparency_and_vault_flags_never_imply_inspection(monkeypatch):
    monkeypatch.delenv(DEMO_INSPECTION_ENV_VAR, raising=False)
    monkeypatch.setenv("ADG_ENABLE_DEMO_TRANSPARENCY", "1")
    monkeypatch.setenv(DEMO_VAULT_EXPLORER_ENV_VAR, "1")

    assert demo_inspection_enabled() is False


def test_inspection_flag_never_implies_the_vault_explorer(monkeypatch):
    monkeypatch.setenv(DEMO_INSPECTION_ENV_VAR, "1")
    monkeypatch.delenv(DEMO_VAULT_EXPLORER_ENV_VAR, raising=False)

    assert demo_vault_explorer_enabled() is False


def test_the_python_api_no_longer_reads_the_transparency_flag_at_all():
    """The Python API's only use of ``ADG_ENABLE_DEMO_TRANSPARENCY`` was the
    inspection gate. Keeping a reader around after #103 would invite exactly
    the coupling this ticket removes (``inspection = transparency or ...``).
    Export/restore stay gated server-side by the web proxy's own
    ``ADG_ENABLE_DEMO_TRANSPARENCY`` check and, here, by
    ``ADG_RESTORE_HANDLE_SECRET`` (``RestoreUnavailableError`` when unset).
    """
    assert not hasattr(settings, "demo_transparency_enabled")
    assert not hasattr(settings, "DEMO_TRANSPARENCY_ENV_VAR")
