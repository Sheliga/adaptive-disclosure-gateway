"""Architectural isolation between the corpus ground truth and the
treatment pipeline (T09 / issue #4, Phase A).

Mirrors ``tests/test_treatment_isolation.py``'s AST-based approach rather
than trusting docstrings: docs/experimental-design.md's "ground truth is
strictly an evaluation oracle; treatments do not receive it as privileged
input" is checked here at the import-graph and call-graph level, so a
change that wires ``pipeline.py`` or a treatment to the corpus package for
convenience fails the suite instead of silently regressing the invariant.
"""

from __future__ import annotations

import ast
from pathlib import Path

from adaptive_disclosure_gateway.corpus import CorpusCaseInput
from adaptive_disclosure_gateway.domain import DisclosureRequest, GovernanceContext

SRC_ROOT = Path(__file__).parents[1] / "src" / "adaptive_disclosure_gateway"
CORPUS_DIR = SRC_ROOT / "corpus"

# The production modules that implement B0-B4 and the shared pipeline. None
# of these may depend on the corpus package at all -- ground truth has no
# legitimate reason to be reachable from treatment/detection/policy code.
PRODUCTION_DIRS = (SRC_ROOT / "transformations", SRC_ROOT / "detection")
PRODUCTION_FILES = (SRC_ROOT / "policies.py", SRC_ROOT / "pipeline.py")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _production_source_files() -> list[Path]:
    files: list[Path] = []
    for directory in PRODUCTION_DIRS:
        files.extend(sorted(directory.glob("*.py")))
    files.extend(PRODUCTION_FILES)
    return files


def test_no_production_module_imports_the_corpus_package():
    files = _production_source_files()
    assert files, "expected production source files to check"

    violations = []
    for path in files:
        for module in _imported_modules(path):
            if "corpus" in module.lower():
                violations.append(f"{path} imports forbidden module {module!r}")

    assert not violations, "\n".join(violations)


def _functions_constructing_disclosure_request(path: Path) -> list[str]:
    """Names of every function/method in ``path`` whose body calls
    ``DisclosureRequest(...)`` directly.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "DisclosureRequest"
            ):
                found.append(node.name)
                break
    return found


def test_only_corpus_case_input_builds_a_disclosure_request():
    calling_functions = {}
    for path in sorted(CORPUS_DIR.glob("*.py")):
        functions = _functions_constructing_disclosure_request(path)
        if functions:
            calling_functions[path.name] = functions

    assert calling_functions == {"case_input.py": ["to_disclosure_request"]}, (
        "only CorpusCaseInput.to_disclosure_request may construct a DisclosureRequest "
        "-- CaseOracle must have no path into the pipeline"
    )


def test_disclosure_request_built_from_a_case_input_carries_no_oracle_field():
    case_input = CorpusCaseInput(
        sample_id="isolation_probe",
        task_family="team_summary_without_salary",
        text="Employee: Probe Person\nDepartment: Engineering\n",
        task="probe task",
        domain="hr",
        purpose="team_summary",
        policy_version="hr-v1",
    )

    request = case_input.to_disclosure_request()

    assert isinstance(request, DisclosureRequest)
    assert isinstance(request.context, GovernanceContext)
    # DisclosureRequest's own schema has exactly these three fields -- an
    # oracle-carrying field could only reach the request by widening this
    # set, which this pins against.
    assert set(type(request).model_fields) == {"text", "task", "context"}
