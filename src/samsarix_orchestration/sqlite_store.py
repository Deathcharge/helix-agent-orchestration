# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Transactional same-host SQLite checkpoint persistence and inspection."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .checkpoints import MAX_CHECKPOINT_BYTES
from .runtime import WorkflowCheckpoint, WorkflowExecutionError

SQLITE_APPLICATION_ID = 0x53584F52
SQLITE_SCHEMA_VERSION = 1
MAX_LIST_LIMIT = 1_000
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_COLUMNS = (
    ("run_id", "TEXT", 1, 1),
    ("workflow_digest", "TEXT", 1, 0),
    ("input_digest", "TEXT", 1, 0),
    ("saved_at", "TEXT", 1, 0),
    ("step_count", "INTEGER", 1, 0),
    ("checkpoint_bytes", "INTEGER", 1, 0),
    ("checkpoint_json", "TEXT", 1, 0),
)


@dataclass(frozen=True, slots=True)
class CheckpointSummary:
    """Payload-free metadata for one stored checkpoint."""

    run_id: str
    workflow_digest: str
    input_digest: str
    saved_at: str
    successful_steps: int
    checkpoint_bytes: int

    def to_dict(self) -> dict[str, str | int]:
        """Return the stable JSON representation."""
        return {
            "run_id": self.run_id,
            "workflow_digest": self.workflow_digest,
            "input_digest": self.input_digest,
            "saved_at": self.saved_at,
            "successful_steps": self.successful_steps,
            "checkpoint_bytes": self.checkpoint_bytes,
        }


class SqliteCheckpointStore:
    """Persist bounded checkpoints in a transactional same-host SQLite database.

    Connections are short-lived and never shared between threads. WAL permits readers
    during a write, while SQLite serializes writers. Distinct run IDs can progress from
    multiple threads or processes. A logical run still requires one active executor;
    same-run regression or divergent successful results are rejected at commit time.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        max_checkpoint_bytes: int = MAX_CHECKPOINT_BYTES,
        busy_timeout_ms: int = 5_000,
        create: bool = True,
    ) -> None:
        if str(database) == ":memory:":
            raise ValueError("SQLite checkpoint storage requires a filesystem path")
        if max_checkpoint_bytes < 1:
            raise ValueError("max_checkpoint_bytes must be positive")
        if not 1 <= busy_timeout_ms <= 60_000:
            raise ValueError("busy_timeout_ms must be between 1 and 60000")
        self.database = Path(database)
        self.max_checkpoint_bytes = max_checkpoint_bytes
        self.busy_timeout_ms = busy_timeout_ms
        self.create = create
        self._initialized = False
        self._initialization_lock = threading.Lock()

    def load(self, run_id: str) -> WorkflowCheckpoint | None:
        """Load and validate one bounded checkpoint from a read snapshot."""
        _require_run_id(run_id)
        connection = self._open()
        try:
            connection.execute("BEGIN")
            metadata = connection.execute(
                "SELECT checkpoint_bytes, length(CAST(checkpoint_json AS BLOB)) "
                "FROM samsarix_checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if metadata is None:
                connection.commit()
                return None
            declared_bytes, actual_bytes = metadata
            size = _validated_size(declared_bytes, actual_bytes, self.max_checkpoint_bytes)
            row = connection.execute(
                "SELECT checkpoint_json FROM samsarix_checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            connection.commit()
            if row is None or not isinstance(row[0], str):
                raise WorkflowExecutionError("SQLite checkpoint row changed unexpectedly.")
            return self._decode(row[0], run_id=run_id, expected_bytes=size)
        except sqlite3.DatabaseError as exc:
            _rollback(connection)
            raise self._database_error("load", exc) from exc
        except BaseException:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        """Commit a validated checkpoint without regression or divergence."""
        validated = WorkflowCheckpoint.from_dict(checkpoint.to_dict())
        encoded = _encode_checkpoint(validated)
        if len(encoded) > self.max_checkpoint_bytes:
            raise WorkflowExecutionError(
                f"Checkpoint is {len(encoded)} bytes; "
                f"the limit is {self.max_checkpoint_bytes} bytes."
            )
        rendered = encoded.decode("utf-8")
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_size = connection.execute(
                "SELECT checkpoint_bytes, length(CAST(checkpoint_json AS BLOB)) "
                "FROM samsarix_checkpoints WHERE run_id = ?",
                (validated.run_id,),
            ).fetchone()
            if existing_size is not None:
                size = _validated_size(
                    existing_size[0],
                    existing_size[1],
                    self.max_checkpoint_bytes,
                )
                existing_row = connection.execute(
                    "SELECT checkpoint_json FROM samsarix_checkpoints WHERE run_id = ?",
                    (validated.run_id,),
                ).fetchone()
                if existing_row is None or not isinstance(existing_row[0], str):
                    raise WorkflowExecutionError("SQLite checkpoint row changed unexpectedly.")
                existing = self._decode(
                    existing_row[0],
                    run_id=validated.run_id,
                    expected_bytes=size,
                )
                _require_monotonic_progress(existing, validated)

            connection.execute(
                """
                INSERT INTO samsarix_checkpoints (
                    run_id, workflow_digest, input_digest, saved_at, step_count,
                    checkpoint_bytes, checkpoint_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    workflow_digest = excluded.workflow_digest,
                    input_digest = excluded.input_digest,
                    saved_at = excluded.saved_at,
                    step_count = excluded.step_count,
                    checkpoint_bytes = excluded.checkpoint_bytes,
                    checkpoint_json = excluded.checkpoint_json
                """,
                (
                    validated.run_id,
                    validated.workflow_digest,
                    validated.input_digest,
                    validated.saved_at,
                    len(validated.steps),
                    len(encoded),
                    rendered,
                ),
            )
            connection.commit()
        except sqlite3.DatabaseError as exc:
            _rollback(connection)
            raise self._database_error("save", exc) from exc
        except BaseException:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def list_summaries(self, *, limit: int = 50) -> tuple[CheckpointSummary, ...]:
        """List bounded payload-free checkpoint metadata, newest first."""
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
        connection = self._open()
        try:
            rows = connection.execute(
                """
                SELECT run_id, workflow_digest, input_digest, saved_at, step_count,
                       checkpoint_bytes, length(CAST(checkpoint_json AS BLOB))
                FROM samsarix_checkpoints
                ORDER BY saved_at DESC, run_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return tuple(self._summary_from_row(row) for row in rows)
        except sqlite3.DatabaseError as exc:
            raise self._database_error("list", exc) from exc
        finally:
            connection.close()

    def delete(self, run_id: str) -> bool:
        """Delete one explicit run and return whether it existed."""
        _require_run_id(run_id)
        connection = self._open()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM samsarix_checkpoints WHERE run_id = ?", (run_id,)
            )
            deleted = cursor.rowcount == 1
            connection.commit()
            return deleted
        except sqlite3.DatabaseError as exc:
            _rollback(connection)
            raise self._database_error("delete", exc) from exc
        except BaseException:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def _summary_from_row(self, row: tuple[Any, ...]) -> CheckpointSummary:
        if len(row) != 7:
            raise WorkflowExecutionError("SQLite checkpoint summary has an invalid shape.")
        run_id, workflow_digest, input_digest, saved_at, step_count, declared, actual = row
        if not all(isinstance(value, str) for value in row[:4]):
            raise WorkflowExecutionError("SQLite checkpoint summary text is invalid.")
        if not _RUN_ID.fullmatch(run_id):
            raise WorkflowExecutionError("SQLite checkpoint summary run_id is invalid.")
        if not _SHA256.fullmatch(workflow_digest) or not _SHA256.fullmatch(input_digest):
            raise WorkflowExecutionError("SQLite checkpoint summary digests are invalid.")
        if type(step_count) is not int or not 0 <= step_count <= 256:
            raise WorkflowExecutionError("SQLite checkpoint step count is invalid.")
        size = _validated_size(declared, actual, self.max_checkpoint_bytes)
        return CheckpointSummary(
            run_id=run_id,
            workflow_digest=workflow_digest,
            input_digest=input_digest,
            saved_at=saved_at,
            successful_steps=step_count,
            checkpoint_bytes=size,
        )

    def _decode(
        self,
        rendered: str,
        *,
        run_id: str,
        expected_bytes: int,
    ) -> WorkflowCheckpoint:
        encoded = rendered.encode("utf-8")
        if len(encoded) != expected_bytes or len(encoded) > self.max_checkpoint_bytes:
            raise WorkflowExecutionError("SQLite checkpoint byte length is inconsistent.")
        try:
            value = json.loads(rendered)
        except json.JSONDecodeError as exc:
            raise WorkflowExecutionError("SQLite checkpoint is not valid JSON.") from exc
        checkpoint = WorkflowCheckpoint.from_dict(value)
        if checkpoint.run_id != run_id:
            raise WorkflowExecutionError("SQLite checkpoint run_id does not match its row.")
        return checkpoint

    def _open(self) -> sqlite3.Connection:
        self._ensure_initialized()
        self._validate_path(require_exists=True)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._raw_connection()
            self._validate_identity(connection)
            self._validate_schema(connection)
            return connection
        except (OSError, sqlite3.DatabaseError) as exc:
            if connection is not None:
                connection.close()
            raise self._database_error("open", exc) from exc
        except BaseException:
            if connection is not None:
                connection.close()
            raise

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._initialization_lock:
            if self._initialized:
                return
            self._initialize()
            self._initialized = True

    def _initialize(self) -> None:
        self._validate_path(require_exists=not self.create)
        if not self.database.exists():
            try:
                self.database.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise WorkflowExecutionError(
                    f"Cannot create SQLite checkpoint directory {self.database.parent}: {exc}"
                ) from exc
        connection: sqlite3.Connection | None = None
        try:
            was_new = not self.database.exists() or self.database.stat().st_size == 0
            connection = self._raw_connection()
            connection.execute("BEGIN IMMEDIATE")
            application_id = _pragma_int(connection, "application_id")
            if application_id == 0:
                user_tables = connection.execute(
                    "SELECT name FROM sqlite_schema "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if not was_new or user_tables:
                    raise WorkflowExecutionError(
                        "Refusing to initialize an existing unowned SQLite database."
                    )
                connection.execute(f"PRAGMA application_id = {SQLITE_APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {SQLITE_SCHEMA_VERSION}")
                connection.execute(
                    """
                    CREATE TABLE samsarix_checkpoints (
                        run_id TEXT PRIMARY KEY NOT NULL,
                        workflow_digest TEXT NOT NULL,
                        input_digest TEXT NOT NULL,
                        saved_at TEXT NOT NULL,
                        step_count INTEGER NOT NULL CHECK(step_count BETWEEN 0 AND 256),
                        checkpoint_bytes INTEGER NOT NULL CHECK(checkpoint_bytes > 0),
                        checkpoint_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX samsarix_checkpoints_saved_at "
                    "ON samsarix_checkpoints(saved_at DESC, run_id ASC)"
                )
            elif application_id != SQLITE_APPLICATION_ID:
                raise WorkflowExecutionError("SQLite database belongs to another application.")
            connection.commit()
            mode_row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            if mode_row is None or str(mode_row[0]).casefold() != "wal":
                raise WorkflowExecutionError("SQLite database could not enable WAL mode.")
            self._validate_identity(connection)
            self._validate_schema(connection)
        except WorkflowExecutionError:
            if connection is not None:
                _rollback(connection)
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            if connection is not None:
                _rollback(connection)
            raise self._database_error("initialize", exc) from exc
        finally:
            if connection is not None:
                connection.close()

    def _raw_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database,
            timeout=self.busy_timeout_ms / 1_000,
            isolation_level=None,
        )
        try:
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            return connection
        except BaseException:
            connection.close()
            raise

    def _validate_identity(self, connection: sqlite3.Connection) -> None:
        if _pragma_int(connection, "application_id") != SQLITE_APPLICATION_ID:
            raise WorkflowExecutionError("SQLite database application identity is invalid.")
        if _pragma_int(connection, "user_version") != SQLITE_SCHEMA_VERSION:
            raise WorkflowExecutionError(
                f"Unsupported SQLite checkpoint schema; expected version {SQLITE_SCHEMA_VERSION}."
            )

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA table_info(samsarix_checkpoints)").fetchall()
        columns = tuple((row[1], str(row[2]).upper(), row[3], row[5]) for row in rows)
        if columns != _EXPECTED_COLUMNS:
            raise WorkflowExecutionError("SQLite checkpoint table schema is invalid.")

    def _validate_path(self, *, require_exists: bool) -> None:
        if self.database.is_symlink():
            raise WorkflowExecutionError(
                f"Refusing symbolic-link SQLite checkpoint database: {self.database}"
            )
        if require_exists and not self.database.exists():
            raise WorkflowExecutionError(
                f"SQLite checkpoint database does not exist: {self.database}"
            )
        if self.database.exists() and not self.database.is_file():
            raise WorkflowExecutionError(
                f"SQLite checkpoint path is not a regular file: {self.database}"
            )

    def _database_error(self, operation: str, error: BaseException) -> WorkflowExecutionError:
        return WorkflowExecutionError(
            f"Cannot {operation} SQLite checkpoint database {self.database}: {error}"
        )


def _encode_checkpoint(checkpoint: WorkflowCheckpoint) -> bytes:
    return json.dumps(
        checkpoint.to_dict(),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _require_monotonic_progress(
    existing: WorkflowCheckpoint,
    candidate: WorkflowCheckpoint,
) -> None:
    if (
        existing.workflow_digest != candidate.workflow_digest
        or existing.input_digest != candidate.input_digest
    ):
        raise WorkflowExecutionError("SQLite checkpoint identity cannot change for a run.")
    existing_steps = {step.step_id: step for step in existing.steps}
    candidate_steps = {step.step_id: step for step in candidate.steps}
    if not existing_steps.keys() <= candidate_steps.keys():
        raise WorkflowExecutionError("SQLite checkpoint cannot regress successful steps.")
    for step_id, result in existing_steps.items():
        if result.to_dict() != candidate_steps[step_id].to_dict():
            raise WorkflowExecutionError(
                f"SQLite checkpoint contains divergent result for step {step_id!r}."
            )


def _validated_size(declared: Any, actual: Any, maximum: int) -> int:
    if type(declared) is not int or type(actual) is not int or declared != actual:
        raise WorkflowExecutionError("SQLite checkpoint byte length is invalid.")
    if not 1 <= declared <= maximum:
        raise WorkflowExecutionError(
            f"SQLite checkpoint is {declared} bytes; the limit is {maximum} bytes."
        )
    return declared


def _require_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError(
            "run_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}"
        )


def _pragma_int(connection: sqlite3.Connection, name: str) -> int:
    row = connection.execute(f"PRAGMA {name}").fetchone()
    if row is None or type(row[0]) is not int:
        raise WorkflowExecutionError(f"SQLite PRAGMA {name} is invalid.")
    return row[0]


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()


__all__ = [
    "MAX_LIST_LIMIT",
    "SQLITE_APPLICATION_ID",
    "SQLITE_SCHEMA_VERSION",
    "CheckpointSummary",
    "SqliteCheckpointStore",
]
