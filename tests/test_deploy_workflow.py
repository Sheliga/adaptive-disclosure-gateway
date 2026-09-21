"""Static invariants over `.github/workflows/deploy.yml`, the workflow that
takes an image tag `publish-images.yml` already pushed to GHCR and rolls it
out on the Hostinger VPS (`srv1994437.hstgr.cloud`) via the Hostinger API's
"Create new project" endpoint (which *replaces* the existing
`disclosure-gateway` Docker Manager project, since `compose.prod.yaml` pins
an explicit `ADG_IMAGE_TAG` and the Hostinger `.../docker/{project}/update`
endpoint would just re-pull that same, already-running tag and do nothing).

Never calls the Hostinger API and never runs the workflow -- parses the
committed YAML and greps its text for the shape CLAUDE.md's "No-leak
invariant" and "Branching and CI" sections require: the API token must never
be echoed into a script body, the demo-transparency/vault-explorer flags
must never be turned on for this public URL, and this workflow must not
touch `test.yml` or `publish-images.yml`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "deploy.yml"
_PUBLISH_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "publish-images.yml"
_TEST_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "test.yml"


def _load_workflow() -> dict:
    with _WORKFLOW_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _workflow_text() -> str:
    return _WORKFLOW_PATH.read_text(encoding="utf-8")


def _on(workflow: dict) -> dict:
    # PyYAML's default (YAML 1.1) resolver parses the bare key `on:` as the
    # boolean True, not the string "on" -- same quirk test_publish_images_workflow.py
    # already works around.
    return workflow.get("on") or workflow.get(True)


def _all_steps(workflow: dict) -> list[dict]:
    steps: list[dict] = []
    for job in workflow.get("jobs", {}).values():
        steps.extend(job.get("steps", []))
    return steps


class TestWorkflowFileExists:
    def test_deploy_workflow_exists(self) -> None:
        assert _WORKFLOW_PATH.is_file(), (
            ".github/workflows/deploy.yml must exist to roll a published image out to "
            "the Hostinger VPS"
        )


class TestTriggers:
    def test_triggers_on_publish_images_completion(self) -> None:
        workflow = _load_workflow()
        on = _on(workflow)
        workflow_run = on.get("workflow_run") or {}
        assert workflow_run.get("workflows") == ["publish-images"], (
            f"must trigger off the publish-images workflow_run event; got {workflow_run!r}"
        )
        assert workflow_run.get("types") == ["completed"], (
            f"must only react to the completed workflow_run type; got {workflow_run!r}"
        )
        assert workflow_run.get("branches") == ["master"], (
            f"must restrict workflow_run to master; got {workflow_run!r}"
        )

    def test_also_supports_manual_dispatch_with_optional_sha_input(self) -> None:
        workflow = _load_workflow()
        on = _on(workflow)
        assert "workflow_dispatch" in on, "workflow must support workflow_dispatch for rollback"
        dispatch = on["workflow_dispatch"] or {}
        inputs = dispatch.get("inputs") or {}
        assert inputs, "workflow_dispatch must expose an input to pin a rollback SHA"
        (input_spec,) = inputs.values()
        assert input_spec.get("required") is not True, (
            "the rollback SHA input must be optional -- omitting it deploys github.sha"
        )

    def test_job_only_runs_on_dispatch_or_successful_publish(self) -> None:
        """The workflow_run event fires for both a successful and a failed
        publish-images run; only a successful one should trigger a deploy.
        """
        workflow = _load_workflow()
        (job,) = workflow["jobs"].values()
        condition = job.get("if", "")
        assert "workflow_dispatch" in condition, (
            f"job condition must allow workflow_dispatch through; got {condition!r}"
        )
        assert "workflow_run" in condition and "conclusion" in condition, (
            f"job condition must gate the workflow_run path on conclusion; got {condition!r}"
        )
        assert "success" in condition, f"job condition must require success; got {condition!r}"

    def test_does_not_alter_publish_images_or_test_workflow(self) -> None:
        assert _PUBLISH_WORKFLOW_PATH.is_file()
        assert _TEST_WORKFLOW_PATH.is_file()
        assert "deploy" not in yaml.safe_load(
            _PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")
        ).get("jobs", {})
        test_text = _TEST_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "hostinger" not in test_text.lower()


class TestPermissionsAndConcurrency:
    def test_declares_minimal_permissions(self) -> None:
        workflow = _load_workflow()
        permissions = workflow.get("permissions")
        assert permissions == {"contents": "read"}, (
            f"deploy.yml must request only contents: read; got {permissions!r}"
        )

    def test_concurrency_serializes_deploys_without_cancelling_in_flight_ones(self) -> None:
        workflow = _load_workflow()
        concurrency = workflow.get("concurrency")
        assert concurrency, "workflow must declare a concurrency group"
        assert isinstance(concurrency.get("group"), str) and concurrency["group"], (
            f"concurrency group must be a fixed, non-empty string; got {concurrency!r}"
        )
        assert concurrency.get("cancel-in-progress") is False, (
            f"an in-flight deploy must never be cancelled mid-rollout -- got {concurrency!r}"
        )


class TestTokenHandling:
    def test_only_hostinger_api_token_secret_is_referenced(self) -> None:
        text = _workflow_text()
        assert "secrets.HOSTINGER_API_TOKEN" in text
        for line in text.splitlines():
            if "secrets." not in line:
                continue
            assert "secrets.HOSTINGER_API_TOKEN" in line, (
                f"deploy.yml must reference only secrets.HOSTINGER_API_TOKEN: {line!r}"
            )

    def test_token_reaches_scripts_only_through_env_not_inline_interpolation(self) -> None:
        """The no-leak invariant (CLAUDE.md) forbids interpolating secret
        material directly into a shell command; it must be passed through an
        `env:` mapping and read back as a shell variable instead, so it never
        appears verbatim in the rendered/logged command line.
        """
        workflow = _load_workflow()
        found_in_env = False
        for step in _all_steps(workflow):
            run = step.get("run", "")
            assert "secrets.HOSTINGER_API_TOKEN" not in run, (
                f"token must not be interpolated directly into a run script: {run!r}"
            )
            env = step.get("env") or {}
            if any("secrets.HOSTINGER_API_TOKEN" in str(v) for v in env.values()):
                found_in_env = True
        job_level_env = {}
        for job in workflow.get("jobs", {}).values():
            job_level_env.update(job.get("env") or {})
        if any("secrets.HOSTINGER_API_TOKEN" in str(v) for v in job_level_env.values()):
            found_in_env = True
        assert found_in_env, "token must be passed into at least one step via env:"

    def test_no_set_dash_x_anywhere(self) -> None:
        text = _workflow_text()
        assert "set -x" not in text, "set -x would echo the token-bearing curl commands verbatim"

    def test_no_ssh_or_scp(self) -> None:
        text = _workflow_text()
        assert "ssh " not in text
        assert "scp " not in text
        assert "ssh-agent" not in text

    def test_no_new_secret_besides_hostinger_api_token(self) -> None:
        text = _workflow_text()
        # Only secrets.HOSTINGER_API_TOKEN may appear (already pinned above);
        # this additionally guards against a secrets-context bulk-dump
        # (`toJSON(secrets)`, `secrets.*`) smuggling other secrets through.
        assert "toJSON(secrets)" not in text
        assert "secrets.*" not in text


class TestComposeContentAndEnvironment:
    def test_ships_compose_prod_yaml_unmodified_via_rawfile(self) -> None:
        text = _workflow_text()
        assert "--rawfile" in text and "compose.prod.yaml" in text, (
            "the API body must be built with jq --rawfile so compose.prod.yaml's bytes "
            "are sent as-is, never string-concatenated into JSON"
        )
        # Scoped to the executed shell (`run:` bodies), not the whole file
        # text -- prose in a header comment is free to use the word "sed"
        # (e.g. inside "based") without a real invocation existing.
        workflow = _load_workflow()
        run_scripts = "\n".join(step.get("run", "") for step in _all_steps(workflow))
        assert "sed " not in run_scripts, "compose.prod.yaml must not be rewritten before sending"
        assert "envsubst" not in run_scripts, "compose.prod.yaml must not be pre-substituted"

    def test_checks_out_the_same_sha_the_images_were_built_from(self) -> None:
        workflow = _load_workflow()
        checkout_steps = [
            step
            for step in _all_steps(workflow)
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]
        assert checkout_steps, "workflow must check out the repository to read compose.prod.yaml"
        assert any("ref" in (step.get("with") or {}) for step in checkout_steps), (
            "checkout must pin an explicit ref matching the deployed image tag, not "
            "whatever the runner defaults to"
        )

    def test_environment_sets_image_tag_and_provider_only(self) -> None:
        text = _workflow_text()
        assert "ADG_IMAGE_TAG=" in text
        assert "ADG_PROVIDER=" in text

    def test_never_enables_demo_transparency_or_vault_explorer(self) -> None:
        """The hosted URL is public and unauthenticated -- compose.prod.yaml's
        own header comment and docs/advisor-demo.md's "Why this defaults
        off" section are explicit that a reachable restore/vault-explorer
        endpoint there is a re-identification oracle.
        """
        text = _workflow_text()
        assert "ADG_ENABLE_DEMO_TRANSPARENCY" not in text
        assert "ADG_ENABLE_DEMO_VAULT_EXPLORER" not in text


class TestNoSshDeployMechanism:
    def test_deploys_exclusively_through_the_hostinger_api(self) -> None:
        text = _workflow_text()
        assert "developers.hostinger.com/api/vps/v1/virtual-machines" in text
        assert "/docker" in text

    def test_does_not_call_the_update_endpoint(self) -> None:
        """update only re-pulls the tags the existing (SHA-pinned) project
        compose already references, so it is a no-op for this deployment --
        create (replace) is the only endpoint that actually changes what
        image tag is running. The header comment is free to explain this
        design decision by naming the endpoint in prose; only an actual
        `run:` invocation of it is forbidden.
        """
        workflow = _load_workflow()
        run_scripts = "\n".join(step.get("run", "") for step in _all_steps(workflow))
        assert "/update" not in run_scripts


class TestVerification:
    def test_verifies_via_api_and_public_ready_endpoint(self) -> None:
        text = _workflow_text()
        assert "/containers" in text, "verification must poll the containers API"
        assert "healthy" in text
        assert "/disclosure-gateway/api/ready" in text, (
            "verification must also request the public readiness endpoint, not just "
            "trust the API-reported container health"
        )
        assert "https://srv1994437.hstgr.cloud" in text
