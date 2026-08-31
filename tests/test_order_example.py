# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import argparse
import json
import runpy
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "examples/resumable_order_pipeline.py"
EXAMPLE = runpy.run_path(str(SCRIPT))
RECEIPT = {"order_id": "order-42", "total_cents": 2999}
ENCODED = (json.dumps(RECEIPT, sort_keys=True) + "\n").encode()


@pytest.mark.asyncio
async def test_order_resume_reuses_completed_work_and_identical_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The public example must survive a response lost after its file side effect."""
    args = argparse.Namespace(
        state_dir=tmp_path, run_id="order-42", resume=False, fail_after_publish=True
    )
    assert await EXAMPLE["execute"](args) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    receipt = next((tmp_path / "receipts").glob("*.json"))
    original = receipt.read_bytes()
    args.resume = True
    args.fail_after_publish = False
    assert await EXAMPLE["execute"](args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["restored_steps"] == 2
    assert report["steps"][-1]["output"] == {"order_id": "order-42", "total_cents": 2999}
    assert receipt.read_bytes() == original
    assert list((tmp_path / "receipts").iterdir()) == [receipt]


@pytest.mark.asyncio
async def test_order_resume_rejects_conflicting_existing_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A valid but different JSON receipt must not become a successful restored result."""
    args = argparse.Namespace(
        state_dir=tmp_path, run_id="order-42", resume=False, fail_after_publish=True
    )
    assert await EXAMPLE["execute"](args) == 1
    capsys.readouterr()
    receipt = next((tmp_path / "receipts").glob("*.json"))
    conflict = b'{"order_id":"different-order","total_cents":1}\n'
    receipt.write_bytes(conflict)
    args.resume = True
    args.fail_after_publish = False
    assert await EXAMPLE["execute"](args) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed"
    assert report["steps"][-1]["error"]["type"] == "ValueError"
    assert receipt.read_bytes() == conflict


def test_receipt_publication_is_complete_before_destination_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The destination links only to a closed, completely written staging file."""
    destination = tmp_path / "receipt.json"
    link = EXAMPLE["os"].link

    def inspect_link(staged: Path, path: Path) -> None:
        assert path == destination and not path.exists()
        assert staged.read_bytes() == ENCODED
        link(staged, path)

    monkeypatch.setattr(EXAMPLE["os"], "link", inspect_link)
    assert EXAMPLE["_publish_receipt"](destination, RECEIPT) is True
    assert destination.read_bytes() == ENCODED
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("phase", ["fsync", "link"])
def test_receipt_io_failure_leaves_no_destination_or_staging_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    """Failure before publication must leave the destination absent and clean staging."""
    destination = tmp_path / "receipt.json"

    def fail(*args: object) -> None:
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(EXAMPLE["os"], phase, fail)
    with pytest.raises(OSError, match="simulated filesystem failure"):
        EXAMPLE["_publish_receipt"](destination, RECEIPT)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("winner", [ENCODED, b"different", None])
def test_receipt_creation_race_preserves_the_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winner: bytes | None
) -> None:
    """A racing publisher is accepted only if its content matches the expected receipt."""
    destination = tmp_path / "receipt.json"

    def race(staged: Path, path: Path) -> None:
        if winner is not None:
            path.write_bytes(winner)
        raise FileExistsError

    monkeypatch.setattr(EXAMPLE["os"], "link", race)
    if winner == ENCODED:
        assert EXAMPLE["_publish_receipt"](destination, RECEIPT) is False
    else:
        with pytest.raises(ValueError, match="conflicts|changed during publication"):
            EXAMPLE["_publish_receipt"](destination, RECEIPT)
    assert not list(tmp_path.glob(".receipt-*.tmp"))
    if winner is not None:
        assert destination.read_bytes() == winner
    else:
        assert not destination.exists()


def test_concurrent_receipt_publishers_create_only_one_file(tmp_path: Path) -> None:
    """Multiple identical destination writes deduplicate without replacing each other."""
    destination = tmp_path / "receipt.json"
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: EXAMPLE["_publish_receipt"](destination, RECEIPT), range(8))
        )
    assert results.count(True) == 1
    assert destination.read_bytes() == ENCODED
    assert list(tmp_path.iterdir()) == [destination]


def test_receipt_accepts_historical_windows_newline_without_rewriting(tmp_path: Path) -> None:
    """Old write_text receipts remain valid across the atomic-publication upgrade."""
    destination = tmp_path / "receipt.json"
    legacy = ENCODED[:-1] + b"\r\n"
    destination.write_bytes(legacy)
    assert EXAMPLE["_publish_receipt"](destination, RECEIPT) is False
    assert destination.read_bytes() == legacy


def test_receipt_bounds_and_nonregular_destinations_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unbounded or nonregular pre-existing destinations cannot satisfy idempotency."""
    destination = tmp_path / "receipt.json"
    with pytest.raises(ValueError, match="size limit"):
        EXAMPLE["_publish_receipt"](destination, {"oversized": "x" * 4096})
    assert not destination.exists()
    destination.write_bytes(b"x" * 4097)
    with pytest.raises(ValueError, match="conflicts"):
        EXAMPLE["_publish_receipt"](destination, RECEIPT)
    assert destination.stat().st_size == 4097
    destination.unlink()
    destination.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        EXAMPLE["_publish_receipt"](destination, RECEIPT)
    # Windows may not permit creating real symlinks; exercise lstat's type rejection.
    monkeypatch.setattr(Path, "lstat", lambda _: SimpleNamespace(st_mode=stat.S_IFLNK))
    with pytest.raises(ValueError, match="symbolic link"):
        EXAMPLE["_publish_receipt"](destination, RECEIPT)


def test_order_example_cli_failure_and_resume(tmp_path: Path) -> None:
    """The documented copy-paste command works through the real Python entry point."""
    common = [sys.executable, "-I", str(SCRIPT), "--state-dir", str(tmp_path)]
    first = subprocess.run(
        [*common, "--fail-after-publish"], capture_output=True, text=True, timeout=20
    )
    assert first.returncode == 1, first.stderr
    assert json.loads(first.stdout)["status"] == "failed"
    resumed = subprocess.run([*common, "--resume"], capture_output=True, text=True, timeout=20)
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["restored_steps"] == 2
