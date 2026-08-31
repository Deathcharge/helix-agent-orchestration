# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "release.yml"


def test_all_external_actions_use_immutable_commit_pins() -> None:
    action_pattern = re.compile(r"^\s*uses:\s*([^#\s]+)", re.MULTILINE)
    immutable_action = re.compile(r"[^@\s]+@[0-9a-f]{40}")

    actions = [
        action
        for workflow in WORKFLOWS.glob("*.yml")
        for action in action_pattern.findall(workflow.read_text(encoding="utf-8"))
    ]

    assert actions
    assert all(immutable_action.fullmatch(action) for action in actions)


def test_release_requires_versioned_github_release_and_protected_environment() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "types: [published]" in workflow
    assert "workflow_dispatch" not in workflow
    assert "release tag {actual!r} must equal package tag {expected!r}" in workflow
    assert "git merge-base --is-ancestor HEAD origin/main" in workflow
    assert "permissions: {}" in workflow
    assert "cache: pip" not in workflow
    assert "persist-credentials: false" in workflow
    assert "name: pypi" in workflow
    assert "needs: [build, release-assets]" in workflow


def test_release_uses_oidc_without_persistent_registry_credentials() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "attestations: true" in workflow
    assert "skip-existing: false" in workflow
    assert "password:" not in workflow
    assert "PYPI_API_TOKEN" not in workflow
    assert "--clobber" not in workflow


def test_checkout_free_upload_has_explicit_repository_identity() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    upload_job = workflow.split("  release-assets:\n", 1)[1].split("  publish:\n", 1)[0]

    assert "GH_REPO: ${{ github.repository }}" in upload_job
    assert 'gh release upload "$RELEASE_TAG"' in upload_job


def test_release_tests_run_without_signing_or_upload_permissions() -> None:
    """Verification dependencies must not share a runner with release write credentials."""
    command = "python scripts/verify_distributions.py dist"
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert command in (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    build, downstream = release.split("  verify:\n", 1)
    verify, downstream = downstream.split("  release-assets:\n", 1)
    assets = downstream.split("  publish:\n", 1)[0]
    assert command not in build
    assert command in verify
    assert "needs: build" in verify
    assert "contents: read" in verify
    assert ": write" not in verify
    assert "persist-credentials: false" in verify
    assert "needs: [build, verify]" in assets
    assert "actions/download-artifact@" in assets


def test_release_consumers_download_only_the_immutable_build_artifact() -> None:
    """A later job cannot substitute a different upload with the same artifact name."""
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    build, downstream = release.split("  verify:\n", 1)
    assert "artifact-id: ${{ steps.payload.outputs.artifact-id }}" in build
    assert "id: payload\n        uses: actions/upload-artifact@" in build
    assert "name: python-distributions" in build
    assert "name: python-distributions" not in downstream
    for job in ("verify", "release-assets", "publish"):
        # Job headers are indented two spaces; body lines at least four.
        body = re.split(r"\n  [a-z][a-z-]*:\n", release.split(f"  {job}:\n", 1)[1])[0]
        assert "artifact-ids: ${{ needs.build.outputs.artifact-id }}" in body
        assert "merge-multiple: true" in body
