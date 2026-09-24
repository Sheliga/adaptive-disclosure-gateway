"""Static invariants over ``compose.prod.yaml``, the VPS-hosted production
deployment stack (T25 follow-up / hosted advisor URL).

Mirrors ``tests/test_demo_deployment_config.py`` for the parts that still
apply, but pins a different shape in the places production actually
diverges from the demo stack:

- no service ever ``build:``s an image -- the ~2.64 GB api image is built by
  CI and only ever pulled here, because the target VPS is a single-vCPU host
  that cannot build it without OOM-ing;
- ``api``/``web`` reference ``ghcr.io/sheliga/adg-*`` images tagged by a
  required, caller-supplied ``ADG_IMAGE_TAG`` interpolation, never a
  hardcoded/floating tag;
- there is no ``caddy`` service and no ``tls`` profile at all -- TLS
  termination is the host's own nginx, not anything this compose file
  starts;
- ``web`` carries ``ADG_WEB_BASE_PATH`` so it serves under the nginx
  subpath the host already routes (see ``deploy/nginx/``).

These tests never start Docker -- they parse the committed YAML and pin the
security-relevant shape the file must have, exactly like the demo file's own
tests. A hand-authored compose file that builds the image on the host, opens
the api port, forwards a secret to the browser-facing container, or starts a
second TLS terminator would fail one of these, not merely disagree with a
style preference.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPOSE_PATH = _REPO_ROOT / "compose.prod.yaml"

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
    host_ip: str | None
    published: str | None
    target: str


#: See test_demo_deployment_config.py's identical constant for why
#: interpolations are masked before splitting on ':'.
_INTERPOLATION_RE = re.compile(r"\$\{[^}]*\}")


def _parse_port_entry(entry: object) -> _PublishedPort:
    if isinstance(entry, dict):
        return _PublishedPort(
            host_ip=entry.get("host_ip"),
            published=str(entry["published"]) if entry.get("published") is not None else None,
            target=str(entry["target"]),
        )
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
    def test_compose_prod_file_exists(self) -> None:
        assert _COMPOSE_PATH.is_file(), "compose.prod.yaml must exist at the repository root"

    def test_compose_prod_is_valid_yaml_with_api_and_web_services(self) -> None:
        compose = _load_compose()
        assert "api" in compose["services"]
        assert "web" in compose["services"]


class TestNoServiceBuildsOnHost:
    """The central point of the production compose file: the ~2.64 GB api
    image (torch + Docling) cannot be built on the 1-vCPU target VPS without
    OOM-ing. Every image must be built by CI and only pulled here.
    """

    def test_no_service_declares_a_build_key(self) -> None:
        compose = _load_compose()
        offenders = [
            name for name, service in compose["services"].items() if "build" in (service or {})
        ]
        assert not offenders, f"no service may declare 'build:' in compose.prod.yaml: {offenders!r}"

    def test_api_and_web_reference_ghcr_images(self) -> None:
        compose = _load_compose()
        api_image = _service(compose, "api").get("image", "")
        web_image = _service(compose, "web").get("image", "")
        assert api_image.startswith("ghcr.io/sheliga/adg-api"), (
            f"api service must reference a ghcr.io/sheliga/adg-api image; got {api_image!r}"
        )
        assert web_image.startswith("ghcr.io/sheliga/adg-web"), (
            f"web service must reference a ghcr.io/sheliga/adg-web image; got {web_image!r}"
        )

    def test_image_tag_is_a_required_interpolation(self) -> None:
        """The tag must be caller-supplied (``ADG_IMAGE_TAG``), never a
        hardcoded or floating default -- a silent ``:latest`` default would
        make a redeploy non-reproducible and could roll back to whatever CI
        last pushed without anyone intending it.
        """
        compose = _load_compose()
        for name in ("api", "web"):
            image = _service(compose, name)["image"]
            assert "${ADG_IMAGE_TAG:?" in image, (
                f"{name} service image must interpolate a required ADG_IMAGE_TAG; got {image!r}"
            )


class TestApiServiceSecurity:
    def test_api_service_publishes_no_host_port(self) -> None:
        api = _service(_load_compose(), "api")
        assert not api.get("ports"), "the api service must not publish a host port"

    def test_api_service_has_no_volumes(self) -> None:
        api = _service(_load_compose(), "api")
        assert not api.get("volumes"), "the api service must not mount any volume"

    def test_api_service_has_a_healthcheck(self) -> None:
        api = _service(_load_compose(), "api")
        assert api.get("healthcheck"), "the api service must define a healthcheck"

    def test_api_service_healthcheck_targets_ready_not_health(self) -> None:
        api = _service(_load_compose(), "api")
        command = " ".join(str(part) for part in api["healthcheck"]["test"])
        assert "/ready" in command, f"api healthcheck must target /ready; got: {command!r}"
        assert "/health" not in command, (
            f"api healthcheck must not target /health; got: {command!r}"
        )

    def test_secret_named_variables_on_api_are_interpolations_not_literals(self) -> None:
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
        api = _service(_load_compose(), "api")
        env = _environment_mapping(api)
        assert "ADG_PROVIDER" in env
        assert ":?" in env["ADG_PROVIDER"], (
            "ADG_PROVIDER must use the compose required-variable interpolation "
            "form ('${ADG_PROVIDER:?...}'), never a silent default"
        )


class TestWebServiceSecurity:
    def test_web_service_carries_no_secret_named_variable(self) -> None:
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        for name in _SECRET_ENV_VAR_NAMES:
            assert name not in env, f"web service must not carry {name}"

    def test_web_service_has_no_next_public_variable(self) -> None:
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
        """Production's nginx (not this compose file) terminates TLS and
        proxies to ``web``. A published port with no host IP (or
        ``0.0.0.0``) would let a caller bypass nginx entirely and reach the
        Next.js container over plain HTTP on any interface -- this is the
        defect a hosted deployment must not ship with.
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
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        assert "ADG_API_BASE_URL" in env
        value = env["ADG_API_BASE_URL"]
        assert "localhost" not in value
        assert "127.0.0.1" not in value
        assert "api" in value

    def test_web_service_carries_the_base_path_variable(self) -> None:
        """The host's nginx routes ``/disclosure-gateway/`` to this
        container (see ``deploy/nginx/``); the web service must be told the
        same path so its own routing/asset URLs agree with the reverse
        proxy in front of it.
        """
        web = _service(_load_compose(), "web")
        env = _environment_mapping(web)
        assert "ADG_WEB_BASE_PATH" in env, "web service must carry ADG_WEB_BASE_PATH"
        value = env["ADG_WEB_BASE_PATH"]
        assert value.startswith("${") and value.endswith("}"), (
            f"ADG_WEB_BASE_PATH must be a compose interpolation; got {value!r}"
        )
        assert "/disclosure-gateway" in value, (
            f"ADG_WEB_BASE_PATH must default to /disclosure-gateway; got {value!r}"
        )


class TestPublicDemoCapabilityPosture:
    """T32.3 / issue #103. This URL is public and unauthenticated
    (docs/advisor-demo.md's "Security stance"), so its posture over the three
    independent demo capabilities is stated in THIS reviewed file, never left
    to whatever the host's ``.env`` happens to contain:

    - INSPECTION on: ``ADG_ENABLE_DEMO_INSPECTION`` is the literal ``"1"`` on
      BOTH services (api populates ``preview.inspection``; web reports it via
      ``/api/demo/features``). It only ever explains, inside one caller's own
      preview response, the content that caller just submitted.
    - TRANSPARENCY (export/restore re-identification) and VAULT_EXPLORER off:
      neither variable is declared on either service at all. Compose passes
      only declared variables into a container, so an operator's ``.env``
      cannot switch either on without editing -- and re-reviewing -- this
      file; both gates then read "unset", i.e. disabled.
    - the restore-handle secret/TTL are not declared on api either: with no
      secret, ``/documents/restore`` and ``/documents/export`` fail closed at
      the API itself (503), a second wall behind the web proxy's own 404.

    The behavioral side (the app actually built from this environment serves
    inspection and refuses the vault explorer/restore routes) is pinned in
    ``tests/test_demo_capability_matrix.py``.
    """

    _OFF_FLAGS = ("ADG_ENABLE_DEMO_TRANSPARENCY", "ADG_ENABLE_DEMO_VAULT_EXPLORER")

    @pytest.mark.parametrize("service_name", ["api", "web"])
    def test_inspection_is_explicitly_enabled(self, service_name: str) -> None:
        env = _environment_mapping(_service(_load_compose(), service_name))
        assert env.get("ADG_ENABLE_DEMO_INSPECTION") == "1", (
            f"{service_name} must set ADG_ENABLE_DEMO_INSPECTION to the literal '1' "
            f"(not an interpolation a host .env could change); got {env.get('ADG_ENABLE_DEMO_INSPECTION')!r}"
        )

    @pytest.mark.parametrize("service_name", ["api", "web"])
    def test_transparency_and_vault_explorer_are_not_declared(self, service_name: str) -> None:
        env = _environment_mapping(_service(_load_compose(), service_name))
        declared = [name for name in self._OFF_FLAGS if name in env]
        assert not declared, (
            f"{service_name} must not declare {declared!r} in compose.prod.yaml: export/restore "
            "and the vault explorer stay off on the public URL, and declaring them would let a "
            "host .env turn them on"
        )

    def test_api_declares_no_restore_handle_configuration(self) -> None:
        env = _environment_mapping(_service(_load_compose(), "api"))
        for name in ("ADG_RESTORE_HANDLE_SECRET", "ADG_RESTORE_HANDLE_TTL_SECONDS"):
            assert name not in env, (
                f"api must not declare {name} in compose.prod.yaml: export/restore is off on "
                "the public URL, so the API itself must also refuse it (503)"
            )

    def test_no_off_flag_appears_anywhere_in_the_file(self) -> None:
        """Belt and braces over the per-service pins: not even a comment-free
        YAML anchor/extension field may reintroduce either variable.
        """
        compose = _load_compose()
        rendered = yaml.safe_dump(compose)
        for name in self._OFF_FLAGS:
            assert name not in rendered, f"{name} must not appear in compose.prod.yaml's data"


class TestNoCaddyOrTlsProfile:
    """TLS termination on the production host is nginx, not Caddy -- this
    compose file must not start a second TLS terminator or define the
    ``tls`` profile the demo file uses for its own Caddy service.
    """

    def test_no_caddy_service(self) -> None:
        compose = _load_compose()
        assert "caddy" not in compose["services"]

    def test_no_service_declares_the_tls_profile(self) -> None:
        compose = _load_compose()
        for name, service in compose["services"].items():
            profiles = (service or {}).get("profiles") or []
            assert "tls" not in profiles, f"{name} must not declare the tls profile"
