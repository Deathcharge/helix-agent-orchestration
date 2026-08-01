# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from samsarix_orchestration import (
    SQLITE_APPLICATION_ID,
    SQLITE_SCHEMA_VERSION,
    ActionContext,
    SqliteCheckpointStore,
    WorkflowCheckpoint,
    WorkflowDefinition,
    WorkflowExecutionError,
    WorkflowRunner,
)


def checkpoint_data(
    run_id: str = "run-1",
    *,
    steps: int = 1,
    output: Any = None,
    saved_at: str = "2026-08-01T00:00:00Z",
    workflow_digest: str = "a" * 64,
    input_digest: str = "b" * 64,
) -> dict[str, Any]:
    return {
        "version": 1,
        "run_id": run_id,
        "workflow_digest": workflow_digest,
        "input_digest": input_digest,
        "saved_at": saved_at,
        "steps": [
            {
                "step_id": f"step-{index}",
                "agent": "local",
                "action": "complete",
                "state": "succeeded",
                "attempts": 1,
                "started_at": f"2026-08-01T00:00:0{index}Z",
                "finished_at": f"2026-08-01T00:00:0{index + 1}Z",
                "duration_ms": 1.0,
                "output": output if index == 0 else {"index": index},
                "error": None,
            }
            for index in range(steps)
        ],
    }


def checkpoint(run_id: str = "run-1", **kwargs: Any) -> WorkflowCheckpoint:
    return WorkflowCheckpoint.from_dict(checkpoint_data(run_id, **kwargs))


def raw_update(database: Path, statement: str, parameters: tuple[Any, ...] = ()) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute(statement, parameters)
        connection.commit()
    finally:
        connection.close()


def test_round_trip_and_owned_wal_schema(tmp_path: Path) -> None:
    database = tmp_path / "state" / "runs.db"
    store = SqliteCheckpointStore(database)
    original = checkpoint(output={"secret": "stored"})
    store.save(original)

    assert store.load("run-1") == original
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert connection.execute("PRAGMA application_id").fetchone() == (
            SQLITE_APPLICATION_ID,
        )
        assert connection.execute("PRAGMA user_version").fetchone() == (
            SQLITE_SCHEMA_VERSION,
        )
    finally:
        connection.close()


def test_lists_payload_free_summaries_newest_first_and_deletes(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path / "runs.db")
    store.save(checkpoint("older", output="PRIVATE", saved_at="2026-08-01T00:00:00Z"))
    store.save(checkpoint("newer", output="SECRET", saved_at="2026-08-02T00:00:00Z"))

    summaries = store.list_summaries(limit=1)
    assert len(summaries) == 1
    assert summaries[0].run_id == "newer"
    assert "output" not in summaries[0].to_dict()
    assert "SECRET" not in json.dumps(summaries[0].to_dict())
    assert store.delete("newer") is True
    assert store.delete("newer") is False
    assert store.load("newer") is None


def test_concurrent_distinct_runs_are_committed(tmp_path: Path) -> None:
    database = tmp_path / "runs.db"

    def save(index: int) -> None:
        SqliteCheckpointStore(database).save(
            checkpoint(f"run-{index}", output={"index": index})
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save, range(40)))

    assert {
        summary.run_id
        for summary in SqliteCheckpointStore(database).list_summaries(limit=40)
    } == {
        f"run-{index}" for index in range(40)
    }


@pytest.mark.asyncio
async def test_runner_resumes_a_failed_sqlite_run_without_repeating_success(
    tmp_path: Path,
) -> None:
    calls = {"prepare": 0, "publish": 0}

    def prepare(_context: ActionContext) -> dict[str, bool]:
        calls["prepare"] += 1
        return {"ready": True}

    def publish(context: ActionContext) -> dict[str, str]:
        calls["publish"] += 1
        assert context.dependencies["prepare"] == {"ready": True}
        if calls["publish"] == 1:
            raise RuntimeError("simulated outage")
        return {"status": "published"}

    workflow = WorkflowDefinition.from_dict(
        {
            "version": 1,
            "name": "sqlite-recovery",
            "steps": [
                {"id": "prepare", "action": "prepare"},
                {"id": "publish", "action": "publish", "dependencies": ["prepare"]},
            ],
        }
    )
    store = SqliteCheckpointStore(tmp_path / "runs.db")
    runner = WorkflowRunner({"prepare": prepare, "publish": publish})

    failed = await runner.run(
        workflow,
        {"record": 42},
        run_id="recover-42",
        checkpoint_store=store,
    )
    assert failed.succeeded is False
    resumed = await runner.run(
        workflow,
        {"record": 42},
        run_id="recover-42",
        checkpoint_store=store,
        resume=True,
    )

    assert resumed.succeeded is True
    assert resumed.restored_steps == 1
    assert calls == {"prepare": 1, "publish": 2}


def test_same_run_accepts_monotonic_and_identical_progress(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path / "runs.db")
    first = checkpoint(output={"value": 1})
    store.save(first)
    store.save(first)
    advanced = checkpoint(steps=2, output={"value": 1}, saved_at="2026-08-02T00:00:00Z")
    store.save(advanced)
    assert store.load("run-1") == advanced


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (checkpoint(steps=0), "regress"),
        (checkpoint(output={"value": 2}), "divergent"),
        (checkpoint(workflow_digest="c" * 64), "identity"),
        (checkpoint(input_digest="d" * 64), "identity"),
    ],
)
def test_same_run_rejects_regression_divergence_and_changed_identity(
    tmp_path: Path,
    candidate: WorkflowCheckpoint,
    message: str,
) -> None:
    store = SqliteCheckpointStore(tmp_path / "runs.db")
    store.save(checkpoint(output={"value": 1}))
    with pytest.raises(WorkflowExecutionError, match=message):
        store.save(candidate)


def test_concurrent_divergent_same_run_has_one_winner(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path / "runs.db")
    candidates = [checkpoint(output={"winner": value}) for value in ("a", "b")]

    def save(candidate: WorkflowCheckpoint) -> str:
        try:
            store.save(candidate)
        except WorkflowExecutionError:
            return "rejected"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(save, candidates))

    assert sorted(outcomes) == ["rejected", "saved"]
    loaded = store.load("run-1")
    assert loaded in candidates


@pytest.mark.parametrize("setting", ["application_id", "user_version"])
def test_refuses_wrong_database_identity(tmp_path: Path, setting: str) -> None:
    database = tmp_path / f"wrong-{setting}.db"
    store = SqliteCheckpointStore(database)
    store.list_summaries()
    wrong = 1 if setting == "application_id" else SQLITE_SCHEMA_VERSION + 1
    raw_update(database, f"PRAGMA {setting} = {wrong}")

    with pytest.raises(WorkflowExecutionError, match="another application|Unsupported"):
        SqliteCheckpointStore(database).list_summaries()


def test_refuses_existing_unowned_database_and_changed_schema(tmp_path: Path) -> None:
    unowned = tmp_path / "unowned.db"
    raw_update(unowned, "CREATE TABLE unrelated (value TEXT)")
    with pytest.raises(WorkflowExecutionError, match="unowned"):
        SqliteCheckpointStore(unowned).list_summaries()

    database = tmp_path / "owned.db"
    SqliteCheckpointStore(database).list_summaries()
    raw_update(database, "ALTER TABLE samsarix_checkpoints ADD COLUMN injected TEXT")
    with pytest.raises(WorkflowExecutionError, match="schema"):
        SqliteCheckpointStore(database).list_summaries()


@pytest.mark.parametrize(
    ("statement", "parameters", "message"),
    [
        (
            "UPDATE samsarix_checkpoints SET checkpoint_bytes = checkpoint_bytes + 1",
            (),
            "byte length",
        ),
        (
            "UPDATE samsarix_checkpoints SET checkpoint_json = ?, checkpoint_bytes = 1",
            ("{",),
            "valid JSON",
        ),
    ],
)
def test_rejects_corrupt_checkpoint_payloads(
    tmp_path: Path,
    statement: str,
    parameters: tuple[Any, ...],
    message: str,
) -> None:
    database = tmp_path / "runs.db"
    store = SqliteCheckpointStore(database)
    store.save(checkpoint())
    raw_update(database, statement, parameters)
    with pytest.raises(WorkflowExecutionError, match=message):
        store.load("run-1")


def test_rejects_mismatched_payload_run_id_and_invalid_summary(tmp_path: Path) -> None:
    database = tmp_path / "runs.db"
    store = SqliteCheckpointStore(database)
    store.save(checkpoint())
    rendered = json.dumps(checkpoint_data("another"), separators=(",", ":"), sort_keys=True)
    raw_update(
        database,
        "UPDATE samsarix_checkpoints SET checkpoint_json = ?, checkpoint_bytes = ?",
        (rendered, len(rendered.encode())),
    )
    with pytest.raises(WorkflowExecutionError, match="does not match"):
        store.load("run-1")

    raw_update(database, "UPDATE samsarix_checkpoints SET workflow_digest = 'bad'")
    with pytest.raises(WorkflowExecutionError, match="digests"):
        store.list_summaries()


def test_configuration_paths_limits_and_run_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="filesystem"):
        SqliteCheckpointStore(":memory:")
    with pytest.raises(ValueError, match="positive"):
        SqliteCheckpointStore(tmp_path / "x.db", max_checkpoint_bytes=0)
    with pytest.raises(ValueError, match="between"):
        SqliteCheckpointStore(tmp_path / "x.db", busy_timeout_ms=0)
    with pytest.raises(WorkflowExecutionError, match="does not exist"):
        SqliteCheckpointStore(tmp_path / "missing.db", create=False).list_summaries()
    with pytest.raises(WorkflowExecutionError, match="regular file"):
        SqliteCheckpointStore(tmp_path).list_summaries()

    store = SqliteCheckpointStore(tmp_path / "valid.db")
    with pytest.raises(ValueError, match="limit"):
        store.list_summaries(limit=0)
    with pytest.raises(ValueError, match="run_id"):
        store.load("../escape")
    with pytest.raises(ValueError, match="run_id"):
        store.delete("")


def test_rejects_symlink_and_removed_initialized_database(tmp_path: Path) -> None:
    target = tmp_path / "target.db"
    SqliteCheckpointStore(target).list_summaries()
    link = tmp_path / "link.db"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available")
    with pytest.raises(WorkflowExecutionError, match="symbolic-link"):
        SqliteCheckpointStore(link).list_summaries()

    store = SqliteCheckpointStore(tmp_path / "removed.db")
    store.list_summaries()
    store.database.unlink()
    with pytest.raises(WorkflowExecutionError, match="does not exist"):
        store.list_summaries()


def test_lock_timeout_fails_boundedly(tmp_path: Path) -> None:
    database = tmp_path / "runs.db"
    SqliteCheckpointStore(database).list_summaries()
    lock = sqlite3.connect(database, isolation_level=None)
    try:
        lock.execute("BEGIN IMMEDIATE")
        assert (
            SqliteCheckpointStore(
                database,
                busy_timeout_ms=1,
                create=False,
            ).list_summaries()
            == ()
        )
        with pytest.raises(WorkflowExecutionError, match="locked"):
            SqliteCheckpointStore(database, busy_timeout_ms=1).save(checkpoint())
    finally:
        lock.rollback()
        lock.close()


def test_oversized_save_and_declared_size_are_rejected(tmp_path: Path) -> None:
    database = tmp_path / "runs.db"
    small = SqliteCheckpointStore(database, max_checkpoint_bytes=10)
    with pytest.raises(WorkflowExecutionError, match="limit"):
        small.save(checkpoint())

    store = SqliteCheckpointStore(database)
    store.save(checkpoint())
    raw_update(database, "UPDATE samsarix_checkpoints SET checkpoint_bytes = 999999999")
    with pytest.raises(WorkflowExecutionError, match="byte length"):
        store.load("run-1")
