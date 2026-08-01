# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Stable, privacy-conscious workflow lifecycle events."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


class StepState(StrEnum):
    """Stable lifecycle states for a workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class WorkflowEventKind(StrEnum):
    """Versioned event names emitted during workflow execution."""

    RUN_STARTED = "run_started"
    STEP_RESTORED = "step_restored"
    STEP_ATTEMPT_STARTED = "step_attempt_started"
    STEP_RETRY_SCHEDULED = "step_retry_scheduled"
    STEP_SUCCEEDED = "step_succeeded"
    STEP_FAILED = "step_failed"
    STEP_BLOCKED = "step_blocked"
    STEP_CANCELLED = "step_cancelled"
    CHECKPOINT_SAVED = "checkpoint_saved"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECORDED = "approval_recorded"
    STEP_REJECTED = "step_rejected"
    RUN_PAUSED = "run_paused"
    RUN_REJECTED = "run_rejected"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """One schema-versioned lifecycle observation.

    The event intentionally excludes workflow inputs, parameters, action outputs,
    error messages, dependency values, and idempotency keys. Identifiers and error
    type names remain observable and should still be treated as operational data.
    """

    sequence: int
    kind: WorkflowEventKind
    run_id: str
    workflow: str
    occurred_at: str
    step_id: str | None = None
    attempt: int | None = None
    state: StepState | None = None
    duration_ms: float | None = None
    error_type: str | None = None
    resumed: bool = False
    schema_version: int = 1
    approval_id: str | None = None
    decision: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the stable JSON representation, including explicit nulls."""
        value: dict[str, object] = {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "run_id": self.run_id,
            "workflow": self.workflow,
            "occurred_at": self.occurred_at,
            "step_id": self.step_id,
            "attempt": self.attempt,
            "state": self.state.value if self.state is not None else None,
            "duration_ms": self.duration_ms,
            "error_type": self.error_type,
            "resumed": self.resumed,
        }
        if self.schema_version >= 2:
            value["approval_id"] = self.approval_id
            value["decision"] = self.decision
        return value


EventHandler: TypeAlias = Callable[[WorkflowEvent], None | Awaitable[None]]


__all__ = [
    "EventHandler",
    "StepState",
    "WorkflowEvent",
    "WorkflowEventKind",
]
