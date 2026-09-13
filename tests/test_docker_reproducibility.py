"""Reproducible container dependencies for the api image (T25 review finding
4). Never starts Docker -- parses the committed Dockerfile/constraints text
and ``pyproject.toml`` so a regression (a runtime dependency added without
refreshing the lock, a base image ``FROM`` line losing its digest, a ``pip
install`` that stops passing the constraints file) is caught by the ordinary
local test suite.

Without a pinned, resolved dependency closure, an unrelated upstream release
(docling, a transitive dependency, even a patch-level bump pulled in by a
loose ``>=``) can silently change what actually ships in the demo image
between two otherwise-identical builds -- exactly the kind of drift this
file's tests exist to make a caught, reviewable failure instead of a silent
one.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_DOCKERFILE_PATH = _REPO_ROOT / "docker" / "api.Dockerfile"
_WEB_DOCKERFILE_PATH = _REPO_ROOT / "web" / "Dockerfile"
_COMPOSE_PATH = _REPO_ROOT / "compose.demo.yaml"
_CONSTRAINTS_PATH = _REPO_ROOT / "docker" / "api-constraints.txt"
_PYPROJECT_PATH = _REPO_ROOT / "pyproject.toml"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*")
_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)==([A-Za-z0-9_.+\-]+)$")
_FROM_RE = re.compile(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", re.IGNORECASE)


def _normalize(name: str) -> str:
    """PEP 503 normalization: lowercase, runs of ``-_.`` collapsed to one ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _distribution_name(requirement: str) -> str:
    match = _NAME_RE.match(requirement.strip())
    assert match, f"could not parse a distribution name from requirement {requirement!r}"
    return _normalize(match.group(0))


def _pyproject() -> dict:
    with _PYPROJECT_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _required_runtime_distribution_names() -> set[str]:
    """Every distribution the api image's runtime closure must cover: the
    project's base ``dependencies`` plus the ``api``, ``documents`` and
    ``anthropic`` optional-dependency groups -- exactly the extras
    ``docker/api.Dockerfile`` installs (``.[api,documents,anthropic]``).
    Deliberately excludes ``dev`` (test tooling never ships in the image).
    """
    project = _pyproject()["project"]
    names = {_distribution_name(req) for req in project["dependencies"]}
    optional = project["optional-dependencies"]
    for extra in ("api", "documents", "anthropic"):
        names.update(_distribution_name(req) for req in optional[extra])
    return names


def _constraints_lines() -> list[str]:
    text = _CONSTRAINTS_PATH.read_text(encoding="utf-8")
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _constraints_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in _constraints_lines():
        match = _PIN_RE.match(line)
        assert match, f"constraints line is not an exact 'name==version' pin: {line!r}"
        pins[_normalize(match.group(1))] = match.group(2)
    return pins


def _dockerfile_run_instructions(path: Path) -> list[str]:
    """Join each Dockerfile ``RUN`` instruction (including its ``\\``-continued
    lines) into one string per instruction, skipping comment lines --
    exactly what "parse the RUN instructions, not comments" requires.
    """
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()]
    instructions: list[str] = []
    current: list[str] | None = None
    for raw_line in lines:
        stripped = raw_line.strip()
        if current is None:
            if stripped.startswith("#"):
                continue
            if stripped.startswith("RUN "):
                current = [stripped]
                if not stripped.endswith("\\"):
                    instructions.append(" ".join(current))
                    current = None
            continue
        current.append(stripped)
        if not stripped.endswith("\\"):
            instructions.append(" ".join(current))
            current = None
    return instructions


class TestConstraintsFile:
    def test_constraints_file_exists(self) -> None:
        assert _CONSTRAINTS_PATH.is_file(), "docker/api-constraints.txt must exist"

    def test_every_non_comment_line_is_an_exact_pin(self) -> None:
        # _constraints_pins() itself asserts every line matches _PIN_RE.
        pins = _constraints_pins()
        assert pins, "docker/api-constraints.txt must not be empty"

    def test_no_duplicate_pins_for_the_same_distribution(self) -> None:
        seen: dict[str, str] = {}
        for line in _constraints_lines():
            match = _PIN_RE.match(line)
            assert match
            name = _normalize(match.group(1))
            assert name not in seen, f"{name} is pinned more than once in the constraints file"
            seen[name] = match.group(2)

    def test_pins_key_runtime_packages(self) -> None:
        pins = _constraints_pins()
        for name in ("docling", "anthropic", "torch", "fastapi", "uvicorn"):
            assert name in pins, f"docker/api-constraints.txt must pin {name}"

    def test_covers_every_declared_runtime_dependency(self) -> None:
        """A runtime dependency added to pyproject.toml (base, api, documents
        or anthropic) without refreshing the lock must fail this test --
        that is the whole reproducibility guarantee this file exists for.
        """
        pins = _constraints_pins()
        required = _required_runtime_distribution_names()
        missing = sorted(required - set(pins))
        assert not missing, (
            f"docker/api-constraints.txt is missing a pin for: {missing!r} -- regenerate it "
            "(see docker/api-constraints.txt's header comment / docs/advisor-demo.md)"
        )

    def test_header_documents_the_regeneration_command(self) -> None:
        text = _CONSTRAINTS_PATH.read_text(encoding="utf-8")
        assert "pip freeze" in text or "pip-compile" in text, (
            "docker/api-constraints.txt's header must document the exact regeneration command"
        )


class TestApiDockerfileUsesConstraints:
    def test_every_pip_install_passes_the_constraints_file(self) -> None:
        instructions = _dockerfile_run_instructions(_API_DOCKERFILE_PATH)
        pip_installs = [instr for instr in instructions if "pip install" in instr]
        assert pip_installs, "api.Dockerfile must contain at least one 'pip install' RUN"
        for instruction in pip_installs:
            assert "-c " in instruction or "--constraint " in instruction, (
                f"pip install must pass -c/--constraint with the constraints file: {instruction!r}"
            )
            assert "api-constraints.txt" in instruction, (
                f"pip install must reference docker/api-constraints.txt: {instruction!r}"
            )

    def test_constraints_file_is_copied_into_the_build_context(self) -> None:
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        assert "api-constraints.txt" in text
        copy_lines = [
            line
            for line in text.splitlines()
            if line.strip().startswith("COPY") and "api-constraints.txt" in line
        ]
        assert copy_lines, (
            "api.Dockerfile must COPY docker/api-constraints.txt into the build context before "
            "the pip install steps that reference it"
        )


def _root_base_image_refs(path: Path) -> list[str]:
    """Every ``FROM`` image reference that names an actual registry image --
    i.e. excluding a multi-stage Dockerfile's later ``FROM <earlier-stage-alias>
    AS <name>`` lines, which reference a previous stage by its own ``AS``
    alias rather than a pullable image and therefore carry no digest of
    their own to pin.
    """
    stage_aliases: set[str] = set()
    root_refs: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _FROM_RE.match(line.strip())
        if not match:
            continue
        image_ref, alias = match.group(1), match.group(2)
        if image_ref not in stage_aliases:
            root_refs.append(image_ref)
        if alias:
            stage_aliases.add(alias)
    return root_refs


class TestBaseImageDigests:
    """Pinning a tag alone (``python:3.13.13-slim``) still lets the same tag
    point at a different image tomorrow if it is ever republished -- the
    digest is the only part of a ``FROM`` line that is truly immutable.
    """

    def test_api_dockerfile_base_image_pins_a_digest(self) -> None:
        refs = _root_base_image_refs(_API_DOCKERFILE_PATH)
        assert refs, "api.Dockerfile must declare at least one FROM"
        for image_ref in refs:
            assert "@sha256:" in image_ref, f"FROM line must pin a digest: {image_ref!r}"

    def test_web_dockerfile_base_image_pins_a_digest(self) -> None:
        refs = _root_base_image_refs(_WEB_DOCKERFILE_PATH)
        assert refs, "web/Dockerfile must declare at least one FROM"
        for image_ref in refs:
            assert "@sha256:" in image_ref, f"FROM line must pin a digest: {image_ref!r}"

    def test_compose_caddy_image_pins_an_exact_version_and_digest(self) -> None:
        import yaml

        with _COMPOSE_PATH.open(encoding="utf-8") as handle:
            compose = yaml.safe_load(handle)
        image = compose["services"]["caddy"]["image"]
        assert "@sha256:" in image, f"caddy image must pin a digest: {image!r}"
        # "caddy:2-alpine" floats across every 2.x release; an exact version
        # (e.g. "caddy:2.11.4-alpine") is required in addition to the digest
        # so the tag itself documents which version is pinned.
        tag = image.split("@", 1)[0]
        assert re.search(r":\d+\.\d+\.\d+", tag), (
            f"caddy image must pin an exact x.y.z version, not a floating tag: {image!r}"
        )
