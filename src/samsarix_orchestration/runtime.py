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
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, TypeGuard

from .spec import WorkflowDefinition, WorkflowStep

MAX_RESULT_BYTES = 1_048_576
ActionHandler = Callable[["ActionContext"], Any | Awaitable[Any]]
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class WorkflowExecutionError(RuntimeError):
    """Raised before execution when the runtime cannot safely run a workflow."""


class StepState(StrEnum):
    """Stable lifecycle states for a workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


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
    """Successful step results persisted for a specific workflow input."""

    version: int
    run_id: str
    workflow_digest: str
    input_digest: str
    saved_at: str
    steps: tuple[StepResult, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        return {
            "version": self.version,
            "run_id": self.run_id,
            "workflow_digest": self.workflow_digest,
            "input_digest": self.input_digest,
            "saved_at": self.saved_at,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, value: Any) -> WorkflowCheckpoint:
        """Validate and restore a workflow checkpoint from decoded JSON."""
        if not isinstance(value, dict):
            raise WorkflowExecutionError("Checkpoint must be a JSON object.")
        if value.get("version") != 1:
            raise WorkflowExecutionError("Only checkpoint version 1 is supported.")
        run_id = value.get("run_id")
        workflow_digest = value.get("workflow_digest")
        input_digest = value.get("input_digest")
        saved_at = value.get("saved_at")
        raw_steps = value.get("steps")
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise WorkflowExecutionError("Checkpoint run_id is invalid.")
        if not _is_sha256(workflow_digest) or not _is_sha256(input_digest):
            raise WorkflowExecutionError("Checkpoint identity digests are invalid.")
        if not isinstance(saved_at, str):
            raise WorkflowExecutionError("Checkpoint saved_at is invalid.")
        if not isinstance(raw_steps, list):
            raise WorkflowExecutionError("Checkpoint steps must be a JSON array.")
        steps = tuple(StepResult.from_dict(step) for step in raw_steps)
        if len({step.step_id for step in steps}) != len(steps):
            raise WorkflowExecutionError("Checkpoint contains duplicate step results.")
        if any(step.state is not StepState.SUCCEEDED for step in steps):
            raise WorkflowExecutionError("Checkpoints may contain only successful step results.")
        if any(
            step.attempts < 1 or step.started_at is None or step.error is not None for step in steps
        ):
            raise WorkflowExecutionError("Checkpoint contains an invalid successful step result.")
        return cls(
            version=1,
            run_id=run_id,
            workflow_digest=workflow_digest,
            input_digest=input_digest,
            saved_at=saved_at,
            steps=steps,
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
    """Serializable result for a complete workflow run."""

    run_id: str
    workflow: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: float
    steps: tuple[StepResult, ...]
    resumed: bool = False
    restored_steps: int = 0

    @property
    def succeeded(self) -> bool:
        """Whether every step completed successfully."""
        return self.status == "succeeded"

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        return {
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


class WorkflowRunner:
    """Execute dependency-aware workflows using explicitly registered handlers."""

    def __init__(
        self,
        actions: Mapping[str, ActionHandler] | None = None,
        *,
        fail_fast: bool = True,
        max_result_bytes: int = MAX_RESULT_BYTES,
    ) -> None:
        if max_result_bytes < 1:
            raise ValueError("max_result_bytes must be positive")
        self._actions: dict[str, ActionHandler] = {}
        self.fail_fast = fail_fast
        self.max_result_bytes = max_result_bytes
        for name, handler in (actions or {}).items():
            self.register_action(name, handler)

    def register_action(self, name: str, handler: ActionHandler) -> None:
        """Register or replace a handler by an explicit action name."""
        if not name or len(name) > 64:
            raise ValueError("Action name must contain 1 to 64 characters.")
        if not callable(handler):
            raise TypeError(f"Handler for {name!r} must be callable.")
        self._actions[name] = handler

    async def run(
        self,
        workflow: WorkflowDefinition,
        workflow_input: Any = None,
        *,
        run_id: str | None = None,
        checkpoint_store: CheckpointStore | None = None,
        resume: bool = False,
    ) -> WorkflowRunResult:
        """Run or resume a workflow and return a terminal-state report.

        Checkpoints reuse only successful step results whose workflow and input
        digests match exactly. Persistence is at-least-once: handlers that cause
        external effects must honor ``ActionContext.idempotency_key`` because a
        process can stop after the effect succeeds but before its checkpoint saves.
        """
        workflow.require_valid()
        self._require_json_value(workflow_input, label="workflow input")
        if resume and checkpoint_store is None:
            raise WorkflowExecutionError("resume requires a checkpoint store.")
        if resume and run_id is None:
            raise WorkflowExecutionError("resume requires an explicit run_id.")
        effective_run_id = run_id or str(uuid.uuid4())
        if not _RUN_ID.fullmatch(effective_run_id):
            raise WorkflowExecutionError(
                "run_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}."
            )
        missing = sorted({step.action for step in workflow.steps} - self._actions.keys())
        if missing:
            raise WorkflowExecutionError(
                "No handler registered for action(s): " + ", ".join(missing)
            )

        started_at = _utc_now()
        started_clock = time.perf_counter()
        ordered_steps = {step.id: step for step in workflow.steps}
        pending = set(ordered_steps)
        results: dict[str, StepResult] = {}
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
            )
        elif checkpoint is not None:
            raise WorkflowExecutionError(
                f"Checkpoint already exists for run_id {effective_run_id!r}; "
                "resume it or choose a new run_id."
            )
        restored_steps = len(results)
        semaphore = asyncio.Semaphore(workflow.max_concurrency)

        while pending:
            blocked_ids = [
                step_id
                for step_id in pending
                if any(
                    dependency in results and results[dependency].state is not StepState.SUCCEEDED
                    for dependency in ordered_steps[step_id].dependencies
                )
            ]
            for step_id in blocked_ids:
                step = ordered_steps[step_id]
                results[step_id] = self._terminal_without_run(
                    step,
                    StepState.BLOCKED,
                    "DependencyFailed",
                    "One or more dependencies did not succeed.",
                )
                pending.remove(step_id)

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
                    raise WorkflowExecutionError("Workflow stalled despite successful validation.")
                break

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
                        semaphore,
                    )
                )
                for step in ready
            ]
            try:
                batch = await asyncio.gather(*tasks)
            except asyncio.CancelledError:
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
                    WorkflowCheckpoint(
                        version=1,
                        run_id=effective_run_id,
                        workflow_digest=workflow_digest,
                        input_digest=input_digest,
                        saved_at=_utc_now(),
                        steps=tuple(
                            results[step.id]
                            for step in workflow.steps
                            if step.id in results
                            and results[step.id].state is StepState.SUCCEEDED
                        ),
                    ),
                )

            if failed and self.fail_fast:
                for step in workflow.steps:
                    if step.id in pending:
                        results[step.id] = self._terminal_without_run(
                            step,
                            StepState.BLOCKED,
                            "FailFast",
                            "Not started because an earlier step failed.",
                        )
                        pending.remove(step.id)
                break

        finished_at = _utc_now()
        ordered_results = tuple(results[step.id] for step in workflow.steps)
        status = (
            "succeeded"
            if all(result.state is StepState.SUCCEEDED for result in ordered_results)
            else "failed"
        )
        return WorkflowRunResult(
            run_id=effective_run_id,
            workflow=workflow.name,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=round((time.perf_counter() - started_clock) * 1_000, 3),
            steps=ordered_results,
            resumed=resume,
            restored_steps=restored_steps,
        )

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

    def _restore_checkpoint(
        self,
        checkpoint: WorkflowCheckpoint,
        *,
        workflow_digest: str,
        input_digest: str,
        ordered_steps: Mapping[str, WorkflowStep],
        results: dict[str, StepResult],
        pending: set[str],
    ) -> None:
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

    async def _run_step(
        self,
        workflow_name: str,
        run_id: str,
        step: WorkflowStep,
        workflow_input: Any,
        dependencies: Mapping[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> StepResult:
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
                context = ActionContext(
                    workflow_name=workflow_name,
                    step=step,
                    workflow_input=workflow_input,
                    dependencies=dependencies,
                    attempt=attempt,
                    run_id=run_id,
                    idempotency_key=f"{run_id}:{step.id}",
                )
                try:
                    output = await asyncio.wait_for(
                        self._invoke(handler, context),
                        timeout=step.timeout_seconds,
                    )
                    self._require_json_value(output, label=f"output from step {step.id}")
                    return StepResult(
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
                except asyncio.CancelledError:
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
                if attempt < attempts and step.retry_delay_seconds:
                    await asyncio.sleep(step.retry_delay_seconds)

            if last_error is None:
                raise RuntimeError("Step exhausted its attempts without an error.")
            return StepResult(
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

    async def _invoke(self, handler: ActionHandler, context: ActionContext) -> Any:
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
    ) -> StepResult:
        return StepResult(
            step_id=step.id,
            agent=step.agent,
            action=step.action,
            state=state,
            attempts=0,
            started_at=None,
            finished_at=_utc_now(),
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


def _is_sha256(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None
