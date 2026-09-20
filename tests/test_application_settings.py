"""T27 / issue #69: ``application/settings.demo_transparency_enabled`` --
the flag-parsing rule for ``ADG_ENABLE_DEMO_TRANSPARENCY``, exercised in
isolation from the rest of ``build_default_service`` (which
``tests/test_application_default_service.py`` covers end to end).
"""

from __future__ import annotations

import pytest

from adaptive_disclosure_gateway.application.settings import (
    DEMO_TRANSPARENCY_ENV_VAR,
    demo_transparency_enabled,
)

assert DEMO_TRANSPARENCY_ENV_VAR == "ADG_ENABLE_DEMO_TRANSPARENCY"


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
def test_demo_transparency_enabled_parsing_table(monkeypatch, raw_value, expected):
    if raw_value is None:
        monkeypatch.delenv(DEMO_TRANSPARENCY_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(DEMO_TRANSPARENCY_ENV_VAR, raw_value)

    assert demo_transparency_enabled() is expected
