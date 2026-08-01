# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded checkpoint stores for resumable local workflows."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from .runtime import (
    WorkflowCheckpoint,
    WorkflowExecutionError,
    _require_monotonic_checkpoint,
)

MAX_CHECKPOINT_BYTES = 16_777_216


class InMemoryCheckpointStore:
    """Thread-safe ephemeral checkpoint storage for tests and embedded processes."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, WorkflowCheckpoint] = {}
        self._lock = threading.Lock()

    def load(self, run_id: str) -> WorkflowCheckpoint | None:
        """Load an isolated copy of a checkpoint."""
        with self._lock:
            checkpoint = self._checkpoints.get(run_id)
            if checkpoint is None:
                return None
            return WorkflowCheckpoint.from_dict(copy.deepcopy(checkpoint.to_dict()))

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        """Replace the latest checkpoint for a run."""
        validated = WorkflowCheckpoint.from_dict(copy.deepcopy(checkpoint.to_dict()))
        with self._lock:
            existing = self._checkpoints.get(checkpoint.run_id)
            if existing is not None:
                _require_monotonic_checkpoint(existing, validated)
            self._checkpoints[checkpoint.run_id] = validated


class JsonDirectoryCheckpointStore:
    """Persist one bounded, atomic JSON checkpoint file per run.

    Run identifiers are hashed for filenames, preventing path traversal and keeping
    filesystem naming rules out of the public run-id contract. A run should have only
    one active writer; both monotonicity checks and atomic replacement assume that
    application-owned coordination. This store is not a distributed coordination
    primitive.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        max_bytes: int = MAX_CHECKPOINT_BYTES,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.directory = Path(directory)
        self.max_bytes = max_bytes

    def path_for(self, run_id: str) -> Path:
        """Return the deterministic checkpoint path for a run identifier."""
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a non-empty string")
        digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def load(self, run_id: str) -> WorkflowCheckpoint | None:
        """Load and validate a bounded UTF-8 JSON checkpoint."""
        path = self.path_for(run_id)
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise WorkflowExecutionError(f"Cannot inspect checkpoint {path}: {exc}") from exc
        if not path.is_file():
            raise WorkflowExecutionError(f"Checkpoint path is not a regular file: {path}")
        if size > self.max_bytes:
            raise WorkflowExecutionError(
                f"Checkpoint is {size} bytes; the limit is {self.max_bytes} bytes."
            )
        try:
            encoded = path.read_bytes()
        except OSError as exc:
            raise WorkflowExecutionError(f"Cannot read checkpoint {path}: {exc}") from exc
        if len(encoded) > self.max_bytes:
            raise WorkflowExecutionError(
                f"Checkpoint is {len(encoded)} bytes; the limit is {self.max_bytes} bytes."
            )
        try:
            value = json.loads(encoded.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WorkflowExecutionError(f"Checkpoint is not valid UTF-8 JSON: {path}") from exc
        checkpoint = WorkflowCheckpoint.from_dict(value)
        if checkpoint.run_id != run_id:
            raise WorkflowExecutionError("Checkpoint run_id does not match its requested run.")
        return checkpoint

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        """Validate and atomically replace a run's checkpoint."""
        validated = WorkflowCheckpoint.from_dict(checkpoint.to_dict())
        encoded = (
            json.dumps(validated.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if len(encoded) > self.max_bytes:
            raise WorkflowExecutionError(
                f"Checkpoint is {len(encoded)} bytes; the limit is {self.max_bytes} bytes."
            )
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkflowExecutionError(
                f"Cannot create checkpoint directory {self.directory}: {exc}"
            ) from exc
        if not self.directory.is_dir():
            raise WorkflowExecutionError(
                f"Checkpoint directory is not a directory: {self.directory}"
            )

        path = self.path_for(checkpoint.run_id)
        existing = self.load(checkpoint.run_id)
        if existing is not None:
            _require_monotonic_checkpoint(existing, validated)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
