"""Static invariants over the T25 / issue #42 demo deployment artifacts:
``compose.demo.yaml``, ``docker/api.Dockerfile``, ``web/Dockerfile`` and the
two ``.dockerignore`` files.

These tests never start Docker -- they parse the committed YAML/text files
and pin the security-relevant shape the deployment must have, so a
regression is caught by the ordinary local test suite rather than only by a
human reading the compose file. This is the adversarial-test half of the
CLAUDE.md no-leak invariant applied to a deployment artifact instead of
application code: a secret-shaped environment variable literally checked
into ``compose.demo.yaml``, or forwarded to the ``web`` service, is exactly
the kind of side channel that invariant exists to catch, and none of it
would be caught by any behavioral test that only looks at HTTP responses.

Each test below is written to fail from a real defect: a hand-authored
compose file that names an API key inline, forwards a secret to the browser-
facing container, publishes the API's port, or omits a healthcheck would
fail one of these, not merely disagree with a style preference.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPOSE_PATH = _REPO_ROOT / "compose.demo.yaml"
_API_DOCKERFILE_PATH = _REPO_ROOT / "docker" / "api.Dockerfile"
_WEB_DOCKERFILE_PATH = _REPO_ROOT / "web" / "Dockerfile"
_ROOT_DOCKERIGNORE_PATH = _REPO_ROOT / ".dockerignore"
_WEB_DOCKERIGNORE_PATH = _REPO_ROOT / "web" / ".dockerignore"

_SECRET_ENV_VAR_NAMES = (
    "ANTHROPIC_API_KEY",
    "ADG_PREVIEW_CONFIRMATION_SECRET",
    "ADG_ANTHROPIC_MODEL_ID",
    "ADG_ANTHROPIC_MAX_OUTPUT_TOKENS",
    "ADG_ANTHROPIC_EFFORT",
    "ADG_ANTHROPIC_THINKING",
    "ADG_ANTHROPIC_TIMEOUT_SECONDS",
    "ADG_ANTHROPIC_BASE_URL",
    "ADG_ANTHROPIC_API_KEY_ENV_VAR",
)


def _load_compose() -> dict:
    with _COMPOSE_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _service(compose: dict, name: str) -> dict:
    return compose["services"][name]


def _environment_mapping(service: dict) -> dict[str, str]:
    """Normalize compose's ``environment`` (mapping or ``KEY=value`` list
    form) to a plain ``dict`` so tests do not care which form was used.
    """
    raw = service.get("environment", {})
    if isinstance(raw, dict):
        return {str(key): "" if value is None else str(value) for key, value in raw.items()}
    mapping: dict[str, str] = {}
    for item in raw:
        key, _, value = str(item).partition("=")
        mapping[key] = value
    return mapping


class TestComposeFileExists:
    def test_compose_demo_file_exists(self) -> None:
        assert _COMPOSE_PATH.is_file(), "compose.demo.yaml must exist at the repository root"

    def test_compose_demo_is_valid_yaml_with_api_and_web_services(self) -> None:
        compose = _load_compose()
        assert "api" in compose["services"]
        assert "web" in compose["services"]


class TestApiServiceSecurity:
    def test_api_service_publishes_no_host_port(self) -> None:
        """The API is internal-only: only the web service is reachable from
        the host. A published API port would let a caller bypass the web
        origin entirely and hit the Python API directly.
        """
        api = _service(_load_compose(), "api")
        assert not api.get("ports"), "the api service must not publish a host port"

    def test_api_service_has_no_volumes(self) -> None:
        """No persistent storage for uploaded documents -- the ephemeral
        no-persistence invariant applies to the container layer too, not
        just to application code.
        """
        api = _service(_load_compose(), "api")
        assert not api.get("volumes"), "the api service must not mount any volume"

    def test_api_service_has_a_healthcheck(self) -> None:
        api = _service(_load_compose(), "api")
        assert api.get("healthcheck"), "the api service must define a healthcheck"

    def test_secret_named_variables_on_api_are_interpolations_not_literals(self) -> None:
        """Every secret-shaped variable must be a compose interpolation
        (``${VAR}``/``${VAR:-...}``/``${VAR:?...}``) sourced from the host
        environment/.env file -- never a literal value checked into the
        compose file. A literal here would be exactly the class of defect
        CLAUDE.md's no-leak invariant warns about: a developer's real key
        baked into a file that gets committed.
        """
        api = _service(_load_compose(), "api")
        env = _environment_mapping(api)
        for name in _SECRET_ENV_VAR_NAMES:
            if name not in env:
                continue
            value = env[name]
            assert value.startswith("${") and value.endswith("}"), (
                f"{name} on the api service must be a compose interpolation, not a literal "
                f"value; got {value!r}"
            )

    def test_provider_selection_is_a_required_interpolation(self) -> None:
        """``ADG_PROVIDER`` must be explicitly required (``${ADG_PROVIDER:?...}``)
        so the demo stack never silently launches with an unintended
        provider default either way.
        """
        api = _service(_load_compose(), "api")
        env = _environment_mapping(api)
        assert "ADG_PROVIDER" in env
        assert ":?" in env["ADG_PROVIDER"], (
            "ADG_PROVIDER must use the compose required-variable interpolation "
            "form ('${ADG_PROVIDER:?...}'), never a silent default"
        )


class TestWebServiceSecurity:
    def test_web_service_carries_no_secret_named_variable(self) -> None:
        """Anthropic credentials and the confirmation secret are read only
        by the Python API, never by the Next.js container -- the browser
        never talks to the API directly (see web/lib/proxy.ts), so the web
        container has no legitimate reason to hold any of these.
        """
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        for name in _SECRET_ENV_VAR_NAMES:
            assert name not in env, f"web service must not carry {name}"

    def test_web_service_has_no_next_public_variable(self) -> None:
        """``NEXT_PUBLIC_*`` variables are inlined into the client bundle at
        build time; nothing this stack configures may ever be exposed that
        way.
        """
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        assert not any(name.startswith("NEXT_PUBLIC_") for name in env)

    def test_web_service_has_no_volumes(self) -> None:
        web = _service(_load_compose(), "web")
        assert not web.get("volumes"), "the web service must not mount any volume"

    def test_web_service_has_a_healthcheck(self) -> None:
        web = _service(_load_compose(), "web")
        assert web.get("healthcheck"), "the web service must define a healthcheck"

    def test_web_service_publishes_exactly_one_host_port(self) -> None:
        web = _service(_load_compose(), "web")
        assert web.get("ports"), "the web service must publish a host port"
        assert len(web["ports"]) == 1

    def test_web_depends_on_api_being_healthy(self) -> None:
        web = _service(_load_compose(), "web")
        depends_on = web.get("depends_on")
        assert depends_on, "the web service must declare depends_on for api"
        if isinstance(depends_on, dict):
            assert depends_on.get("api", {}).get("condition") == "service_healthy"
        else:
            pytest.fail("depends_on must use the long form with a service_healthy condition")

    def test_web_api_base_url_targets_the_api_service_not_localhost(self) -> None:
        """The web container reaches the API by its compose service name
        (``api``), never ``127.0.0.1``/``localhost`` -- those would resolve
        to the web container itself, not the API container.
        """
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        assert "ADG_API_BASE_URL" in env
        value = env["ADG_API_BASE_URL"]
        assert "localhost" not in value
        assert "127.0.0.1" not in value
        assert "api" in value


class TestDockerfiles:
    def test_api_dockerfile_exists(self) -> None:
        assert _API_DOCKERFILE_PATH.is_file()

    def test_web_dockerfile_exists(self) -> None:
        assert _WEB_DOCKERFILE_PATH.is_file()

    def test_api_dockerfile_uses_python_313(self) -> None:
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        assert "python:3.13" in text

    def test_api_dockerfile_declares_no_secret_env_or_arg(self) -> None:
        """A secret-named ``ENV``/``ARG`` instruction would bake that name's
        value into an image layer at build time (and, for ``ARG``, often
        into build logs/history too) -- credentials must only ever arrive
        at container *runtime*, via compose interpolation.
        """
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("ENV ", "ARG ")):
                continue
            for name in _SECRET_ENV_VAR_NAMES:
                assert name not in stripped, (
                    f"api.Dockerfile must not declare {name} via ENV/ARG: {stripped!r}"
                )

    def test_api_dockerfile_runs_as_non_root(self) -> None:
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        assert "USER " in text, "api.Dockerfile must switch to a non-root USER"
        assert "USER root" not in text.splitlines()[-5:]

    def test_web_dockerfile_runs_as_non_root(self) -> None:
        text = _WEB_DOCKERFILE_PATH.read_text(encoding="utf-8")
        assert "USER " in text, "web/Dockerfile must switch to a non-root USER"

    def test_web_dockerfile_declares_no_secret_env_or_arg(self) -> None:
        text = _WEB_DOCKERFILE_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("ENV ", "ARG ")):
                continue
            for name in _SECRET_ENV_VAR_NAMES:
                assert name not in stripped

    def test_web_dockerfile_does_not_bake_api_base_url_at_build_time(self) -> None:
        """``ADG_API_BASE_URL`` must be read at container runtime (Next.js
        route handlers read ``process.env`` when the request is handled),
        never fixed as a build-time ``ENV``/``ARG`` -- that would freeze the
        compose network address into the image and break portability across
        deployments.
        """
        text = _WEB_DOCKERFILE_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("ENV ADG_API_BASE_URL", "ARG ADG_API_BASE_URL")):
                pytest.fail(f"ADG_API_BASE_URL must not be a build-time ENV/ARG: {stripped!r}")


class TestDockerignore:
    def test_root_dockerignore_exists(self) -> None:
        assert _ROOT_DOCKERIGNORE_PATH.is_file()

    def test_root_dockerignore_excludes_env_files(self) -> None:
        text = _ROOT_DOCKERIGNORE_PATH.read_text(encoding="utf-8")
        entries = {line.strip() for line in text.splitlines() if line.strip()}
        assert ".env" in entries
        assert any(entry.startswith(".env.") and "*" in entry for entry in entries), (
            "root .dockerignore must exclude .env.* variants (e.g. '.env.*')"
        )

    def test_root_dockerignore_excludes_git_and_venv(self) -> None:
        text = _ROOT_DOCKERIGNORE_PATH.read_text(encoding="utf-8")
        assert ".git" in text
        assert ".venv" in text

    def test_web_dockerignore_exists(self) -> None:
        assert _WEB_DOCKERIGNORE_PATH.is_file()

    def test_web_dockerignore_excludes_node_modules_and_next(self) -> None:
        text = _WEB_DOCKERIGNORE_PATH.read_text(encoding="utf-8")
        assert "node_modules" in text
        assert ".next" in text
