"""T29 / issue #72: ``application/settings.demo_vault_explorer_enabled`` --
the flag-parsing rule for ``ADG_ENABLE_DEMO_VAULT_EXPLORER``, independent of
``ADG_ENABLE_DEMO_TRANSPARENCY``. Mirrors
``tests/test_application_settings.py``'s parsing table for that sibling flag.
"""

from __future__ import annotations

import pytest

from adaptive_disclosure_gateway.application.settings import (
    DEMO_VAULT_EXPLORER_ENV_VAR,
    demo_vault_explorer_enabled,
)

assert DEMO_VAULT_EXPLORER_ENV_VAR == "ADG_ENABLE_DEMO_VAULT_EXPLORER"


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
        ("2", False),
    ],
)
def test_demo_vault_explorer_enabled_parsing_table(monkeypatch, raw_value, expected):
    if raw_value is None:
        monkeypatch.delenv(DEMO_VAULT_EXPLORER_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(DEMO_VAULT_EXPLORER_ENV_VAR, raw_value)

    assert demo_vault_explorer_enabled() is expected


def test_demo_vault_explorer_flag_is_independent_of_demo_transparency_flag(monkeypatch):
    """The two flags must never be conflated -- enabling one must not
    silently enable or require the other.
    """
    monkeypatch.setenv("ADG_ENABLE_DEMO_TRANSPARENCY", "1")
    monkeypatch.delenv(DEMO_VAULT_EXPLORER_ENV_VAR, raising=False)
    assert demo_vault_explorer_enabled() is False

    monkeypatch.delenv("ADG_ENABLE_DEMO_TRANSPARENCY", raising=False)
    monkeypatch.setenv(DEMO_VAULT_EXPLORER_ENV_VAR, "1")
    assert demo_vault_explorer_enabled() is True
