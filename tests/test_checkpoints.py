# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from samsarix_orchestration import (
    JsonDirectoryCheckpointStore,
    StepResult,
    WorkflowCheckpoint,
    WorkflowDefinition,
    WorkflowExecutionError,
    WorkflowRunner,
    WorkflowStep,
)


def one_step_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        name="checkpoint-store-test",
        steps=(WorkflowStep(id="complete", action="complete"),),
    )


def valid_checkpoint_data() -> dict[str, Any]:
    return {
        "version": 1,
        "run_id": "valid-run",
        "workflow_digest": "a" * 64,
        "input_digest": "b" * 64,
        "saved_at": "2026-08-01T00:00:00Z",
        "steps": [
            {
                "step_id": "complete",
                "agent": "local",
                "action": "complete",
                "state": "succeeded",
                "attempts": 1,
                "started_at": "2026-08-01T00:00:00Z",
                "finished_at": "2026-08-01T00:00:01Z",
                "duration_ms": 1.0,
                "output": {"ok": True},
                "error": None,
            }
        ],
    }


@pytest.mark.asyncio
async def test_json_store_round_trips_an_atomic_checkpoint(tmp_path: Path) -> None:
    store = JsonDirectoryCheckpointStore(tmp_path / "checkpoints")
    result = await WorkflowRunner({"complete": lambda _context: {"ok": True}}).run(
        one_step_workflow(),
        {"customer": 42},
        run_id="order-42",
        checkpoint_store=store,
    )

    path = store.path_for("order-42")
    assert path.is_file()
    assert not list(path.parent.glob("*.tmp"))
    checkpoint = store.load("order-42")
    assert checkpoint is not None
    assert checkpoint.run_id == result.run_id
    assert checkpoint.steps[0].output == {"ok": True}
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "order-42"


def test_json_store_rejects_invalid_and_oversized_files(tmp_path: Path) -> None:
    store = JsonDirectoryCheckpointStore(tmp_path, max_bytes=32)
    path = store.path_for("broken")
    path.write_text("{", encoding="utf-8")
    with pytest.raises(WorkflowExecutionError, match="valid UTF-8 JSON"):
        store.load("broken")

    path.write_text("x" * 33, encoding="utf-8")
    with pytest.raises(WorkflowExecutionError, match="limit"):
        store.load("broken")


def test_json_store_configuration_and_run_ids_are_validated(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        JsonDirectoryCheckpointStore(tmp_path, max_bytes=0)
    store = JsonDirectoryCheckpointStore(tmp_path)
    with pytest.raises(ValueError, match="non-empty"):
        store.path_for("")


def test_memory_store_returns_isolated_validated_snapshots() -> None:
    from samsarix_orchestration import InMemoryCheckpointStore

    store = InMemoryCheckpointStore()
    checkpoint = WorkflowCheckpoint.from_dict(valid_checkpoint_data())
    store.save(checkpoint)
    loaded = store.load("valid-run")
    assert loaded is not None
    assert loaded is not checkpoint
    loaded.steps[0].output["ok"] = False
    loaded_again = store.load("valid-run")
    assert loaded_again is not None
    assert loaded_again.steps[0].output == {"ok": True}
    assert store.load("missing") is None


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("version",), 2, "version 1"),
        (("run_id",), "../bad", "run_id"),
        (("workflow_digest",), "bad", "digests"),
        (("saved_at",), 1, "saved_at"),
        (("steps",), {}, "JSON array"),
        (("steps", 0, "state"), "failed", "only successful"),
        (("steps", 0, "attempts"), 0, "invalid successful"),
        (("steps", 0, "duration_ms"), -1, "duration"),
        (("steps", 0, "output"), float("nan"), "finite JSON"),
        (("steps", 0, "error"), {"type": 1}, "error"),
    ],
)
def test_checkpoint_validation_fails_closed(
    path: tuple[str | int, ...],
    value: Any,
    message: str,
) -> None:
    data = valid_checkpoint_data()
    target: Any = data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(WorkflowExecutionError, match=message):
        WorkflowCheckpoint.from_dict(data)


def test_checkpoint_rejects_duplicate_results() -> None:
    data = valid_checkpoint_data()
    data["steps"].append(dict(data["steps"][0]))
    with pytest.raises(WorkflowExecutionError, match="duplicate"):
        WorkflowCheckpoint.from_dict(data)


def test_json_store_rejects_oversized_save_and_non_directory(tmp_path: Path) -> None:
    checkpoint = WorkflowCheckpoint.from_dict(valid_checkpoint_data())
    with pytest.raises(WorkflowExecutionError, match="limit"):
        JsonDirectoryCheckpointStore(tmp_path / "small", max_bytes=10).save(checkpoint)

    not_directory = tmp_path / "file"
    not_directory.write_text("occupied", encoding="utf-8")
    with pytest.raises(WorkflowExecutionError, match="directory"):
        JsonDirectoryCheckpointStore(not_directory).save(checkpoint)


def test_step_result_rejects_missing_fields_and_invalid_shapes() -> None:
    with pytest.raises(WorkflowExecutionError, match="invalid step result"):
        StepResult.from_dict({})
    data = valid_checkpoint_data()["steps"][0]
    data["started_at"] = 1
    with pytest.raises(WorkflowExecutionError, match="start time"):
        StepResult.from_dict(data)
