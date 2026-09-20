"""Static invariants over `.github/workflows/publish-images.yml`, the CI
workflow that builds and pushes the api/web images to GHCR for
`compose.prod.yaml` to pull.

Never runs the workflow -- parses the committed YAML and pins the shape
CLAUDE.md's "Branching and CI" section requires: `test.yml` stays reserved
for the `develop -> master` integration boundary, and this separate,
`master`-triggered workflow must not silently start running on `develop`
PRs, invent a new secret where `GITHUB_TOKEN` already suffices, or drop the
build cache that keeps the ~2.64 GB api image from rebuilding every layer on
every push.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "publish-images.yml"
_TEST_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "test.yml"


def _load_workflow() -> dict:
    with _WORKFLOW_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


class TestWorkflowFileExists:
    def test_publish_images_workflow_exists(self) -> None:
        assert _WORKFLOW_PATH.is_file(), (
            ".github/workflows/publish-images.yml must exist to publish images for "
            "compose.prod.yaml to pull"
        )


class TestTriggers:
    def test_triggers_on_push_to_master(self) -> None:
        workflow = _load_workflow()
        # PyYAML parses the bare key `on:` as the boolean True.
        on = workflow.get("on") or workflow.get(True)
        assert on is not None, "workflow must declare 'on:' triggers"
        push = on.get("push") or {}
        assert push.get("branches") == ["master"], (
            f"workflow must trigger on push to master only; got {push!r}"
        )

    def test_also_supports_manual_dispatch(self) -> None:
        workflow = _load_workflow()
        on = workflow.get("on") or workflow.get(True)
        assert "workflow_dispatch" in on, "workflow must support workflow_dispatch"

    def test_does_not_trigger_on_pull_request(self) -> None:
        """CLAUDE.md: PRs targeting develop deliberately do not run GitHub
        Actions, and this workflow is not the develop->master integration
        boundary either -- it must never trigger on a pull_request event.
        """
        workflow = _load_workflow()
        on = workflow.get("on") or workflow.get(True)
        assert "pull_request" not in on, "publish-images.yml must not trigger on pull_request"

    def test_does_not_alter_the_existing_test_workflow(self) -> None:
        """This workflow must be additive: `test.yml` remains the only CI
        entrypoint for the develop->master boundary (CLAUDE.md).
        """
        assert _TEST_WORKFLOW_PATH.is_file()
        text = _TEST_WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "publish-images" not in text


class TestPermissionsAndSecrets:
    def test_declares_minimal_permissions(self) -> None:
        workflow = _load_workflow()
        permissions = workflow.get("permissions")
        assert permissions, "workflow must declare explicit 'permissions:'"
        assert permissions.get("packages") == "write", (
            f"workflow must grant packages: write to push to GHCR; got {permissions!r}"
        )
        assert permissions.get("contents") == "read", (
            f"workflow must not request more than contents: read; got {permissions!r}"
        )

    def test_uses_only_the_builtin_github_token_no_new_secret(self) -> None:
        """No new PAT/secret should be introduced for GHCR publish --
        GITHUB_TOKEN with packages: write already suffices.
        """
        text = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "secrets.GITHUB_TOKEN" in text
        assert "secrets." in text
        for line in text.splitlines():
            if "secrets." not in line:
                continue
            assert "secrets.GITHUB_TOKEN" in line, (
                f"workflow must reference only secrets.GITHUB_TOKEN, not a new secret: {line!r}"
            )


class TestImagesAndTags:
    def test_builds_both_api_and_web_images(self) -> None:
        text = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "docker/api.Dockerfile" in text
        assert "web/Dockerfile" in text

    def test_image_references_are_lowercase_ghcr(self) -> None:
        text = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "ghcr.io/sheliga/adg-api" in text
        assert "ghcr.io/sheliga/adg-web" in text
        # GHCR rejects uppercase image path segments outright.
        assert "ghcr.io/Sheliga" not in text

    def test_tags_with_both_sha_and_latest(self) -> None:
        text = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "github.sha" in text
        assert ":latest" in text

    def test_web_build_passes_base_path_build_arg(self) -> None:
        text = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "ADG_WEB_BASE_PATH=/disclosure-gateway" in text

    def test_uses_build_push_action_with_gha_cache(self) -> None:
        text = _WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "docker/build-push-action" in text
        assert "cache-from: type=gha" in text or "cache-from:" in text and "gha" in text
        assert "cache-to:" in text and "gha" in text
