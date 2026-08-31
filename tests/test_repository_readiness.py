# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_public_support_and_security_metadata_are_complete() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    urls = project["urls"]

    assert urls["Security"].endswith("/security/policy")
    assert urls["Support"].endswith("/blob/main/SUPPORT.md")
    assert "support@samsarix.com" in (ROOT / "SUPPORT.md").read_text(encoding="utf-8")
    assert "contact@samsarix.com" in (ROOT / "SUPPORT.md").read_text(encoding="utf-8")


def test_repository_has_structured_contribution_intake() -> None:
    expected = [
        ".github/CODEOWNERS",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/pull_request_template.md",
    ]

    assert all((ROOT / path).is_file() for path in expected)
    config = (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in config
    assert "/security/policy" in config
    assert "@Deathcharge" in (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")


@pytest.mark.parametrize("document", ["README.md", "CONTRIBUTING.md"])
def test_setup_selects_the_virtual_environment_before_installing(document: str) -> None:
    """Creating a venv alone must not be presented as changing the active interpreter."""
    instructions = (ROOT / document).read_text(encoding="utf-8")
    create = instructions.index("python -m venv .venv")
    install = instructions.index("python -m pip install")
    assert create < instructions.index("source .venv/bin/activate") < install
    assert create < instructions.index(".\\.venv\\Scripts\\Activate.ps1") < install
