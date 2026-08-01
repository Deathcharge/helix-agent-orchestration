# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded asynchronous execution for validated workflows."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, TypeGuard, TypeVar

from .events import EventHandler, StepState, WorkflowEvent, WorkflowEventKind
from .spec import (
    MAX_APPROVAL_PROMPT_CHARACTERS,
    MAX_STEPS,
    WorkflowDefinition,
    WorkflowStep,
)

MAX_RESULT_BYTES = 1_048_576
ActionHandler = Callable[["ActionContext"], Any | Awaitable[Any]]
CompensationHandler = Callable[["CompensationContext"], Any | Awaitable[Any]]
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_APPROVAL_ACTOR_CHARACTERS = 128
MAX_APPROVAL_REASON_CHARACTERS = 1_000
MAX_TIMESTAMP_CHARACTERS = 64


class WorkflowExecutionError(RuntimeError):
    """Raised before execution when the runtime cannot safely run a workflow."""


class EventDeliveryError(WorkflowExecutionError):
    """Raised when an event handler cannot accept a lifecycle event."""


class ApprovalStatus(StrEnum):
    """Durable state of a pre-action approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalDecisionKind(StrEnum):
    """Supported operator decisions for a pending approval."""

    APPROVE = "approve"
    REJECT = "reject"


class CheckpointPhase(StrEnum):
    """Durable schema-v3 execution phase."""

    FORWARD = "forward"
    COMPENSATING = "compensating"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """One bounded operator decision supplied while resuming a paused run."""

    request_id: str
    decision: ApprovalDecisionKind
    decided_by: str | None = None
    reason: str | None = None

    @classmethod
    def approve(
        cls,
        request_id: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> ApprovalDecision:
        """Create an approval decision."""
        return cls(request_id, ApprovalDecisionKind.APPROVE, decided_by, reason)

    @classmethod
    def reject(
        cls,
        request_id: str,
        *,
        decided_by: str | None = None,
        reason: str | None = None,
    ) -> ApprovalDecision:
        """Create a rejection decision."""
        return cls(request_id, ApprovalDecisionKind.REJECT, decided_by, reason)

    def to_dict(self) -> dict[str, str | None]:
        """Return the stable JSON representation."""
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "decided_by": self.decided_by,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> ApprovalDecision:
        """Validate and restore a decision from finite JSON data."""
        if not isinstance(value, dict) or set(value) != {
            "request_id",
            "decision",
            "decided_by",
            "reason",
        }:
            raise WorkflowExecutionError("Approval decision has an invalid shape.")
        request_id = value["request_id"]
        try:
            decision = ApprovalDecisionKind(value["decision"])
        except (TypeError, ValueError) as exc:
            raise WorkflowExecutionError("Approval decision kind is invalid.") from exc
        decided_by = value["decided_by"]
        reason = value["reason"]
        if not _is_sha256(request_id):
            raise WorkflowExecutionError("Approval decision request_id is invalid.")
        _require_optional_bounded_text(
            decided_by,
            label="Approval decided_by",
            maximum=MAX_APPROVAL_ACTOR_CHARACTERS,
        )
        _require_optional_bounded_text(
            reason,
            label="Approval reason",
            maximum=MAX_APPROVAL_REASON_CHARACTERS,
        )
        return cls(
            request_id=request_id,
            decision=decision,
            decided_by=decided_by,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """A pending or decided approval bound to exact workflow state."""

    request_id: str
    step_id: str
    prompt: str
    context_digest: str
    requested_at: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: str | None = None
    decided_by: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Return the stable checkpoint and report representation."""
        return {
            "request_id": self.request_id,
            "step_id": self.step_id,
            "prompt": self.prompt,
            "context_digest": self.context_digest,
            "requested_at": self.requested_at,
            "status": self.status.value,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: Any) -> ApprovalRecord:
        """Validate and restore an approval record from checkpoint JSON."""
        expected = {
            "request_id",
            "step_id",
            "prompt",
            "context_digest",
            "requested_at",
            "status",
            "decided_at",
            "decided_by",
            "reason",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise WorkflowExecutionError("Checkpoint approval has an invalid shape.")
        request_id = value["request_id"]
        step_id = value["step_id"]
        prompt = value["prompt"]
        context_digest = value["context_digest"]
        requested_at = value["requested_at"]
        try:
            status = ApprovalStatus(value["status"])
        except (TypeError, ValueError) as exc:
            raise WorkflowExecutionError("Checkpoint approval status is invalid.") from exc
        decided_at = value["decided_at"]
        decided_by = value["decided_by"]
        reason = value["reason"]
        if not _is_sha256(request_id) or not _is_sha256(context_digest):
            raise WorkflowExecutionError("Checkpoint approval digests are invalid.")
        if not isinstance(step_id, str) or not _RUN_ID.fullmatch(step_id):
            raise WorkflowExecutionError("Checkpoint approval step_id is invalid.")
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > MAX_APPROVAL_PROMPT_CHARACTERS
        ):
            raise WorkflowExecutionError("Checkpoint approval prompt is invalid.")
        _require_bounded_timestamp(requested_at, label="Checkpoint approval requested_at")
        _require_optional_bounded_text(
            decided_by,
            label="Checkpoint approval decided_by",
            maximum=MAX_APPROVAL_ACTOR_CHARACTERS,
        )
        _require_optional_bounded_text(
            reason,
            label="Checkpoint approval reason",
            maximum=MAX_APPROVAL_REASON_CHARACTERS,
        )
        if status is ApprovalStatus.PENDING:
            if decided_at is not None or decided_by is not None or reason is not None:
                raise WorkflowExecutionError(
                    "Pending checkpoint approval cannot contain decision metadata."
                )
        elif decided_at is None:
            raise WorkflowExecutionError("Decided checkpoint approval needs decided_at.")
        else:
            _require_bounded_timestamp(decided_at, label="Checkpoint approval decided_at")
        return cls(
            request_id=request_id,
            step_id=step_id,
            prompt=prompt,
            context_digest=context_digest,
            requested_at=requested_at,
            status=status,
            decided_at=decided_at,
            decided_by=decided_by,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Data made available to one registered action handler."""

    workflow_name: str
    step: WorkflowStep
    workflow_input: Any
    dependencies: Mapping[str, Any]
    attempt: int
    run_id: str = ""
    idempotency_key: str = ""
    approval: ApprovalRecord | None = None


@dataclass(frozen=True, slots=True)
class CompensationContext:
    """Data supplied to a compensator for one previously successful step."""

    workflow_name: str
    step: WorkflowStep
    workflow_input: Any
    dependencies: Mapping[str, Any]
    output: Any
    attempt: int
    run_id: str
    idempotency_key: str


HandlerContextT = TypeVar("HandlerContextT", ActionContext, CompensationContext)


@dataclass(frozen=True, slots=True)
class StepResult:
    """Serializable terminal result for one workflow step."""

    step_id: str
    agent: str
    action: str
    state: StepState
    attempts: int
    started_at: str | None
    finished_at: str
    duration_ms: float
    output: Any = None
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        return {
            "step_id": self.step_id,
            "agent": self.agent,
            "action": self.action,
            "state": self.state.value,
            "attempts": self.attempts,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "output": self.output,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: Any) -> StepResult:
        """Validate and restore a terminal step result from checkpoint JSON."""
        if not isinstance(value, dict):
            raise WorkflowExecutionError("Checkpoint step results must be JSON objects.")
        try:
            state = StepState(value["state"])
            step_id = value["step_id"]
            agent = value["agent"]
            action = value["action"]
            attempts = value["attempts"]
            started_at = value["started_at"]
            finished_at = value["finished_at"]
            duration_ms = value["duration_ms"]
            output = value.get("output")
            error = value.get("error")
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkflowExecutionError("Checkpoint contains an invalid step result.") from exc
        if not all(isinstance(item, str) for item in (step_id, agent, action, finished_at)):
            raise WorkflowExecutionError("Checkpoint step result identifiers are invalid.")
        if started_at is not None and not isinstance(started_at, str):
            raise WorkflowExecutionError("Checkpoint step start time is invalid.")
        if type(attempts) is not int or attempts < 0:
            raise WorkflowExecutionError("Checkpoint step attempt count is invalid.")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, (int, float))
            or not math.isfinite(duration_ms)
            or duration_ms < 0
        ):
            raise WorkflowExecutionError("Checkpoint step duration is invalid.")
        if error is not None and not (
            isinstance(error, dict)
            and all(isinstance(key, str) and isinstance(item, str) for key, item in error.items())
        ):
            raise WorkflowExecutionError("Checkpoint step error is invalid.")
        try:
            json.dumps(output, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise WorkflowExecutionError("Checkpoint step output is not finite JSON.") from exc
        return cls(
            step_id=step_id,
            agent=agent,
            action=action,
            state=state,
            attempts=attempts,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=float(duration_ms),
            output=output,
            error=error,
        )


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    """Durable forward, approval, and compensation state for one exact workflow input."""

    version: int
    run_id: str
    workflow_digest: str
    input_digest: str
    saved_at: str
    steps: tuple[StepResult, ...]
    approvals: tuple[ApprovalRecord, ...] = ()
    phase: CheckpointPhase = CheckpointPhase.FORWARD
    compensations: tuple[StepResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        value: dict[str, Any] = {
            "version": self.version,
            "run_id": self.run_id,
            "workflow_digest": self.workflow_digest,
            "input_digest": self.input_digest,
            "saved_at": self.saved_at,
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.version >= 2:
            value["approvals"] = [approval.to_dict() for approval in self.approvals]
        if self.version >= 3:
            value["phase"] = self.phase.value
            value["compensations"] = [result.to_dict() for result in self.compensations]
        return value

    @classmethod
    def from_dict(cls, value: Any) -> WorkflowCheckpoint:
        """Validate and restore a workflow checkpoint from decoded JSON."""
        if not isinstance(value, dict):
            raise WorkflowExecutionError("Checkpoint must be a JSON object.")
        version = value.get("version")
        if type(version) is not int or version not in (1, 2, 3):
            raise WorkflowExecutionError("Only checkpoint versions 1, 2, and 3 are supported.")
        if version == 2 and set(value) != {
            "version",
            "run_id",
            "workflow_digest",
            "input_digest",
            "saved_at",
            "steps",
            "approvals",
        }:
            raise WorkflowExecutionError("Checkpoint version 2 has an invalid shape.")
        if version == 3 and set(value) != {
            "version",
            "run_id",
            "workflow_digest",
            "input_digest",
            "saved_at",
            "steps",
            "approvals",
            "phase",
            "compensations",
        }:
            raise WorkflowExecutionError("Checkpoint version 3 has an invalid shape.")
        run_id = value.get("run_id")
        workflow_digest = value.get("workflow_digest")
        input_digest = value.get("input_digest")
        saved_at = value.get("saved_at")
        raw_steps = value.get("steps")
        raw_approvals = value.get("approvals", [])
        raw_compensations = value.get("compensations", [])
        try:
            phase = CheckpointPhase(value.get("phase", CheckpointPhase.FORWARD))
        except (TypeError, ValueError) as exc:
            raise WorkflowExecutionError("Checkpoint phase is invalid.") from exc
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise WorkflowExecutionError("Checkpoint run_id is invalid.")
        if not _is_sha256(workflow_digest) or not _is_sha256(input_digest):
            raise WorkflowExecutionError("Checkpoint identity digests are invalid.")
        if not isinstance(saved_at, str):
            raise WorkflowExecutionError("Checkpoint saved_at is invalid.")
        if not isinstance(raw_steps, list):
            raise WorkflowExecutionError("Checkpoint steps must be a JSON array.")
        if not isinstance(raw_approvals, list) or not isinstance(raw_compensations, list):
            raise WorkflowExecutionError(
                "Checkpoint approvals and compensations must be JSON arrays."
            )
        if any(len(items) > MAX_STEPS for items in (raw_steps, raw_approvals, raw_compensations)):
            raise WorkflowExecutionError(
                f"Checkpoint may contain at most {MAX_STEPS} steps, approvals, and compensations."
            )
        if version == 1 and ("approvals" in value or raw_approvals):
            raise WorkflowExecutionError("Checkpoint version 1 cannot contain approvals.")
        steps = tuple(StepResult.from_dict(step) for step in raw_steps)
        approvals = tuple(ApprovalRecord.from_dict(item) for item in raw_approvals)
        compensations = tuple(StepResult.from_dict(item) for item in raw_compensations)
        if len({step.step_id for step in steps}) != len(steps):
            raise WorkflowExecutionError("Checkpoint contains duplicate step results.")
        terminal_states = {
            StepState.SUCCEEDED,
            StepState.FAILED,
            StepState.BLOCKED,
            StepState.CANCELLED,
            StepState.REJECTED,
        }
        if version >= 3 and any(step.state not in terminal_states for step in steps):
            raise WorkflowExecutionError("Checkpoint contains a non-terminal step result.")
        if version < 3 and any(step.state is not StepState.SUCCEEDED for step in steps):
            raise WorkflowExecutionError("Checkpoints may contain only successful step results.")
        if any(
            step.attempts < 1 or step.started_at is None or step.error is not None
            for step in steps
            if step.state is StepState.SUCCEEDED
        ):
            raise WorkflowExecutionError("Checkpoint contains an invalid successful step result.")
        if version >= 3 and any(
            step.error is None for step in steps if step.state is not StepState.SUCCEEDED
        ):
            raise WorkflowExecutionError("Checkpoint contains an invalid terminal step result.")
        if len({result.step_id for result in compensations}) != len(compensations):
            raise WorkflowExecutionError("Checkpoint contains duplicate compensation results.")
        if any(result.state is not StepState.SUCCEEDED for result in compensations):
            raise WorkflowExecutionError("Checkpoints may contain only successful compensations.")
        if any(
            result.attempts < 1 or result.started_at is None or result.error is not None
            for result in compensations
        ):
            raise WorkflowExecutionError("Checkpoint contains an invalid successful compensation.")
        forward_results = {result.step_id: result for result in steps}
        if any(
            result.step_id not in forward_results
            or forward_results[result.step_id].state is not StepState.SUCCEEDED
            for result in compensations
        ):
            raise WorkflowExecutionError(
                "Checkpoint compensation does not reference a successful forward step."
            )
        if phase is CheckpointPhase.FORWARD and compensations:
            raise WorkflowExecutionError(
                "Forward-phase checkpoint cannot contain compensation results."
            )
        if version < 3 and ("phase" in value or "compensations" in value or compensations):
            raise WorkflowExecutionError(
                "Checkpoint versions 1 and 2 cannot contain compensation state."
            )
        if len({record.request_id for record in approvals}) != len(approvals):
            raise WorkflowExecutionError("Checkpoint contains duplicate approval requests.")
        if len({record.step_id for record in approvals}) != len(approvals):
            raise WorkflowExecutionError("Checkpoint contains duplicate step approvals.")
        return cls(
            version=version,
            run_id=run_id,
            workflow_digest=workflow_digest,
            input_digest=input_digest,
            saved_at=saved_at,
            steps=steps,
            approvals=approvals,
            phase=phase,
            compensations=compensations,
        )


class CheckpointStore(Protocol):
    """Synchronous persistence contract used outside the event loop."""

    def load(self, run_id: str) -> WorkflowCheckpoint | None:
        """Load a checkpoint, or return ``None`` when the run is unknown."""
        ...

    def save(self, checkpoint: WorkflowCheckpoint) -> None:
        """Atomically persist the latest checkpoint for a run."""
        ...


@dataclass(frozen=True, slots=True)
class WorkflowRunResult:
    """Serializable result for a complete or paused workflow invocation."""

    run_id: str
    workflow: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    steps: tuple[StepResult, ...]
    resumed: bool = False
    restored_steps: int = 0
    approvals: tuple[ApprovalRecord, ...] = ()
    schema_version: int = 1
    compensations: tuple[StepResult, ...] = ()
    compensation_status: str = "not_requested"

    @property
    def succeeded(self) -> bool:
        """Whether every step completed successfully."""
        return self.status == "succeeded"

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        value: dict[str, Any] = {
            "run_id": self.run_id,
            "workflow": self.workflow,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "resumed": self.resumed,
            "restored_steps": self.restored_steps,
            "steps": [step.to_dict() for step in self.steps],
        }
        if self.schema_version >= 2:
            value["schema_version"] = self.schema_version
            value["approvals"] = [approval.to_dict() for approval in self.approvals]
        if self.schema_version >= 3:
            value["compensation_status"] = self.compensation_status
            value["compensations"] = [result.to_dict() for result in self.compensations]
        return value


class _EventDispatcher:
    """Serialize event delivery for one run, including concurrent steps."""

    def __init__(self, handlers: tuple[EventHandler, ...], *, schema_version: int = 1) -> None:
        self._handlers = handlers
        self._schema_version = schema_version
        self._sequence = 0
        self._lock = asyncio.Lock()

    async def emit(
        self,
        kind: WorkflowEventKind,
        *,
        run_id: str,
        workflow: str,
        step_id: str | None = None,
        attempt: int | None = None,
        state: StepState | None = None,
        duration_ms: float | None = None,
        error_type: str | None = None,
        resumed: bool = False,
        approval_id: str | None = None,
        decision: str | None = None,
    ) -> None:
        if not self._handlers:
            return
        async with self._lock:
            self._sequence += 1
            event = WorkflowEvent(
                sequence=self._sequence,
                kind=kind,
                run_id=run_id,
                workflow=workflow,
                occurred_at=_utc_now(),
                step_id=step_id,
                attempt=attempt,
                state=state,
                duration_ms=duration_ms,
                error_type=error_type,
                resumed=resumed,
                schema_version=self._schema_version,
                approval_id=approval_id,
                decision=decision,
            )
            for handler in self._handlers:
                try:
                    await self._invoke(handler, event)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    raise EventDeliveryError(
                        f"Event handler failed while delivering {kind.value!r} "
                        f"at sequence {event.sequence}."
                    ) from exc

    @staticmethod
    async def _invoke(handler: EventHandler, event: WorkflowEvent) -> None:
        if inspect.iscoroutinefunction(handler):
            await handler(event)
            return
        result = await asyncio.to_thread(handler, event)
        if inspect.isawaitable(result):
            await result


class WorkflowRunner:
    """Execute dependency-aware workflows using explicitly registered handlers."""

    def __init__(
        self,
        actions: Mapping[str, ActionHandler] | None = None,
        *,
        compensations: Mapping[str, CompensationHandler] | None = None,
        fail_fast: bool = True,
        max_result_bytes: int = MAX_RESULT_BYTES,
        event_handlers: Iterable[EventHandler] | None = None,
    ) -> None:
        if max_result_bytes < 1:
            raise ValueError("max_result_bytes must be positive")
        self._actions: dict[str, ActionHandler] = {}
        self._compensations: dict[str, CompensationHandler] = {}
        self.fail_fast = fail_fast
        self.max_result_bytes = max_result_bytes
        self._event_handlers: list[EventHandler] = []
        for name, handler in (actions or {}).items():
            self.register_action(name, handler)
        for name, compensation_handler in (compensations or {}).items():
            self.register_compensation(name, compensation_handler)
        for event_handler in event_handlers or ():
            self.register_event_handler(event_handler)

    def register_action(self, name: str, handler: ActionHandler) -> None:
        """Register or replace a handler by an explicit action name."""
        if not name or len(name) > 64:
            raise ValueError("Action name must contain 1 to 64 characters.")
        if not callable(handler):
            raise TypeError(f"Handler for {name!r} must be callable.")
        self._actions[name] = handler

    def register_event_handler(self, handler: EventHandler) -> None:
        """Register an ordered, backpressured lifecycle event handler."""
        if not callable(handler):
            raise TypeError("Event handler must be callable.")
        self._event_handlers.append(handler)

    def register_compensation(self, name: str, handler: CompensationHandler) -> None:
        """Register or replace a compensating handler by explicit action name."""
        if not name or len(name) > 64:
            raise ValueError("Compensation name must contain 1 to 64 characters.")
        if not callable(handler):
            raise TypeError(f"Compensation handler for {name!r} must be callable.")
        self._compensations[name] = handler

    async def run(
        self,
        workflow: WorkflowDefinition,
        workflow_input: Any = None,
        *,
        run_id: str | None = None,
        checkpoint_store: CheckpointStore | None = None,
        resume: bool = False,
        approval_decisions: Iterable[ApprovalDecision] | None = None,
    ) -> WorkflowRunResult:
        """Run or resume a workflow and return a terminal-state report.

        Forward recovery reuses successful results whose workflow and input digests match
        exactly. Schema-v3 compensation recovery restores terminal forward state and
        completed compensations. Persistence is at-least-once: effectful handlers must
        honor their context idempotency key because a process can stop after an effect
        succeeds but before its checkpoint saves.
        """
        workflow.require_valid()
        self._require_json_value(workflow_input, label="workflow input")
        raw_decisions = tuple(approval_decisions or ())
        if any(not isinstance(decision, ApprovalDecision) for decision in raw_decisions):
            raise WorkflowExecutionError("approval_decisions must contain ApprovalDecision values.")
        try:
            decisions = tuple(
                ApprovalDecision.from_dict(decision.to_dict()) for decision in raw_decisions
            )
        except AttributeError as exc:
            raise WorkflowExecutionError("Approval decision is invalid.") from exc
        if len({decision.request_id for decision in decisions}) != len(decisions):
            raise WorkflowExecutionError("Approval decisions contain duplicate request IDs.")
        if decisions and not resume:
            raise WorkflowExecutionError("Approval decisions require resume=True.")
        if resume and checkpoint_store is None:
            raise WorkflowExecutionError("resume requires a checkpoint store.")
        if resume and run_id is None:
            raise WorkflowExecutionError("resume requires an explicit run_id.")
        has_approval_gates = any(step.approval is not None for step in workflow.steps)
        has_compensations = any(step.compensation is not None for step in workflow.steps)
        if has_approval_gates and checkpoint_store is None:
            raise WorkflowExecutionError("Approval gates require a checkpoint store.")
        if has_approval_gates and run_id is None:
            raise WorkflowExecutionError("Approval gates require an explicit run_id.")
        if has_compensations and checkpoint_store is None:
            raise WorkflowExecutionError("Compensating actions require a checkpoint store.")
        if has_compensations and run_id is None:
            raise WorkflowExecutionError("Compensating actions require an explicit run_id.")
        effective_run_id = run_id or str(uuid.uuid4())
        if not _RUN_ID.fullmatch(effective_run_id):
            raise WorkflowExecutionError("run_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}.")
        missing = sorted({step.action for step in workflow.steps} - self._actions.keys())
        if missing:
            raise WorkflowExecutionError(
                "No handler registered for action(s): " + ", ".join(missing)
            )
        missing_compensations = sorted(
            {step.compensation.action for step in workflow.steps if step.compensation is not None}
            - self._compensations.keys()
        )
        if missing_compensations:
            raise WorkflowExecutionError(
                "No handler registered for compensation(s): " + ", ".join(missing_compensations)
            )

        started_at = _utc_now()
        started_clock = time.perf_counter()
        dispatcher = _EventDispatcher(
            tuple(self._event_handlers),
            schema_version=workflow.version,
        )
        ordered_steps = {step.id: step for step in workflow.steps}
        pending = set(ordered_steps)
        results: dict[str, StepResult] = {}
        approvals: dict[str, ApprovalRecord] = {}
        compensation_results: dict[str, StepResult] = {}
        phase = CheckpointPhase.FORWARD
        workflow_digest = _json_digest(workflow.to_dict())
        input_digest = _json_digest(workflow_input)
        checkpoint = (
            await self._load_checkpoint(checkpoint_store, effective_run_id)
            if checkpoint_store is not None
            else None
        )
        if resume:
            if checkpoint_store is None:
                raise WorkflowExecutionError("Resume requires a checkpoint store.")
            if checkpoint is None:
                raise WorkflowExecutionError(
                    f"No checkpoint exists for run_id {effective_run_id!r}."
                )
            self._restore_checkpoint(
                checkpoint,
                workflow_digest=workflow_digest,
                input_digest=input_digest,
                ordered_steps=ordered_steps,
                results=results,
                pending=pending,
                approvals=approvals,
                compensations=compensation_results,
                workflow_version=workflow.version,
                run_id=effective_run_id,
            )
            phase = checkpoint.phase
        elif checkpoint is not None:
            raise WorkflowExecutionError(
                f"Checkpoint already exists for run_id {effective_run_id!r}; "
                "resume it or choose a new run_id."
            )
        restored_steps = len(results)
        semaphore = asyncio.Semaphore(workflow.max_concurrency)
        await dispatcher.emit(
            WorkflowEventKind.RUN_STARTED,
            run_id=effective_run_id,
            workflow=workflow.name,
            resumed=resume,
        )
        for step in workflow.steps:
            if step.id in results:
                restored = results[step.id]
                await dispatcher.emit(
                    WorkflowEventKind.STEP_RESTORED,
                    run_id=effective_run_id,
                    workflow=workflow.name,
                    step_id=step.id,
                    attempt=restored.attempts,
                    state=restored.state,
                    duration_ms=restored.duration_ms,
                    resumed=True,
                )
            if step.id in compensation_results:
                restored_compensation = compensation_results[step.id]
                await dispatcher.emit(
                    WorkflowEventKind.COMPENSATION_RESTORED,
                    run_id=effective_run_id,
                    workflow=workflow.name,
                    step_id=step.id,
                    attempt=restored_compensation.attempts,
                    state=StepState.SUCCEEDED,
                    duration_ms=restored_compensation.duration_ms,
                    resumed=True,
                )

        if decisions:
            if phase is not CheckpointPhase.FORWARD:
                raise WorkflowExecutionError(
                    "Approval decisions cannot be applied after compensation starts."
                )
            applied: list[tuple[ApprovalRecord, ApprovalDecision]] = []
            for decision in decisions:
                record = approvals.get(decision.request_id)
                if record is None:
                    raise WorkflowExecutionError(
                        f"Approval request {decision.request_id!r} is not pending for this run."
                    )
                if record.status is not ApprovalStatus.PENDING:
                    raise WorkflowExecutionError(
                        f"Approval request {decision.request_id!r} is already decided."
                    )
                approvals[decision.request_id] = replace(
                    record,
                    status=(
                        ApprovalStatus.APPROVED
                        if decision.decision is ApprovalDecisionKind.APPROVE
                        else ApprovalStatus.REJECTED
                    ),
                    decided_at=_utc_now(),
                    decided_by=decision.decided_by,
                    reason=decision.reason,
                )
                applied.append((record, decision))
            if checkpoint_store is None:
                raise WorkflowExecutionError("Approval decisions require a checkpoint store.")
            await self._save_checkpoint(
                checkpoint_store,
                self._build_checkpoint(
                    workflow,
                    effective_run_id,
                    workflow_digest,
                    input_digest,
                    results,
                    approvals,
                ),
            )
            for record, decision in applied:
                await dispatcher.emit(
                    WorkflowEventKind.APPROVAL_RECORDED,
                    run_id=effective_run_id,
                    workflow=workflow.name,
                    step_id=record.step_id,
                    resumed=True,
                    approval_id=record.request_id,
                    decision=decision.decision.value,
                )
            await dispatcher.emit(
                WorkflowEventKind.CHECKPOINT_SAVED,
                run_id=effective_run_id,
                workflow=workflow.name,
                resumed=True,
            )

        try:
            while pending and phase is CheckpointPhase.FORWARD:
                blocked_ids = [
                    step.id
                    for step in workflow.steps
                    if step.id in pending
                    if any(
                        dependency in results
                        and results[dependency].state is not StepState.SUCCEEDED
                        for dependency in step.dependencies
                    )
                ]
                for step_id in blocked_ids:
                    step = ordered_steps[step_id]
                    blocked = self._terminal_without_run(
                        step,
                        StepState.BLOCKED,
                        "DependencyFailed",
                        "One or more dependencies did not succeed.",
                    )
                    results[step_id] = blocked
                    pending.remove(step_id)
                    await dispatcher.emit(
                        WorkflowEventKind.STEP_BLOCKED,
                        run_id=effective_run_id,
                        workflow=workflow.name,
                        step_id=step.id,
                        state=StepState.BLOCKED,
                        duration_ms=0.0,
                        error_type="DependencyFailed",
                    )

                ready = [
                    step
                    for step in workflow.steps
                    if step.id in pending
                    and all(
                        dependency in results and results[dependency].state is StepState.SUCCEEDED
                        for dependency in step.dependencies
                    )
                ]
                if not ready:
                    if pending:
                        raise WorkflowExecutionError(
                            "Workflow stalled despite successful validation."
                        )
                    break

                denied = [
                    step
                    for step in ready
                    if step.approval is not None
                    and (record := _approval_for_step(approvals, step.id)) is not None
                    and record.status in (ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED)
                ]
                if denied:
                    rejected_ids = {
                        step.id
                        for step in denied
                        if (record := _approval_for_step(approvals, step.id)) is not None
                        and record.status is ApprovalStatus.REJECTED
                    }
                    cancelled_records: list[ApprovalRecord] = []
                    for request_id, record in tuple(approvals.items()):
                        if (
                            record.status is ApprovalStatus.PENDING
                            and record.step_id not in rejected_ids
                        ):
                            cancelled = replace(
                                record,
                                status=ApprovalStatus.CANCELLED,
                                decided_at=_utc_now(),
                                reason="Cancelled because another approval was rejected.",
                            )
                            approvals[request_id] = cancelled
                            cancelled_records.append(cancelled)
                    if cancelled_records:
                        if checkpoint_store is None:
                            raise WorkflowExecutionError(
                                "Approval cancellation requires a checkpoint store."
                            )
                        await self._save_checkpoint(
                            checkpoint_store,
                            self._build_checkpoint(
                                workflow,
                                effective_run_id,
                                workflow_digest,
                                input_digest,
                                results,
                                approvals,
                            ),
                        )
                        for record in cancelled_records:
                            await dispatcher.emit(
                                WorkflowEventKind.APPROVAL_RECORDED,
                                run_id=effective_run_id,
                                workflow=workflow.name,
                                step_id=record.step_id,
                                resumed=resume,
                                approval_id=record.request_id,
                                decision="cancel",
                            )
                        await dispatcher.emit(
                            WorkflowEventKind.CHECKPOINT_SAVED,
                            run_id=effective_run_id,
                            workflow=workflow.name,
                            resumed=resume,
                        )
                    for step in workflow.steps:
                        if step.id not in pending:
                            continue
                        if step.id in rejected_ids:
                            record = _approval_for_step(approvals, step.id)
                            if record is None:
                                raise WorkflowExecutionError(
                                    f"Rejected step {step.id!r} has no approval record."
                                )
                            result = self._terminal_without_run(
                                step,
                                StepState.REJECTED,
                                "ApprovalRejected",
                                record.reason or "The approval request was rejected.",
                                finished_at=record.decided_at,
                            )
                            results[step.id] = result
                            pending.remove(step.id)
                            await dispatcher.emit(
                                WorkflowEventKind.STEP_REJECTED,
                                run_id=effective_run_id,
                                workflow=workflow.name,
                                step_id=step.id,
                                state=StepState.REJECTED,
                                error_type="ApprovalRejected",
                                resumed=resume,
                                approval_id=record.request_id,
                                decision=ApprovalDecisionKind.REJECT.value,
                            )
                        else:
                            blocked = self._terminal_without_run(
                                step,
                                StepState.BLOCKED,
                                "ApprovalRejected",
                                "Not started because an approval was rejected.",
                            )
                            results[step.id] = blocked
                            pending.remove(step.id)
                            await dispatcher.emit(
                                WorkflowEventKind.STEP_BLOCKED,
                                run_id=effective_run_id,
                                workflow=workflow.name,
                                step_id=step.id,
                                state=StepState.BLOCKED,
                                error_type="ApprovalRejected",
                                resumed=resume,
                            )
                    break

                waiting: list[ApprovalRecord] = []
                created_approval = False
                for step in ready:
                    if step.approval is None:
                        continue
                    dependencies = {
                        dependency: results[dependency].output for dependency in step.dependencies
                    }
                    record = _approval_for_step(approvals, step.id)
                    expected = _approval_record(
                        run_id=effective_run_id,
                        workflow_digest=workflow_digest,
                        input_digest=input_digest,
                        step=step,
                        dependencies=dependencies,
                        requested_at=(record.requested_at if record is not None else None),
                    )
                    if record is None:
                        approvals[expected.request_id] = expected
                        record = expected
                        created_approval = True
                    elif not _same_approval_request(record, expected):
                        raise WorkflowExecutionError(
                            f"Checkpoint approval does not match step {step.id!r}."
                        )
                    if record.status is ApprovalStatus.PENDING:
                        waiting.append(record)

                if waiting:
                    if checkpoint_store is None:
                        raise WorkflowExecutionError(
                            "Approval requests require a checkpoint store."
                        )
                    if created_approval:
                        await self._save_checkpoint(
                            checkpoint_store,
                            self._build_checkpoint(
                                workflow,
                                effective_run_id,
                                workflow_digest,
                                input_digest,
                                results,
                                approvals,
                            ),
                        )
                        await dispatcher.emit(
                            WorkflowEventKind.CHECKPOINT_SAVED,
                            run_id=effective_run_id,
                            workflow=workflow.name,
                            resumed=resume,
                        )
                    for record in waiting:
                        await dispatcher.emit(
                            WorkflowEventKind.APPROVAL_REQUESTED,
                            run_id=effective_run_id,
                            workflow=workflow.name,
                            step_id=record.step_id,
                            resumed=resume,
                            approval_id=record.request_id,
                        )
                    return await self._paused_result(
                        workflow=workflow,
                        run_id=effective_run_id,
                        started_at=started_at,
                        started_clock=started_clock,
                        results=results,
                        approvals=approvals,
                        restored_steps=restored_steps,
                        resumed=resume,
                        dispatcher=dispatcher,
                    )

                tasks = [
                    asyncio.create_task(
                        self._run_step(
                            workflow.name,
                            effective_run_id,
                            step,
                            workflow_input,
                            {
                                dependency: results[dependency].output
                                for dependency in step.dependencies
                            },
                            _approval_for_step(approvals, step.id),
                            semaphore,
                            dispatcher,
                        )
                    )
                    for step in ready
                ]
                try:
                    batch = await asyncio.gather(*tasks)
                except BaseException:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise

                failed = False
                for result in batch:
                    results[result.step_id] = result
                    pending.remove(result.step_id)
                    failed = failed or result.state is StepState.FAILED

                if checkpoint_store is not None:
                    await self._save_checkpoint(
                        checkpoint_store,
                        self._build_checkpoint(
                            workflow,
                            effective_run_id,
                            workflow_digest,
                            input_digest,
                            results,
                            approvals,
                        ),
                    )
                    await dispatcher.emit(
                        WorkflowEventKind.CHECKPOINT_SAVED,
                        run_id=effective_run_id,
                        workflow=workflow.name,
                        resumed=resume,
                    )

                if failed and self.fail_fast:
                    for step in workflow.steps:
                        if step.id in pending:
                            blocked = self._terminal_without_run(
                                step,
                                StepState.BLOCKED,
                                "FailFast",
                                "Not started because an earlier step failed.",
                            )
                            results[step.id] = blocked
                            pending.remove(step.id)
                            await dispatcher.emit(
                                WorkflowEventKind.STEP_BLOCKED,
                                run_id=effective_run_id,
                                workflow=workflow.name,
                                step_id=step.id,
                                state=StepState.BLOCKED,
                                duration_ms=0.0,
                                error_type="FailFast",
                            )
                    break

            finished_at = _utc_now()
            ordered_results = tuple(results[step.id] for step in workflow.steps)
            status = (
                "failed"
                if any(result.state is StepState.FAILED for result in ordered_results)
                else (
                    "succeeded"
                    if all(result.state is StepState.SUCCEEDED for result in ordered_results)
                    else (
                        "rejected"
                        if any(result.state is StepState.REJECTED for result in ordered_results)
                        else "failed"
                    )
                )
            )
            compensation_status = "not_requested"
            compensation_report = tuple(
                compensation_results[step.id]
                for step in workflow.steps
                if step.id in compensation_results
            )
            eligible_compensations = tuple(
                step
                for step in workflow.steps
                if step.compensation is not None
                and step.id in results
                and results[step.id].state is StepState.SUCCEEDED
            )
            if status in ("failed", "rejected") and eligible_compensations:
                if checkpoint_store is None:
                    raise WorkflowExecutionError("Compensating actions require a checkpoint store.")
                if phase is CheckpointPhase.FORWARD:
                    phase = CheckpointPhase.COMPENSATING
                    await self._persist_phase(
                        store=checkpoint_store,
                        workflow=workflow,
                        run_id=effective_run_id,
                        workflow_digest=workflow_digest,
                        input_digest=input_digest,
                        results=results,
                        approvals=approvals,
                        phase=phase,
                        compensations=compensation_results,
                        dispatcher=dispatcher,
                        resumed=resume,
                    )
                if phase is CheckpointPhase.COMPENSATING:
                    compensation_report = await self._run_compensations(
                        workflow=workflow,
                        workflow_input=workflow_input,
                        run_id=effective_run_id,
                        workflow_digest=workflow_digest,
                        input_digest=input_digest,
                        results=results,
                        approvals=approvals,
                        successful=compensation_results,
                        checkpoint_store=checkpoint_store,
                        semaphore=semaphore,
                        dispatcher=dispatcher,
                        resumed=resume,
                    )
                    if all(step.id in compensation_results for step in eligible_compensations):
                        phase = CheckpointPhase.COMPLETE
                        compensation_status = "succeeded"
                        await self._persist_phase(
                            store=checkpoint_store,
                            workflow=workflow,
                            run_id=effective_run_id,
                            workflow_digest=workflow_digest,
                            input_digest=input_digest,
                            results=results,
                            approvals=approvals,
                            phase=phase,
                            compensations=compensation_results,
                            dispatcher=dispatcher,
                            resumed=resume,
                        )
                    else:
                        compensation_status = "failed"
                else:
                    compensation_status = "succeeded"
            if (
                workflow.version >= 3
                and phase is CheckpointPhase.FORWARD
                and checkpoint_store is not None
            ):
                phase = CheckpointPhase.COMPLETE
                await self._persist_phase(
                    store=checkpoint_store,
                    workflow=workflow,
                    run_id=effective_run_id,
                    workflow_digest=workflow_digest,
                    input_digest=input_digest,
                    results=results,
                    approvals=approvals,
                    phase=phase,
                    compensations=compensation_results,
                    dispatcher=dispatcher,
                    resumed=resume,
                )
            duration_ms = round((time.perf_counter() - started_clock) * 1_000, 3)
            run_result = WorkflowRunResult(
                run_id=effective_run_id,
                workflow=workflow.name,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                steps=ordered_results,
                resumed=resume,
                restored_steps=restored_steps,
                approvals=_ordered_approvals(workflow, approvals),
                schema_version=workflow.version,
                compensations=compensation_report,
                compensation_status=compensation_status,
            )
            await dispatcher.emit(
                (
                    WorkflowEventKind.RUN_SUCCEEDED
                    if run_result.succeeded
                    else (
                        WorkflowEventKind.RUN_REJECTED
                        if run_result.status == "rejected"
                        else WorkflowEventKind.RUN_FAILED
                    )
                ),
                run_id=effective_run_id,
                workflow=workflow.name,
                duration_ms=duration_ms,
                resumed=resume,
            )
            return run_result
        except asyncio.CancelledError:
            try:
                await dispatcher.emit(
                    WorkflowEventKind.RUN_CANCELLED,
                    run_id=effective_run_id,
                    workflow=workflow.name,
                    duration_ms=round((time.perf_counter() - started_clock) * 1_000, 3),
                    resumed=resume,
                )
            except EventDeliveryError:
                pass
            raise

    async def _load_checkpoint(
        self,
        store: CheckpointStore,
        run_id: str,
    ) -> WorkflowCheckpoint | None:
        try:
            return await asyncio.to_thread(store.load, run_id)
        except WorkflowExecutionError:
            raise
        except Exception as exc:
            raise WorkflowExecutionError(
                f"Cannot load checkpoint for run_id {run_id!r}: {exc}"
            ) from exc

    async def _save_checkpoint(
        self,
        store: CheckpointStore,
        checkpoint: WorkflowCheckpoint,
    ) -> None:
        try:
            await asyncio.to_thread(store.save, checkpoint)
        except WorkflowExecutionError:
            raise
        except Exception as exc:
            raise WorkflowExecutionError(
                f"Cannot save checkpoint for run_id {checkpoint.run_id!r}: {exc}"
            ) from exc

    async def _persist_phase(
        self,
        *,
        store: CheckpointStore,
        workflow: WorkflowDefinition,
        run_id: str,
        workflow_digest: str,
        input_digest: str,
        results: Mapping[str, StepResult],
        approvals: Mapping[str, ApprovalRecord],
        phase: CheckpointPhase,
        compensations: Mapping[str, StepResult],
        dispatcher: _EventDispatcher,
        resumed: bool,
    ) -> None:
        """Persist one Saga phase transition and emit its lifecycle event."""
        await self._save_checkpoint(
            store,
            self._build_checkpoint(
                workflow,
                run_id,
                workflow_digest,
                input_digest,
                results,
                approvals,
                phase=phase,
                compensations=compensations,
            ),
        )
        await dispatcher.emit(
            WorkflowEventKind.CHECKPOINT_SAVED,
            run_id=run_id,
            workflow=workflow.name,
            resumed=resumed,
        )

    def _restore_checkpoint(
        self,
        checkpoint: WorkflowCheckpoint,
        *,
        workflow_digest: str,
        input_digest: str,
        ordered_steps: Mapping[str, WorkflowStep],
        results: dict[str, StepResult],
        pending: set[str],
        approvals: dict[str, ApprovalRecord],
        compensations: dict[str, StepResult],
        workflow_version: int,
        run_id: str,
    ) -> None:
        if checkpoint.run_id != run_id:
            raise WorkflowExecutionError("Checkpoint run_id does not match the requested run.")
        if checkpoint.version != workflow_version:
            raise WorkflowExecutionError(
                "Checkpoint version does not match the workflow schema version."
            )
        if checkpoint.workflow_digest != workflow_digest:
            raise WorkflowExecutionError(
                "Checkpoint workflow does not match the requested workflow definition."
            )
        if checkpoint.input_digest != input_digest:
            raise WorkflowExecutionError(
                "Checkpoint input does not match the requested workflow input."
            )
        restored_ids = {result.step_id for result in checkpoint.steps}
        for result in checkpoint.steps:
            step = ordered_steps.get(result.step_id)
            if step is None:
                raise WorkflowExecutionError(
                    f"Checkpoint references unknown step {result.step_id!r}."
                )
            if result.action != step.action or result.agent != step.agent:
                raise WorkflowExecutionError(
                    f"Checkpoint metadata does not match step {result.step_id!r}."
                )
            if any(dependency not in restored_ids for dependency in step.dependencies):
                raise WorkflowExecutionError(
                    f"Checkpoint is missing a dependency for step {result.step_id!r}."
                )
            self._require_json_value(
                result.output,
                label=f"checkpoint output from {result.step_id}",
            )
            results[result.step_id] = result
            pending.remove(result.step_id)
        for result in checkpoint.compensations:
            step = ordered_steps.get(result.step_id)
            if step is None or step.compensation is None:
                raise WorkflowExecutionError(
                    f"Checkpoint compensation references unconfigured step {result.step_id!r}."
                )
            if result.action != step.compensation.action or result.agent != step.agent:
                raise WorkflowExecutionError(
                    f"Checkpoint compensation metadata does not match step {result.step_id!r}."
                )
            if result.step_id not in restored_ids:
                raise WorkflowExecutionError(
                    f"Checkpoint compensation lacks forward result {result.step_id!r}."
                )
            self._require_json_value(
                result.output,
                label=f"checkpoint compensation output from {result.step_id}",
            )
            compensations[result.step_id] = result
        for record in checkpoint.approvals:
            step = ordered_steps.get(record.step_id)
            if step is None or step.approval is None:
                raise WorkflowExecutionError(
                    f"Checkpoint approval references ungated step {record.step_id!r}."
                )
            if any(dependency not in restored_ids for dependency in step.dependencies):
                raise WorkflowExecutionError(
                    f"Checkpoint approval is missing a dependency for step {record.step_id!r}."
                )
            expected = _approval_record(
                run_id=run_id,
                workflow_digest=workflow_digest,
                input_digest=input_digest,
                step=step,
                dependencies={
                    dependency: results[dependency].output for dependency in step.dependencies
                },
                requested_at=record.requested_at,
            )
            if not _same_approval_request(record, expected):
                raise WorkflowExecutionError(
                    f"Checkpoint approval does not match step {record.step_id!r}."
                )
            if record.step_id in restored_ids and record.status is not ApprovalStatus.APPROVED:
                raise WorkflowExecutionError(
                    f"Successful step {record.step_id!r} lacks durable approval."
                )
            approvals[record.request_id] = record
        if checkpoint.phase is not CheckpointPhase.FORWARD:
            if pending:
                raise WorkflowExecutionError(
                    "Compensation-phase checkpoint must contain every terminal forward result."
                )
            business_unsuccessful = not all(
                result.state is StepState.SUCCEEDED for result in results.values()
            )
            eligible = {
                step.id
                for step in ordered_steps.values()
                if step.compensation is not None and results[step.id].state is StepState.SUCCEEDED
            }
            completed = set(compensations)
            if checkpoint.phase is CheckpointPhase.COMPENSATING and (
                not business_unsuccessful or not eligible - completed
            ):
                raise WorkflowExecutionError(
                    "Compensating checkpoint has no valid unfinished compensation."
                )
            if checkpoint.phase is CheckpointPhase.COMPLETE:
                if business_unsuccessful and eligible != completed:
                    raise WorkflowExecutionError(
                        "Complete checkpoint is missing successful compensation results."
                    )
                if not business_unsuccessful and completed:
                    raise WorkflowExecutionError(
                        "Successful workflow checkpoint cannot contain compensation results."
                    )

    @staticmethod
    def _build_checkpoint(
        workflow: WorkflowDefinition,
        run_id: str,
        workflow_digest: str,
        input_digest: str,
        results: Mapping[str, StepResult],
        approvals: Mapping[str, ApprovalRecord],
        *,
        phase: CheckpointPhase = CheckpointPhase.FORWARD,
        compensations: Mapping[str, StepResult] | None = None,
    ) -> WorkflowCheckpoint:
        return WorkflowCheckpoint(
            version=workflow.version,
            run_id=run_id,
            workflow_digest=workflow_digest,
            input_digest=input_digest,
            saved_at=_utc_now(),
            steps=tuple(
                results[step.id]
                for step in workflow.steps
                if step.id in results
                and (
                    results[step.id].state is StepState.SUCCEEDED
                    or phase is not CheckpointPhase.FORWARD
                )
            ),
            approvals=_ordered_approvals(workflow, approvals),
            phase=phase,
            compensations=tuple(
                (compensations or {})[step.id]
                for step in workflow.steps
                if step.id in (compensations or {})
            ),
        )

    async def _paused_result(
        self,
        *,
        workflow: WorkflowDefinition,
        run_id: str,
        started_at: str,
        started_clock: float,
        results: Mapping[str, StepResult],
        approvals: Mapping[str, ApprovalRecord],
        restored_steps: int,
        resumed: bool,
        dispatcher: _EventDispatcher,
    ) -> WorkflowRunResult:
        duration_ms = round((time.perf_counter() - started_clock) * 1_000, 3)
        result = WorkflowRunResult(
            run_id=run_id,
            workflow=workflow.name,
            status="paused",
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=duration_ms,
            steps=tuple(results[step.id] for step in workflow.steps if step.id in results),
            resumed=resumed,
            restored_steps=restored_steps,
            approvals=_ordered_approvals(workflow, approvals),
            schema_version=workflow.version,
        )
        await dispatcher.emit(
            WorkflowEventKind.RUN_PAUSED,
            run_id=run_id,
            workflow=workflow.name,
            duration_ms=duration_ms,
            resumed=resumed,
        )
        return result

    async def _run_compensations(
        self,
        *,
        workflow: WorkflowDefinition,
        workflow_input: Any,
        run_id: str,
        workflow_digest: str,
        input_digest: str,
        results: Mapping[str, StepResult],
        approvals: Mapping[str, ApprovalRecord],
        successful: dict[str, StepResult],
        checkpoint_store: CheckpointStore,
        semaphore: asyncio.Semaphore,
        dispatcher: _EventDispatcher,
        resumed: bool,
    ) -> tuple[StepResult, ...]:
        """Compensate successful effects in reverse dependency order."""
        eligible = {
            step.id
            for step in workflow.steps
            if step.compensation is not None
            and step.id in results
            and results[step.id].state is StepState.SUCCEEDED
        }
        remaining = eligible - successful.keys()
        report = dict(successful)
        dependents: dict[str, set[str]] = {step.id: set() for step in workflow.steps}
        for step in workflow.steps:
            for dependency in step.dependencies:
                dependents[dependency].add(step.id)

        while remaining:
            ready = tuple(
                step
                for step in workflow.steps
                if step.id in remaining and not (dependents[step.id] & remaining)
            )
            if not ready:
                raise WorkflowExecutionError("Compensation graph unexpectedly stalled.")
            tasks = [
                asyncio.create_task(
                    self._run_compensation(
                        workflow.name,
                        run_id,
                        step,
                        workflow_input,
                        {
                            dependency: results[dependency].output
                            for dependency in step.dependencies
                        },
                        results[step.id].output,
                        semaphore,
                        dispatcher,
                    )
                )
                for step in ready
            ]
            try:
                batch = await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            failed = False
            for result in batch:
                report[result.step_id] = result
                remaining.remove(result.step_id)
                if result.state is StepState.SUCCEEDED:
                    successful[result.step_id] = result
                else:
                    failed = True
            await self._persist_phase(
                store=checkpoint_store,
                workflow=workflow,
                run_id=run_id,
                workflow_digest=workflow_digest,
                input_digest=input_digest,
                results=results,
                approvals=approvals,
                phase=CheckpointPhase.COMPENSATING,
                compensations=successful,
                dispatcher=dispatcher,
                resumed=resumed,
            )
            if failed:
                break
        return tuple(report[step.id] for step in workflow.steps if step.id in report)

    async def _run_compensation(
        self,
        workflow_name: str,
        run_id: str,
        step: WorkflowStep,
        workflow_input: Any,
        dependencies: Mapping[str, Any],
        output: Any,
        semaphore: asyncio.Semaphore,
        dispatcher: _EventDispatcher,
    ) -> StepResult:
        policy = step.compensation
        if policy is None:
            raise WorkflowExecutionError(f"Step {step.id!r} has no compensation policy.")
        async with semaphore:
            started_at = _utc_now()
            started_clock = time.perf_counter()
            last_error: BaseException | None = None
            attempts = policy.retries + 1
            attempts_used = 0
            handler = self._compensations[policy.action]
            handler_is_async = inspect.iscoroutinefunction(handler)
            for attempt in range(1, attempts + 1):
                attempts_used = attempt
                await dispatcher.emit(
                    WorkflowEventKind.COMPENSATION_STARTED,
                    run_id=run_id,
                    workflow=workflow_name,
                    step_id=step.id,
                    attempt=attempt,
                    state=StepState.RUNNING,
                )
                context = CompensationContext(
                    workflow_name=workflow_name,
                    step=step,
                    workflow_input=workflow_input,
                    dependencies=dependencies,
                    output=output,
                    attempt=attempt,
                    run_id=run_id,
                    idempotency_key=f"{run_id}:{step.id}:compensate",
                )
                try:
                    compensation_output = await asyncio.wait_for(
                        self._invoke(handler, context),
                        timeout=policy.timeout_seconds,
                    )
                    self._require_json_value(
                        compensation_output,
                        label=f"compensation output from step {step.id}",
                    )
                    result = StepResult(
                        step_id=step.id,
                        agent=step.agent,
                        action=policy.action,
                        state=StepState.SUCCEEDED,
                        attempts=attempt,
                        started_at=started_at,
                        finished_at=_utc_now(),
                        duration_ms=round((time.perf_counter() - started_clock) * 1_000, 3),
                        output=compensation_output,
                    )
                    await dispatcher.emit(
                        WorkflowEventKind.COMPENSATION_SUCCEEDED,
                        run_id=run_id,
                        workflow=workflow_name,
                        step_id=step.id,
                        attempt=attempt,
                        state=StepState.SUCCEEDED,
                        duration_ms=result.duration_ms,
                    )
                    return result
                except asyncio.CancelledError:
                    try:
                        await dispatcher.emit(
                            WorkflowEventKind.COMPENSATION_CANCELLED,
                            run_id=run_id,
                            workflow=workflow_name,
                            step_id=step.id,
                            attempt=attempt,
                            state=StepState.CANCELLED,
                            duration_ms=round(
                                (time.perf_counter() - started_clock) * 1_000,
                                3,
                            ),
                        )
                    except EventDeliveryError:
                        pass
                    raise
                except EventDeliveryError:
                    raise
                except TimeoutError:
                    last_error = TimeoutError(
                        f"Compensation exceeded its {policy.timeout_seconds:g}s timeout."
                    )
                    if not handler_is_async:
                        break
                except Exception as exc:
                    last_error = exc
                if attempt < attempts:
                    await dispatcher.emit(
                        WorkflowEventKind.COMPENSATION_RETRY_SCHEDULED,
                        run_id=run_id,
                        workflow=workflow_name,
                        step_id=step.id,
                        attempt=attempt,
                        state=StepState.RUNNING,
                        error_type=type(last_error).__name__,
                    )
                    if policy.retry_delay_seconds:
                        await asyncio.sleep(policy.retry_delay_seconds)
            if last_error is None:
                raise RuntimeError("Compensation exhausted its attempts without an error.")
            result = StepResult(
                step_id=step.id,
                agent=step.agent,
                action=policy.action,
                state=StepState.FAILED,
                attempts=attempts_used,
                started_at=started_at,
                finished_at=_utc_now(),
                duration_ms=round((time.perf_counter() - started_clock) * 1_000, 3),
                error={"type": type(last_error).__name__, "message": str(last_error)[:1_000]},
            )
            await dispatcher.emit(
                WorkflowEventKind.COMPENSATION_FAILED,
                run_id=run_id,
                workflow=workflow_name,
                step_id=step.id,
                attempt=attempts_used,
                state=StepState.FAILED,
                duration_ms=result.duration_ms,
                error_type=type(last_error).__name__,
            )
            return result

    async def _run_step(
        self,
        workflow_name: str,
        run_id: str,
        step: WorkflowStep,
        workflow_input: Any,
        dependencies: Mapping[str, Any],
        approval: ApprovalRecord | None,
        semaphore: asyncio.Semaphore,
        dispatcher: _EventDispatcher,
    ) -> StepResult:
        if step.approval is not None and (
            approval is None or approval.status is not ApprovalStatus.APPROVED
        ):
            raise WorkflowExecutionError(f"Step {step.id!r} cannot start without durable approval.")
        async with semaphore:
            started_at = _utc_now()
            started_clock = time.perf_counter()
            last_error: BaseException | None = None
            attempts = step.retries + 1
            attempts_used = 0
            handler = self._actions[step.action]
            handler_is_async = inspect.iscoroutinefunction(handler)
            for attempt in range(1, attempts + 1):
                attempts_used = attempt
                await dispatcher.emit(
                    WorkflowEventKind.STEP_ATTEMPT_STARTED,
                    run_id=run_id,
                    workflow=workflow_name,
                    step_id=step.id,
                    attempt=attempt,
                    state=StepState.RUNNING,
                )
                context = ActionContext(
                    workflow_name=workflow_name,
                    step=step,
                    workflow_input=workflow_input,
                    dependencies=dependencies,
                    attempt=attempt,
                    run_id=run_id,
                    idempotency_key=f"{run_id}:{step.id}",
                    approval=approval,
                )
                try:
                    output = await asyncio.wait_for(
                        self._invoke(handler, context),
                        timeout=step.timeout_seconds,
                    )
                    self._require_json_value(output, label=f"output from step {step.id}")
                    result = StepResult(
                        step_id=step.id,
                        agent=step.agent,
                        action=step.action,
                        state=StepState.SUCCEEDED,
                        attempts=attempt,
                        started_at=started_at,
                        finished_at=_utc_now(),
                        duration_ms=round((time.perf_counter() - started_clock) * 1_000, 3),
                        output=output,
                    )
                    await dispatcher.emit(
                        WorkflowEventKind.STEP_SUCCEEDED,
                        run_id=run_id,
                        workflow=workflow_name,
                        step_id=step.id,
                        attempt=attempt,
                        state=StepState.SUCCEEDED,
                        duration_ms=result.duration_ms,
                    )
                    return result
                except asyncio.CancelledError:
                    try:
                        await dispatcher.emit(
                            WorkflowEventKind.STEP_CANCELLED,
                            run_id=run_id,
                            workflow=workflow_name,
                            step_id=step.id,
                            attempt=attempt,
                            state=StepState.CANCELLED,
                            duration_ms=round(
                                (time.perf_counter() - started_clock) * 1_000,
                                3,
                            ),
                        )
                    except EventDeliveryError:
                        pass
                    raise
                except EventDeliveryError:
                    raise
                except TimeoutError:
                    last_error = TimeoutError(
                        f"Step exceeded its {step.timeout_seconds:g}s timeout."
                    )
                    # asyncio cannot terminate work already running in a worker
                    # thread. Retrying a timed-out synchronous handler could run
                    # the same side effect concurrently, so fail this step after
                    # the first timeout regardless of its retry setting.
                    if not handler_is_async:
                        break
                except Exception as exc:
                    last_error = exc
                if attempt < attempts:
                    await dispatcher.emit(
                        WorkflowEventKind.STEP_RETRY_SCHEDULED,
                        run_id=run_id,
                        workflow=workflow_name,
                        step_id=step.id,
                        attempt=attempt,
                        state=StepState.RUNNING,
                        error_type=type(last_error).__name__,
                    )
                    if step.retry_delay_seconds:
                        await asyncio.sleep(step.retry_delay_seconds)

            if last_error is None:
                raise RuntimeError("Step exhausted its attempts without an error.")
            result = StepResult(
                step_id=step.id,
                agent=step.agent,
                action=step.action,
                state=StepState.FAILED,
                attempts=attempts_used,
                started_at=started_at,
                finished_at=_utc_now(),
                duration_ms=round((time.perf_counter() - started_clock) * 1_000, 3),
                error={
                    "type": type(last_error).__name__,
                    "message": str(last_error)[:1_000],
                },
            )
            await dispatcher.emit(
                WorkflowEventKind.STEP_FAILED,
                run_id=run_id,
                workflow=workflow_name,
                step_id=step.id,
                attempt=attempts_used,
                state=StepState.FAILED,
                duration_ms=result.duration_ms,
                error_type=type(last_error).__name__,
            )
            return result

    async def _invoke(
        self,
        handler: Callable[[HandlerContextT], Any | Awaitable[Any]],
        context: HandlerContextT,
    ) -> Any:
        if inspect.iscoroutinefunction(handler):
            return await handler(context)
        result = await asyncio.to_thread(handler, context)
        if inspect.isawaitable(result):
            return await result
        return result

    def _require_json_value(self, value: Any, *, label: str) -> None:
        try:
            encoded = json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError) as exc:
            raise WorkflowExecutionError(f"{label} must be finite JSON data.") from exc
        if len(encoded) > self.max_result_bytes:
            raise WorkflowExecutionError(
                f"{label} is {len(encoded)} bytes; the limit is {self.max_result_bytes} bytes."
            )

    @staticmethod
    def _terminal_without_run(
        step: WorkflowStep,
        state: StepState,
        error_type: str,
        message: str,
        *,
        finished_at: str | None = None,
    ) -> StepResult:
        return StepResult(
            step_id=step.id,
            agent=step.agent,
            action=step.action,
            state=state,
            attempts=0,
            started_at=None,
            finished_at=finished_at or _utc_now(),
            duration_ms=0.0,
            error={"type": error_type, "message": message},
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _approval_record(
    *,
    run_id: str,
    workflow_digest: str,
    input_digest: str,
    step: WorkflowStep,
    dependencies: Mapping[str, Any],
    requested_at: str | None = None,
) -> ApprovalRecord:
    if step.approval is None:
        raise WorkflowExecutionError(f"Step {step.id!r} has no approval policy.")
    context_digest = _json_digest(
        {
            "workflow_digest": workflow_digest,
            "input_digest": input_digest,
            "step_id": step.id,
            "dependencies": dependencies,
        }
    )
    request_id = _json_digest({"run_id": run_id, "context_digest": context_digest})
    return ApprovalRecord(
        request_id=request_id,
        step_id=step.id,
        prompt=step.approval.prompt,
        context_digest=context_digest,
        requested_at=requested_at or _utc_now(),
    )


def _same_approval_request(left: ApprovalRecord, right: ApprovalRecord) -> bool:
    return (
        left.request_id == right.request_id
        and left.step_id == right.step_id
        and left.prompt == right.prompt
        and left.context_digest == right.context_digest
        and left.requested_at == right.requested_at
    )


def _approval_for_step(
    approvals: Mapping[str, ApprovalRecord],
    step_id: str,
) -> ApprovalRecord | None:
    return next((record for record in approvals.values() if record.step_id == step_id), None)


def _ordered_approvals(
    workflow: WorkflowDefinition,
    approvals: Mapping[str, ApprovalRecord],
) -> tuple[ApprovalRecord, ...]:
    by_step = {record.step_id: record for record in approvals.values()}
    return tuple(by_step[step.id] for step in workflow.steps if step.id in by_step)


def _require_optional_bounded_text(value: Any, *, label: str, maximum: int) -> None:
    if value is not None and (not isinstance(value, str) or len(value) > maximum):
        raise WorkflowExecutionError(
            f"{label} must be null or a string of at most {maximum} characters."
        )


def _require_bounded_timestamp(value: Any, *, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > MAX_TIMESTAMP_CHARACTERS:
        raise WorkflowExecutionError(
            f"{label} must be a non-empty string of at most {MAX_TIMESTAMP_CHARACTERS} characters."
        )


def _require_monotonic_checkpoint(
    existing: WorkflowCheckpoint,
    candidate: WorkflowCheckpoint,
) -> None:
    if (
        existing.version != candidate.version
        or existing.workflow_digest != candidate.workflow_digest
        or existing.input_digest != candidate.input_digest
    ):
        raise WorkflowExecutionError("Checkpoint identity cannot change for a run.")
    phase_order = {
        CheckpointPhase.FORWARD: 0,
        CheckpointPhase.COMPENSATING: 1,
        CheckpointPhase.COMPLETE: 2,
    }
    if phase_order[candidate.phase] < phase_order[existing.phase]:
        raise WorkflowExecutionError("Checkpoint execution phase cannot regress.")
    if existing.phase is CheckpointPhase.COMPLETE and existing.to_dict() != candidate.to_dict():
        raise WorkflowExecutionError("A complete checkpoint is immutable.")
    existing_steps = {step.step_id: step for step in existing.steps}
    candidate_steps = {step.step_id: step for step in candidate.steps}
    if not existing_steps.keys() <= candidate_steps.keys():
        raise WorkflowExecutionError("Checkpoint cannot regress successful steps.")
    for step_id, result in existing_steps.items():
        if result.to_dict() != candidate_steps[step_id].to_dict():
            raise WorkflowExecutionError(
                f"Checkpoint contains divergent result for step {step_id!r}."
            )
    existing_approvals = {record.request_id: record for record in existing.approvals}
    candidate_approvals = {record.request_id: record for record in candidate.approvals}
    if not existing_approvals.keys() <= candidate_approvals.keys():
        raise WorkflowExecutionError("Checkpoint cannot remove approval records.")
    immutable = (
        "request_id",
        "step_id",
        "prompt",
        "context_digest",
        "requested_at",
    )
    for request_id, record in existing_approvals.items():
        updated = candidate_approvals[request_id]
        original_value = record.to_dict()
        updated_value = updated.to_dict()
        if any(original_value[field] != updated_value[field] for field in immutable):
            raise WorkflowExecutionError(f"Checkpoint contains divergent approval {request_id!r}.")
        if record.status is not ApprovalStatus.PENDING and original_value != updated_value:
            raise WorkflowExecutionError(
                f"Checkpoint cannot change decided approval {request_id!r}."
            )
    existing_compensations = {result.step_id: result for result in existing.compensations}
    candidate_compensations = {result.step_id: result for result in candidate.compensations}
    if not existing_compensations.keys() <= candidate_compensations.keys():
        raise WorkflowExecutionError("Checkpoint cannot regress successful compensations.")
    for step_id, result in existing_compensations.items():
        if result.to_dict() != candidate_compensations[step_id].to_dict():
            raise WorkflowExecutionError(
                f"Checkpoint contains divergent compensation for step {step_id!r}."
            )


def _is_sha256(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


__all__ = [
    "MAX_APPROVAL_ACTOR_CHARACTERS",
    "MAX_APPROVAL_REASON_CHARACTERS",
    "MAX_RESULT_BYTES",
    "ActionContext",
    "ActionHandler",
    "ApprovalDecision",
    "ApprovalDecisionKind",
    "ApprovalRecord",
    "ApprovalStatus",
    "CheckpointPhase",
    "CheckpointStore",
    "CompensationContext",
    "CompensationHandler",
    "EventDeliveryError",
    "StepResult",
    "WorkflowCheckpoint",
    "WorkflowExecutionError",
    "WorkflowRunResult",
    "WorkflowRunner",
]
