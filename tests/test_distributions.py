# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import io
import runpy
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest

VERIFIER = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/verify_distributions.py")
)
STEM = "samsarix_orchestration-0.1.0"


def artifacts(tmp_path: Path, *, omit: str = "", extra: str = "") -> tuple[Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests/test_example.py").write_text("", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    with ZipFile(dist / f"{STEM}-py3-none-any.whl", "w") as wheel:
        for package in ("samsarix_orchestration", "helix_orchestration"):
            for name in VERIFIER["PACKAGE_FILES"]:
                wheel.writestr(f"{package}/{name}", "")
        for name in (
            "METADATA",
            "WHEEL",
            "entry_points.txt",
            "top_level.txt",
            "RECORD",
            "licenses/LICENSE",
            "licenses/NOTICE",
            "licenses/TRADEMARKS.md",
        ):
            wheel.writestr(f"{STEM}.dist-info/{name}", "")
        if extra:
            wheel.writestr(extra, "")
    with tarfile.open(dist / f"{STEM}.tar.gz", "w:gz") as sdist:
        for name in VERIFIER["REQUIRED_SOURCE_FILES"] | {"tests/test_example.py"}:
            if name != omit:
                sdist.addfile(tarfile.TarInfo(f"{STEM}/{name}"), io.BytesIO(b""))
    return dist, source


def test_accept_complete_distributions(tmp_path: Path) -> None:
    dist, source = artifacts(tmp_path)
    wheel, sdist, stem = VERIFIER["verify_archives"](dist, source)
    assert wheel.is_file() and sdist.is_file()
    assert stem == STEM


@pytest.mark.parametrize(
    "missing",
    [
        ".github/CODEOWNERS",
        "CONTRIBUTING.md",
        "tests/test_example.py",
        "scripts/verify_distributions.py",
    ],
)
def test_reject_source_archive_missing_required_payload(tmp_path: Path, missing: str) -> None:
    dist, source = artifacts(tmp_path, omit=missing)
    with pytest.raises(ValueError, match="source archive is incomplete"):
        VERIFIER["verify_archives"](dist, source)


@pytest.mark.parametrize("extra", ["samsarix_orchestration/agents/legacy.py", "unexpected.py"])
def test_reject_unadvertised_wheel_modules(tmp_path: Path, extra: str) -> None:
    dist, source = artifacts(tmp_path, extra=extra)
    with pytest.raises(ValueError, match="wheel boundary mismatch"):
        VERIFIER["verify_archives"](dist, source)


def test_reject_stale_artifacts(tmp_path: Path) -> None:
    dist, source = artifacts(tmp_path)
    (dist / "old-version.whl").write_bytes(b"")
    with pytest.raises(ValueError, match="exactly the versioned wheel and sdist"):
        VERIFIER["verify_archives"](dist, source)
