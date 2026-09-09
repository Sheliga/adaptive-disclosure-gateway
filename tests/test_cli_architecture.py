"""T20 / issue #28, slice 3, absolute rule 3: the CLI must work WITHOUT
FastAPI installed. ``adaptive_disclosure_gateway.api.__init__`` imports
``create_app``, which imports ``fastapi`` -- so
``adaptive_disclosure_gateway.cli`` must never import anything under
``adaptive_disclosure_gateway.api``, nor ``fastapi``/``starlette`` directly.

Mirrors ``tests/test_api_architecture.py``'s AST-based approach (checked at
the source-code level, not trusted from docstrings) plus a functional
subprocess proof that importing ``cli`` alone never pulls ``fastapi`` into
``sys.modules``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

CLI_PATH = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway" / "cli.py"

_FORBIDDEN_MODULE_PREFIXES = ("fastapi", "starlette", "adaptive_disclosure_gateway.api")


def test_cli_module_file_exists():
    assert CLI_PATH.is_file()


def test_cli_does_not_import_fastapi_or_the_api_package_at_the_source_level():
    tree = ast.parse(CLI_PATH.read_text(encoding="utf-8"), filename=str(CLI_PATH))
    violations = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        for module in modules:
            if module.startswith(_FORBIDDEN_MODULE_PREFIXES):
                violations.append(module)
    assert not violations, f"cli.py imports forbidden module(s): {violations}"


def test_importing_cli_alone_in_a_fresh_process_never_pulls_in_fastapi():
    """Functional proof, not just a source-level pin: block ``fastapi`` from
    ``sys.modules`` via a meta-path finder in a fresh subprocess, import only
    ``adaptive_disclosure_gateway.cli``, and confirm both that the import
    succeeds and that fastapi was never (transitively) imported.
    """
    script = """
import sys

class _BlockFastAPI:
    def find_module(self, name, path=None):
        if name == "fastapi" or name.startswith("fastapi."):
            raise ImportError("fastapi is deliberately unavailable in this test")
        return None

sys.meta_path.insert(0, _BlockFastAPI())

import adaptive_disclosure_gateway.cli  # noqa: F401

assert "fastapi" not in sys.modules, "cli import pulled fastapi into sys.modules"
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(__file__).parents[1] / "src"),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "OK" in result.stdout


def test_cli_main_entry_point_is_registered_as_a_console_script():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'adg = "adaptive_disclosure_gateway.cli:main"' in pyproject
