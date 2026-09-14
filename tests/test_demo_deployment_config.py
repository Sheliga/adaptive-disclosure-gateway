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

import dataclasses
import re
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
    "ADG_RESTORE_HANDLE_SECRET",
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


@dataclasses.dataclass(frozen=True)
class _PublishedPort:
    """One published-port entry, normalized regardless of which of compose's
    two ``ports:`` syntaxes produced it -- short string
    (``"127.0.0.1:3000:3000"``, or bare ``"3000"``/``"3000:3000"`` with no
    host IP at all) or long mapping form
    (``{host_ip: 127.0.0.1, published: 3000, target: 3000}``). ``host_ip`` is
    ``None`` when the entry does not bind a specific host interface (i.e. it
    would publish on every interface), which is exactly the shape Finding 1
    exists to catch.
    """

    host_ip: str | None
    published: str | None
    target: str


#: Matches one compose interpolation (``${VAR}``/``${VAR:-default}``/
#: ``${VAR:?message}``) as a single opaque unit, so its own internal ``:``
#: (the ``:-``/``:?`` operator) is never mistaken for a host/port separator
#: by the short-syntax parsing below.
_INTERPOLATION_RE = re.compile(r"\$\{[^}]*\}")


def _parse_port_entry(entry: object) -> _PublishedPort:
    if isinstance(entry, dict):
        return _PublishedPort(
            host_ip=entry.get("host_ip"),
            published=str(entry["published"]) if entry.get("published") is not None else None,
            target=str(entry["target"]),
        )
    # Short syntax: "[HOST_IP:][HOST_PORT:]CONTAINER_PORT[/PROTOCOL]" per
    # https://docs.docker.com/reference/compose-file/services/#short-syntax-1.
    # An IPv6 host_ip would itself contain ':', but nothing in this repo's
    # compose file uses one, so splitting on the last two ':' cleanly
    # separates the fixed trailing "[host_port:]container_port" pair from an
    # arbitrarily-':'-containing leading host_ip -- once any ``${...}``
    # interpolation is masked out first, so its own colon does not get
    # mistaken for one of those separators.
    text = str(entry).split("/", 1)[0]
    placeholders: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\x00{len(placeholders) - 1}\x00"

    masked = _INTERPOLATION_RE.sub(_stash, text)

    def _unstash(part: str) -> str:
        for index, value in enumerate(placeholders):
            part = part.replace(f"\x00{index}\x00", value)
        return part

    parts = [_unstash(part) for part in masked.rsplit(":", 2)]
    if len(parts) == 3:
        host_ip, published, target = parts
        return _PublishedPort(host_ip=host_ip or None, published=published, target=target)
    if len(parts) == 2:
        published, target = parts
        return _PublishedPort(host_ip=None, published=published, target=target)
    return _PublishedPort(host_ip=None, published=None, target=parts[0])


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

    def test_api_service_healthcheck_targets_ready_not_health(self) -> None:
        """T25 review finding 2: the container healthcheck that gates
        ``web``'s ``depends_on: service_healthy`` must probe ``/ready``
        (purely local, 503 when not ready), not ``/health`` (always 200,
        liveness/introspection only) -- a container wired to an external
        provider with no credential must show as unhealthy, which only
        ``/ready`` can report.
        """
        api = _service(_load_compose(), "api")
        command = " ".join(str(part) for part in api["healthcheck"]["test"])
        assert "/ready" in command, f"api healthcheck must target /ready; got: {command!r}"
        assert "/health" not in command, (
            f"api healthcheck must not target /health; got: {command!r}"
        )

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

    def test_api_service_carries_optional_restore_handle_variables(self) -> None:
        """T26 / issue #67. Export/restore are an OPTIONAL feature: an
        unconfigured ``ADG_RESTORE_HANDLE_SECRET`` must not block startup of
        the whole demo stack (unlike ``ADG_PROVIDER``'s required
        interpolation above) -- it only makes ``/documents/export`` and
        ``/documents/restore`` themselves refuse with 503, per
        ``RestoreUnavailableError``. A ``:?`` (required) interpolation here
        would be a regression: it would make the entire api service refuse
        to start over a feature nobody asked to enable.
        """
        api = _service(_load_compose(), "api")
        env = _environment_mapping(api)
        for name in ("ADG_RESTORE_HANDLE_SECRET", "ADG_RESTORE_HANDLE_TTL_SECONDS"):
            assert name in env, f"api service must carry {name}"
            value = env[name]
            assert value.startswith("${") and value.endswith("}"), (
                f"{name} on the api service must be a compose interpolation; got {value!r}"
            )
            assert ":-" in value, (
                f"{name} must use the OPTIONAL interpolation form ('${{{name}:-}}'), "
                f"not a required ('${{{name}:?...}}') one; got {value!r}"
            )
            assert ":?" not in value, (
                f"{name} must not be a required interpolation (that would block startup of "
                f"the whole stack for an optional feature); got {value!r}"
            )

    def test_api_service_carries_the_optional_demo_transparency_variable(self) -> None:
        """T27/T28 / issues #69-#70. Like the restore-handle variables above,
        this must be OPTIONAL (``:-``): the demo transparency surfaces are an
        opt-in layered on top of the demo, not a precondition for it -- an
        unconfigured value must not block startup of the whole stack, it
        must simply keep every response's ``inspection`` field ``null``
        (the historical, pre-T27 behavior).
        """
        api = _service(_load_compose(), "api")
        env = _environment_mapping(api)
        name = "ADG_ENABLE_DEMO_TRANSPARENCY"
        assert name in env, f"api service must carry {name}"
        value = env[name]
        assert value.startswith("${") and value.endswith("}"), (
            f"{name} on the api service must be a compose interpolation; got {value!r}"
        )
        assert ":-" in value, (
            f"{name} must use the OPTIONAL interpolation form ('${{{name}:-}}'), "
            f"not a required ('${{{name}:?...}}') one; got {value!r}"
        )
        assert ":?" not in value, (
            f"{name} must not be a required interpolation (that would block startup of "
            f"the whole stack for an optional feature); got {value!r}"
        )

    def test_api_service_carries_the_optional_demo_vault_explorer_variable(self) -> None:
        """T29 / issue #72. Independent of ``ADG_ENABLE_DEMO_TRANSPARENCY``
        above (a separate opt-in), but the same OPTIONAL posture: unset must
        not block startup of the whole stack, it must simply keep
        ``PreviewResponse.vault_explorer_token`` null and
        ``POST /demo/vault-explorer`` answering a fixed 404.
        """
        api = _service(_load_compose(), "api")
        env = _environment_mapping(api)
        name = "ADG_ENABLE_DEMO_VAULT_EXPLORER"
        assert name in env, f"api service must carry {name}"
        value = env[name]
        assert value.startswith("${") and value.endswith("}"), (
            f"{name} on the api service must be a compose interpolation; got {value!r}"
        )
        assert ":-" in value, (
            f"{name} must use the OPTIONAL interpolation form ('${{{name}:-}}'), "
            f"not a required ('${{{name}:?...}}') one; got {value!r}"
        )
        assert ":?" not in value, (
            f"{name} must not be a required interpolation (that would block startup of "
            f"the whole stack for an optional feature); got {value!r}"
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

    def test_web_service_carries_no_restore_handle_variable(self) -> None:
        """T26 / issue #67. Export/restore are API/CLI-only in this slice --
        the web container has no proxy route for either, so it has no
        legitimate reason to hold either variable, secret or not (the TTL
        is not itself a secret, but a name it should never see either).
        """
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        assert "ADG_RESTORE_HANDLE_SECRET" not in env
        assert "ADG_RESTORE_HANDLE_TTL_SECONDS" not in env

    def test_web_service_carries_the_optional_demo_transparency_variable(self) -> None:
        """T27/T28 / issues #69-#70. Mirrors the api service's own pin: the
        web service carries the SAME variable (a later slice's export/
        restore proxy reads it at request time), as an OPTIONAL
        interpolation, never a NEXT_PUBLIC_* build-time name (that would
        bake it into the client bundle -- see the NEXT_PUBLIC_* pin below).
        """
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        name = "ADG_ENABLE_DEMO_TRANSPARENCY"
        assert name in env, f"web service must carry {name}"
        value = env[name]
        assert value.startswith("${") and value.endswith("}"), (
            f"{name} on the web service must be a compose interpolation; got {value!r}"
        )
        assert ":-" in value and ":?" not in value, (
            f"{name} must use the OPTIONAL interpolation form; got {value!r}"
        )
        assert not name.startswith("NEXT_PUBLIC_")

    def test_web_service_carries_the_optional_demo_vault_explorer_variable(self) -> None:
        """T29 / issue #72. Mirrors the api service's own pin above; not yet
        proxied by any web route in this backend-only stage, but carried
        through so a later web slice does not need a second compose change.
        """
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        name = "ADG_ENABLE_DEMO_VAULT_EXPLORER"
        assert name in env, f"web service must carry {name}"
        value = env[name]
        assert value.startswith("${") and value.endswith("}"), (
            f"{name} on the web service must be a compose interpolation; got {value!r}"
        )
        assert ":-" in value and ":?" not in value, (
            f"{name} must use the OPTIONAL interpolation form; got {value!r}"
        )
        assert not name.startswith("NEXT_PUBLIC_")

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

    def test_web_service_healthcheck_targets_api_ready_not_api_health(self) -> None:
        """T25 review finding 2: the web container's own healthcheck must
        hit its ``/api/ready`` proxy route (which tracks the real API's
        ``/ready``), not ``/api/health`` -- so web's reported health tracks
        whether the API is actually ready, not merely alive.
        """
        web = _service(_load_compose(), "web")
        command = " ".join(str(part) for part in web["healthcheck"]["test"])
        assert "/api/ready" in command, f"web healthcheck must target /api/ready; got: {command!r}"
        assert "/api/health" not in command, (
            f"web healthcheck must not target /api/health; got: {command!r}"
        )

    def test_web_service_publishes_exactly_one_host_port(self) -> None:
        web = _service(_load_compose(), "web")
        assert web.get("ports"), "the web service must publish a host port"
        assert len(web["ports"]) == 1

    def test_web_service_port_binds_loopback_only(self) -> None:
        """Finding 1: a direct ``http://<public-ip>:3000`` connection must
        bypass Caddy/TLS entirely unless the published port is bound to
        ``127.0.0.1`` specifically. Compose's default (no host IP, or
        ``0.0.0.0``) publishes on every host interface, including a public
        one -- this is the defect a hosted deployment must not ship with.
        """
        web = _service(_load_compose(), "web")
        ports = web.get("ports") or []
        assert len(ports) == 1
        entry = _parse_port_entry(ports[0])
        assert entry.host_ip == "127.0.0.1", (
            f"the web service's published port must be bound to 127.0.0.1 only; got "
            f"host_ip={entry.host_ip!r} (entry: {ports[0]!r})"
        )

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


class TestCaddyServicePorts:
    """The optional ``tls`` profile's reverse proxy is the only service
    meant to be reachable from a public interface at all -- and only on the
    standard TLS-adjacent ports.
    """

    def test_caddy_service_publishes_exactly_80_and_443(self) -> None:
        compose = _load_compose()
        caddy = compose["services"].get("caddy")
        assert caddy is not None, "compose.demo.yaml must define a caddy service"
        ports = caddy.get("ports") or []
        published_targets = {_parse_port_entry(entry).published for entry in ports}
        assert published_targets == {"80", "443"}, (
            f"the caddy service must publish exactly ports 80 and 443; got {published_targets!r}"
        )


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

    def test_api_dockerfile_does_not_bake_demo_transparency_at_build_time(self) -> None:
        """T27/T28 / issues #69-#70. Like ``ADG_API_BASE_URL`` on web, this
        must be read at container RUNTIME (via compose interpolation), never
        fixed as a build-time ``ENV``/``ARG`` -- a build-time default would
        freeze the flag into the image regardless of what a deployer
        configures in their environment/.env file.
        """
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(
                ("ENV ADG_ENABLE_DEMO_TRANSPARENCY", "ARG ADG_ENABLE_DEMO_TRANSPARENCY")
            ):
                pytest.fail(
                    f"ADG_ENABLE_DEMO_TRANSPARENCY must not be a build-time ENV/ARG: {stripped!r}"
                )

    def test_api_dockerfile_does_not_bake_demo_vault_explorer_at_build_time(self) -> None:
        """T29 / issue #72. Mirrors the demo-transparency pin above: must be
        read at container RUNTIME via compose interpolation, never fixed as
        a build-time ENV/ARG.
        """
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(
                ("ENV ADG_ENABLE_DEMO_VAULT_EXPLORER", "ARG ADG_ENABLE_DEMO_VAULT_EXPLORER")
            ):
                pytest.fail(
                    f"ADG_ENABLE_DEMO_VAULT_EXPLORER must not be a build-time ENV/ARG: {stripped!r}"
                )

    def test_api_dockerfile_healthcheck_targets_ready_not_health(self) -> None:
        """T25 review finding 2: the image's own ``HEALTHCHECK`` -- used
        whenever the image runs outside ``compose.demo.yaml`` too -- must
        probe ``/ready``, not ``/health``, for the same reason
        ``compose.demo.yaml``'s own healthcheck must.
        """
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        urlopen_lines = [
            line
            for line in text.splitlines()
            if "urlopen(" in line and not line.strip().startswith("#")
        ]
        assert urlopen_lines, "api.Dockerfile's HEALTHCHECK CMD must call urlopen(...)"
        for line in urlopen_lines:
            assert "/ready" in line, f"api.Dockerfile HEALTHCHECK must target /ready: {line!r}"
            assert "/health" not in line, (
                f"api.Dockerfile HEALTHCHECK must not target /health: {line!r}"
            )

    def test_api_dockerfile_runs_as_non_root(self) -> None:
        text = _API_DOCKERFILE_PATH.read_text(encoding="utf-8")
        assert "USER " in text, "api.Dockerfile must switch to a non-root USER"
        assert "USER root" not in text.splitlines()[-5:]

    def test_web_dockerfile_healthcheck_targets_api_ready_not_api_health(self) -> None:
        """T25 review finding 2: mirrors the api.Dockerfile check above for
        the web image's own ``HEALTHCHECK``.
        """
        text = _WEB_DOCKERFILE_PATH.read_text(encoding="utf-8")
        fetch_lines = [
            line
            for line in text.splitlines()
            if "fetch(" in line and not line.strip().startswith("#")
        ]
        assert fetch_lines, "web/Dockerfile's HEALTHCHECK CMD must call fetch(...)"
        for line in fetch_lines:
            assert "/api/ready" in line, (
                f"web/Dockerfile HEALTHCHECK must target /api/ready: {line!r}"
            )
            assert "/api/health" not in line, (
                f"web/Dockerfile HEALTHCHECK must not target /api/health: {line!r}"
            )

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

    def test_web_dockerfile_does_not_bake_demo_transparency_at_build_time(self) -> None:
        text = _WEB_DOCKERFILE_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(
                ("ENV ADG_ENABLE_DEMO_TRANSPARENCY", "ARG ADG_ENABLE_DEMO_TRANSPARENCY")
            ):
                pytest.fail(
                    f"ADG_ENABLE_DEMO_TRANSPARENCY must not be a build-time ENV/ARG: {stripped!r}"
                )

    def test_web_dockerfile_does_not_bake_demo_vault_explorer_at_build_time(self) -> None:
        text = _WEB_DOCKERFILE_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(
                ("ENV ADG_ENABLE_DEMO_VAULT_EXPLORER", "ARG ADG_ENABLE_DEMO_VAULT_EXPLORER")
            ):
                pytest.fail(
                    f"ADG_ENABLE_DEMO_VAULT_EXPLORER must not be a build-time ENV/ARG: {stripped!r}"
                )

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


_WEB_ROOT = _REPO_ROOT / "web"
_WEB_EXCLUDED_DIR_NAMES = {"node_modules", ".next"}


def _web_source_files() -> list[Path]:
    files: list[Path] = []
    for path in _WEB_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _WEB_EXCLUDED_DIR_NAMES for part in path.relative_to(_WEB_ROOT).parts):
            continue
        if path.suffix == ".tsbuildinfo":
            # A generated TypeScript incremental-build cache, not source: it
            # embeds absolute file paths (e.g. this very route file's own
            # path) as JSON strings, which would otherwise read as a false
            # positive "reference" to an upstream path below.
            continue
        files.append(path)
    return files


class TestWebExportRestoreIsGated:
    """T27/T28 (issues #69-#70) supersede ADR-0002's original decision
    (`docs/adr/0002-deferred-restore-handles.md`) that export/restore stay
    API/CLI-only: this is the deliberate removal that class's own docstring
    called for -- a UI slice now proxies both routes, but ONLY behind the
    server-side `ADG_ENABLE_DEMO_TRANSPARENCY` gate
    (`web/lib/demoTransparency.ts`), which defaults to disabled. This is a
    static, repository-wide pin rather than a behavioral one specifically so
    it also reaches code that has not been written yet: a future change that
    adds another export/restore-referencing file, or reorders a route
    handler so the gate check no longer runs first, trips this without
    needing a matching behavioral test to also be written correctly.
    """

    def test_web_app_api_directory_exists(self) -> None:
        api_dir = _WEB_ROOT / "app" / "api"
        assert api_dir.is_dir(), (
            f"expected web API route directory at {api_dir}; if the web app has been "
            "restructured, update this pin rather than let it silently pass"
        )

    def test_export_and_restore_routes_check_the_gate_before_any_proxy_call(self) -> None:
        api_dir = _WEB_ROOT / "app" / "api"
        gated_routes = [
            route_file
            for route_file in api_dir.rglob("route.ts")
            if "documents/export" in route_file.relative_to(api_dir).as_posix()
            or "documents/restore" in route_file.relative_to(api_dir).as_posix()
        ]
        assert len(gated_routes) == 2, (
            "expected exactly one route.ts for documents/export and one for "
            f"documents/restore; found {gated_routes!r}"
        )

        for route_file in gated_routes:
            text = route_file.read_text(encoding="utf-8")
            assert "@/lib/demoTransparency" in text, (
                f"{route_file} must import the gate from @/lib/demoTransparency"
            )
            gate_call_index = text.find("isDemoTransparencyEnabled(")
            assert gate_call_index != -1, f"{route_file} must call isDemoTransparencyEnabled(...)"

            proxy_call_indices = [
                index
                for marker in ("proxyMultipartPost(", "proxyJsonPost(", "proxyGet(")
                if (index := text.find(marker)) != -1
            ]
            assert proxy_call_indices, f"{route_file} must forward to a proxy* call when enabled"
            assert gate_call_index < min(proxy_call_indices), (
                f"{route_file} must check isDemoTransparencyEnabled(...) BEFORE calling any "
                "proxy* function -- a disabled gate must make zero upstream calls"
            )

    def test_only_the_two_gated_routes_and_the_client_reference_the_paths(self) -> None:
        api_dir = _WEB_ROOT / "app" / "api"
        allowed = {
            (api_dir / "documents" / "export" / "route.ts").resolve(),
            (api_dir / "documents" / "restore" / "route.ts").resolve(),
            (_WEB_ROOT / "lib" / "api.ts").resolve(),
        }
        offenders = []
        for path in _web_source_files():
            if path.name.endswith((".test.ts", ".test.tsx")):
                continue
            if path.resolve() in allowed:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "/documents/export" in text or "/documents/restore" in text:
                offenders.append(path)
        assert not offenders, (
            "only the export/restore route handlers and lib/api.ts may reference "
            f"/documents/export or /documents/restore outside tests: {offenders!r}"
        )

    def test_no_file_references_next_public_demo_transparency_or_other_secrets(self) -> None:
        forbidden = (
            "NEXT_PUBLIC_ADG_ENABLE_DEMO_TRANSPARENCY",
            "ADG_RESTORE_HANDLE_SECRET",
            "ADG_PREVIEW_CONFIRMATION_SECRET",
        )
        offenders = []
        for path in _web_source_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(name in text for name in forbidden):
                offenders.append(path)
        assert not offenders, f"no file under web/ may reference {forbidden!r}: {offenders!r}"

    def test_demo_features_route_declares_force_dynamic(self) -> None:
        features_route = _WEB_ROOT / "app" / "api" / "demo" / "features" / "route.ts"
        assert features_route.is_file(), f"expected {features_route} to exist"
        text = features_route.read_text(encoding="utf-8")
        assert re.search(r'export const dynamic = ["\']force-dynamic["\'];', text), (
            f'{features_route} must declare `export const dynamic = "force-dynamic";` -- '
            "otherwise next build may prerender it and bake the build-time env into the image"
        )


class TestWebVaultExplorerIsGated:
    """T29 / issue #72, mirroring ``TestWebExportRestoreIsGated`` above: the
    vault explorer route.ts proxies ``POST /demo/vault-explorer`` only behind
    the server-side ``ADG_ENABLE_DEMO_VAULT_EXPLORER`` gate
    (``web/lib/demoVaultExplorer.ts``), which defaults to disabled. Same
    static, repository-wide posture for the same reason: it also reaches
    code that has not been written yet.
    """

    def test_vault_explorer_route_exists(self) -> None:
        route_file = _WEB_ROOT / "app" / "api" / "demo" / "vault-explorer" / "route.ts"
        assert route_file.is_file(), f"expected {route_file} to exist"

    def test_vault_explorer_route_checks_the_gate_before_any_proxy_call(self) -> None:
        route_file = _WEB_ROOT / "app" / "api" / "demo" / "vault-explorer" / "route.ts"
        text = route_file.read_text(encoding="utf-8")

        assert "@/lib/demoVaultExplorer" in text, (
            f"{route_file} must import the gate from @/lib/demoVaultExplorer"
        )
        gate_call_index = text.find("isDemoVaultExplorerEnabled(")
        assert gate_call_index != -1, f"{route_file} must call isDemoVaultExplorerEnabled(...)"

        proxy_call_indices = [
            index
            for marker in ("proxyMultipartPost(", "proxyJsonPost(", "proxyGet(")
            if (index := text.find(marker)) != -1
        ]
        assert proxy_call_indices, f"{route_file} must forward to a proxy* call when enabled"
        assert gate_call_index < min(proxy_call_indices), (
            f"{route_file} must check isDemoVaultExplorerEnabled(...) BEFORE calling any "
            "proxy* function -- a disabled gate must make zero upstream calls"
        )

    def test_only_the_route_and_the_client_reference_the_path(self) -> None:
        api_dir = _WEB_ROOT / "app" / "api"
        allowed = {
            (api_dir / "demo" / "vault-explorer" / "route.ts").resolve(),
            (_WEB_ROOT / "lib" / "api.ts").resolve(),
        }
        offenders = []
        for path in _web_source_files():
            if path.name.endswith((".test.ts", ".test.tsx")):
                continue
            if path.resolve() in allowed:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "/demo/vault-explorer" in text:
                offenders.append(path)
        assert not offenders, (
            "only the vault explorer route handler and lib/api.ts may reference "
            f"/demo/vault-explorer outside tests: {offenders!r}"
        )

    def test_no_file_references_next_public_demo_vault_explorer(self) -> None:
        forbidden = ("NEXT_PUBLIC_ADG_ENABLE_DEMO_VAULT_EXPLORER",)
        offenders = []
        for path in _web_source_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(name in text for name in forbidden):
                offenders.append(path)
        assert not offenders, f"no file under web/ may reference {forbidden!r}: {offenders!r}"

    def test_vault_explorer_route_declares_force_dynamic(self) -> None:
        route_file = _WEB_ROOT / "app" / "api" / "demo" / "vault-explorer" / "route.ts"
        assert route_file.is_file(), f"expected {route_file} to exist"
        text = route_file.read_text(encoding="utf-8")
        assert re.search(r'export const dynamic = ["\']force-dynamic["\'];', text), (
            f'{route_file} must declare `export const dynamic = "force-dynamic";` -- '
            "otherwise next build may prerender it and bake the build-time env into the image"
        )
