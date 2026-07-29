"""Bounded asynchronous execution for validated workflows."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .spec import WorkflowDefinition, WorkflowStep

MAX_RESULT_BYTES = 1_048_576
ActionHandler = Callable[["ActionContext"], Any | Awaitable[Any]]


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
    ) -> WorkflowRunResult:
        """Run a workflow and return a complete terminal-state report."""
        workflow.require_valid()
        self._require_json_value(workflow_input, label="workflow input")
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
        semaphore = asyncio.Semaphore(workflow.max_concurrency)

        while pending:
            blocked_ids = [
                step_id
                for step_id in pending
                if any(
                    dependency in results
                    and results[dependency].state is not StepState.SUCCEEDED
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
                    dependency in results
                    and results[dependency].state is StepState.SUCCEEDED
                    for dependency in step.dependencies
                )
            ]
            if not ready:
                if pending:
                    raise WorkflowExecutionError(
                        "Workflow stalled despite successful validation."
                    )
                break

            tasks = [
                asyncio.create_task(
                    self._run_step(
                        workflow.name,
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
            run_id=str(uuid.uuid4()),
            workflow=workflow.name,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=round((time.perf_counter() - started_clock) * 1_000, 3),
            steps=ordered_results,
        )

    async def _run_step(
        self,
        workflow_name: str,
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
            for attempt in range(1, attempts + 1):
                context = ActionContext(
                    workflow_name=workflow_name,
                    step=step,
                    workflow_input=workflow_input,
                    dependencies=dependencies,
                    attempt=attempt,
                )
                try:
                    output = await asyncio.wait_for(
                        self._invoke(self._actions[step.action], context),
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
                        duration_ms=round(
                            (time.perf_counter() - started_clock) * 1_000, 3
                        ),
                        output=output,
                    )
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    last_error = TimeoutError(
                        f"Step exceeded its {step.timeout_seconds:g}s timeout."
                    )
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
                attempts=attempts,
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
                f"{label} is {len(encoded)} bytes; the limit is "
                f"{self.max_result_bytes} bytes."
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
