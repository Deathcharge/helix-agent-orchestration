# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Verify locally built release artifacts, never arbitrary downloaded archives.

Run from a development environment: python scripts/verify_distributions.py dist
This installs test tools in a fresh temporary venv, so package-index access is needed.
No repository credentials, uploads, or runtime dependencies are required.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path
from zipfile import ZipFile

REQUIRED_SOURCE_FILES = {
    "pyproject.toml",
    "MANIFEST.in",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
    "LICENSING.md",
    "NOTICE",
    "TRADEMARKS.md",
    "SECURITY.md",
    "SUPPORT.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".github/CODEOWNERS",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "scripts/verify_distributions.py",
}
PACKAGE_FILES = {
    "__init__.py",
    "__main__.py",
    "actions.py",
    "checkpoints.py",
    "cli.py",
    "events.py",
    "planning.py",
    "py.typed",
    "runtime.py",
    "spec.py",
    "sqlite_store.py",
    "subprocess_actions.py",
}


def verify_archives(dist: Path, source: Path) -> tuple[Path, Path, str]:
    """Reject ambiguous builds, incomplete sdists, and accidental public modules."""
    version = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    stem = f"samsarix_orchestration-{version}"
    wheel = dist / f"{stem}-py3-none-any.whl"
    sdist = dist / f"{stem}.tar.gz"
    if set(dist.iterdir()) != {wheel, sdist}:
        raise ValueError(
            "distribution directory must contain exactly the versioned wheel and sdist"
        )

    with ZipFile(wheel) as archive:
        names = archive.namelist()
    expected = {
        f"{package}/{name}"
        for package in ("samsarix_orchestration", "helix_orchestration")
        for name in PACKAGE_FILES
    }
    expected.update(
        f"{stem}.dist-info/{name}"
        for name in (
            "METADATA",
            "WHEEL",
            "entry_points.txt",
            "top_level.txt",
            "RECORD",
            "licenses/LICENSE",
            "licenses/NOTICE",
            "licenses/TRADEMARKS.md",
        )
    )
    if set(names) != expected or len(names) != len(expected):
        raise ValueError(
            f"wheel boundary mismatch: missing={sorted(expected.difference(names))}; "
            f"unexpected={sorted(set(names).difference(expected))}"
        )

    required = set(REQUIRED_SOURCE_FILES)
    for folder, pattern in (
        ("tests", "*.py"),
        ("examples", "*.py"),
        ("docs", "*.md"),
        ("scripts", "*.py"),
        ("src", "*.py"),
        ("src", "py.typed"),
    ):
        required.update(
            path.relative_to(source).as_posix() for path in (source / folder).rglob(pattern)
        )
    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
    names = [member.name for member in members]
    if len(names) != len(set(names)):
        raise ValueError("source archive contains duplicate paths")
    if any(not (member.isfile() or member.isdir()) for member in members):
        raise ValueError("source archive must contain only regular files and directories")
    available = {member.name for member in members if member.isfile()}
    missing = {f"{stem}/{name}" for name in required}.difference(available)
    if missing:
        raise ValueError(f"source archive is incomplete: {sorted(missing)}")
    return wheel, sdist, stem


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="directory containing only locally built artifacts")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    wheel, sdist, stem = verify_archives(args.dist.resolve(), source)
    print("Archive completeness and wheel boundary: passed", flush=True)

    env = os.environ.copy()
    # Do not let an editable checkout or caller-selected pytest plugins satisfy these tests.
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="samsarix-dist-test-") as directory:
        workspace = Path(directory)
        with tarfile.open(sdist, "r:gz") as archive:
            archive.extractall(workspace / "source", filter="data")
        unpacked = workspace / "source" / stem
        venv = workspace / "venv"
        run([sys.executable, "-I", "-m", "venv", str(venv)], cwd=workspace, env=env)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                f"{wheel}[dev]",
            ],
            cwd=workspace,
            env=env,
        )
        run(
            [
                str(python),
                "-I",
                "-c",
                "import pathlib, sys, samsarix_orchestration as s, helix_orchestration as h; "
                "prefix = pathlib.Path(sys.prefix).resolve(); "
                "assert pathlib.Path(s.__file__).resolve().is_relative_to(prefix); "
                "assert pathlib.Path(h.__file__).resolve().is_relative_to(prefix); "
                "assert s.WorkflowRunner is h.WorkflowRunner; "
                "print('Isolated wheel imports: passed')",
            ],
            cwd=unpacked,
            env=env,
        )
        run([str(python), "-I", "-m", "pytest", "--import-mode=importlib"], cwd=unpacked, env=env)
        for package in ("samsarix_orchestration", "helix_orchestration"):
            run([str(python), "-I", "-m", package, "--version"], cwd=unpacked, env=env)
    print("Distribution round-trip: passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
