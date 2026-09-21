"""Issue #87 / M3 -- the two frozen-corpus pilot scripts must pin
``protocol_id="post-pilot-v3"`` explicitly, never rely on
``CURRENT_PROTOCOL_ID``'s default.

``corpus/hr/v1`` and ``corpus/contracts/v1`` are both frozen, legacy
(schema-v2) corpora: no case file has an opted-in
``CaseOracle.utility_references``, and several depend on a registered
numeric category. ``CURRENT_PROTOCOL_ID`` is now ``post-pilot-v4``, under
which both corpora are refused outright
(``MissingUtilityReferencesError``) -- a script that let ``run_pilot``
resolve its own default protocol id would break the moment
``CURRENT_PROTOCOL_ID`` moves again, exactly the kind of silent drift a
pinned constant exists to prevent.

This is a real regression test: if a future edit removes the explicit
``protocol_id=PROTOCOL_ID`` keyword argument from either script's
``run_pilot(...)`` call (even while leaving the ``PROTOCOL_ID`` constant
itself in place, unused), the AST check below fails.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from adaptive_disclosure_gateway.corpus.loader import load_corpus
from adaptive_disclosure_gateway.experiments.scoring.utility import (
    MissingUtilityReferencesError,
    check_corpus_protocol_compatibility,
)

REPO_ROOT = Path(__file__).parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_script_module(name: str) -> ModuleType:
    """Import a ``scripts/*.py`` dev entrypoint by file path -- ``scripts/``
    is deliberately not on ``pythonpath`` (it is not a package, per its own
    module docstrings), so this loads it directly rather than adding it to
    ``sys.path`` for the whole test session.
    """
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_pilot_call_has_protocol_id_kwarg(script_name: str) -> bool:
    """AST check: does the ``run_pilot(...)`` call inside ``main()`` pass a
    ``protocol_id`` keyword argument at all -- regardless of its value?
    Deliberately narrow (mirrors this repo's other AST-based architectural
    tests): it does not evaluate what the keyword's value resolves to, only
    that the call site names it, so a future edit cannot silently drop the
    keyword while leaving an unused constant behind as false reassurance.
    """
    source = (SCRIPTS_DIR / f"{script_name}.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script_name)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "run_pilot"
            and any(keyword.arg == "protocol_id" for keyword in node.keywords)
        ):
            return True
    return False


@pytest.mark.parametrize(
    ("script_name", "corpus_relpath"),
    [
        ("run_hr_v1_pilot", ("corpus", "hr", "v1", "cases")),
        ("run_contracts_v1_pilot", ("corpus", "contracts", "v1", "cases")),
    ],
)
def test_script_pins_protocol_id_post_pilot_v3_explicitly(script_name, corpus_relpath):
    module = _load_script_module(script_name)
    assert module.PROTOCOL_ID == "post-pilot-v3"


@pytest.mark.parametrize(
    "script_name",
    ["run_hr_v1_pilot", "run_contracts_v1_pilot"],
)
def test_script_run_pilot_call_passes_protocol_id_keyword(script_name):
    assert _run_pilot_call_has_protocol_id_kwarg(script_name), (
        f"{script_name}.py's run_pilot(...) call must pass protocol_id= explicitly -- "
        "relying on run_pilot's own CURRENT_PROTOCOL_ID default would refuse this "
        "frozen, legacy corpus once CURRENT_PROTOCOL_ID moves to post-pilot-v4"
    )


@pytest.mark.parametrize(
    ("script_name", "corpus_relpath"),
    [
        ("run_hr_v1_pilot", ("corpus", "hr", "v1", "cases")),
        ("run_contracts_v1_pilot", ("corpus", "contracts", "v1", "cases")),
    ],
)
def test_pinned_protocol_id_is_actually_compatible_with_the_frozen_corpus(
    script_name, corpus_relpath
):
    module = _load_script_module(script_name)
    cases = load_corpus(REPO_ROOT.joinpath(*corpus_relpath))
    check_corpus_protocol_compatibility(cases, module.PROTOCOL_ID)  # must not raise


@pytest.mark.parametrize(
    "corpus_relpath",
    [
        ("corpus", "hr", "v1", "cases"),
        ("corpus", "contracts", "v1", "cases"),
    ],
)
def test_current_protocol_id_would_have_refused_these_frozen_corpora(corpus_relpath):
    """Demonstrates exactly why the pin in the test above matters: had
    either script instead resolved its own default (``CURRENT_PROTOCOL_ID``,
    now ``post-pilot-v4``), loading its corpus would fail closed before any
    provider call -- neither frozen corpus has an opted-in
    ``CaseOracle.utility_references``.
    """
    cases = load_corpus(REPO_ROOT.joinpath(*corpus_relpath))
    with pytest.raises(MissingUtilityReferencesError):
        check_corpus_protocol_compatibility(cases, "post-pilot-v4")
