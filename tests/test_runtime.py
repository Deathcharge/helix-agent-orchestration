from __future__ import annotations

import asyncio
from typing import Any

import pytest

from helix_orchestration import (
    ActionContext,
    StepState,
    WorkflowDefinition,
    WorkflowExecutionError,
    WorkflowRunner,
    WorkflowStep,
)


def workflow(*steps: WorkflowStep, max_concurrency: int = 4) -> WorkflowDefinition:
    return WorkflowDefinition(
        name="runtime-test",
        steps=steps,
        max_concurrency=max_concurrency,
    )


@pytest.mark.asyncio
async def test_dependency_outputs_flow_between_real_handlers() -> None:
    async def start(context: ActionContext) -> str:
        assert context.workflow_input == {"value": "hello"}
        return context.workflow_input["value"]

    def finish(context: ActionContext) -> dict[str, str]:
        return {"result": context.dependencies["start"].upper()}

    runner = WorkflowRunner({"start": start, "finish": finish})
    result = await runner.run(
        workflow(
            WorkflowStep(id="start", action="start"),
            WorkflowStep(id="finish", action="finish", dependencies=("start",)),
        ),
        {"value": "hello"},
    )

    assert result.succeeded
    assert result.steps[1].output == {"result": "HELLO"}
    assert result.to_dict()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_ready_steps_respect_concurrency_limit() -> None:
    active = 0
    peak = 0

    async def measured(_context: ActionContext) -> str:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "done"

    steps = tuple(
        WorkflowStep(id=f"step-{index}", action="measured") for index in range(6)
    )
    result = await WorkflowRunner({"measured": measured}).run(
        workflow(*steps, max_concurrency=2)
    )

    assert result.succeeded
    assert peak == 2


@pytest.mark.asyncio
async def test_retry_succeeds_on_last_allowed_attempt() -> None:
    attempts = 0

    async def flaky(context: ActionContext) -> int:
        nonlocal attempts
        attempts += 1
        if context.attempt < 3:
            raise RuntimeError("temporary")
        return context.attempt

    result = await WorkflowRunner({"flaky": flaky}).run(
        workflow(WorkflowStep(id="retry", action="flaky", retries=2))
    )

    assert result.succeeded
    assert attempts == 3
    assert result.steps[0].attempts == 3


@pytest.mark.asyncio
async def test_timeout_fails_and_blocks_downstream() -> None:
    async def slow(_context: ActionContext) -> None:
        await asyncio.sleep(0.05)

    result = await WorkflowRunner({"slow": slow, "never": slow}).run(
        workflow(
            WorkflowStep(id="slow", action="slow", timeout_seconds=0.001),
            WorkflowStep(id="downstream", action="never", dependencies=("slow",)),
        )
    )

    assert result.status == "failed"
    assert result.steps[0].state is StepState.FAILED
    assert result.steps[0].error == {
        "type": "TimeoutError",
        "message": "Step exceeded its 0.001s timeout.",
    }
    assert result.steps[1].state is StepState.BLOCKED


@pytest.mark.asyncio
async def test_non_fail_fast_runs_independent_branch() -> None:
    async def fail(_context: ActionContext) -> None:
        raise ValueError("no")

    async def succeed(_context: ActionContext) -> str:
        return "yes"

    result = await WorkflowRunner(
        {"fail": fail, "succeed": succeed},
        fail_fast=False,
    ).run(
        workflow(
            WorkflowStep(id="bad", action="fail"),
            WorkflowStep(id="good", action="succeed"),
            WorkflowStep(id="blocked", action="succeed", dependencies=("bad",)),
        )
    )

    assert [step.state for step in result.steps] == [
        StepState.FAILED,
        StepState.SUCCEEDED,
        StepState.BLOCKED,
    ]


@pytest.mark.asyncio
async def test_fail_fast_blocks_later_batch() -> None:
    async def fail(_context: ActionContext) -> None:
        raise ValueError("no")

    result = await WorkflowRunner({"fail": fail, "ok": lambda _context: "ok"}).run(
        workflow(
            WorkflowStep(id="bad", action="fail"),
            WorkflowStep(id="later", action="ok", dependencies=("bad",)),
        )
    )
    assert result.steps[1].error == {
        "type": "FailFast",
        "message": "Not started because an earlier step failed.",
    }


@pytest.mark.asyncio
async def test_missing_action_and_non_json_values_are_rejected() -> None:
    runner = WorkflowRunner()
    with pytest.raises(WorkflowExecutionError, match="missing"):
        await runner.run(workflow(WorkflowStep(id="x", action="missing")))

    runner.register_action("bad-output", lambda _context: object())
    result = await runner.run(workflow(WorkflowStep(id="x", action="bad-output")))
    assert result.steps[0].state is StepState.FAILED
    assert result.steps[0].error is not None
    assert result.steps[0].error["type"] == "WorkflowExecutionError"

    runner.register_action("ok", lambda _context: None)
    with pytest.raises(WorkflowExecutionError, match="workflow input"):
        await runner.run(workflow(WorkflowStep(id="x", action="ok")), object())


@pytest.mark.asyncio
async def test_result_size_limit_is_enforced_as_step_failure() -> None:
    runner = WorkflowRunner({"large": lambda _context: "x" * 100}, max_result_bytes=10)
    result = await runner.run(workflow(WorkflowStep(id="x", action="large")))
    assert result.steps[0].state is StepState.FAILED
    assert "limit" in result.steps[0].error["message"]


def test_runner_configuration_is_validated() -> None:
    with pytest.raises(ValueError):
        WorkflowRunner(max_result_bytes=0)
    runner = WorkflowRunner()
    with pytest.raises(ValueError):
        runner.register_action("", lambda _context: None)
    with pytest.raises(TypeError):
        runner.register_action("bad", None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cancellation_propagates_to_caller() -> None:
    started = asyncio.Event()

    async def wait_forever(_context: ActionContext) -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        WorkflowRunner({"wait": wait_forever}).run(
            workflow(WorkflowStep(id="wait", action="wait"))
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_handler_returning_awaitable_is_supported() -> None:
    def factory(_context: ActionContext) -> Any:
        async def inner() -> str:
            return "awaited"

        return inner()

    result = await WorkflowRunner({"factory": factory}).run(
        workflow(WorkflowStep(id="x", action="factory"))
    )
    assert result.steps[0].output == "awaited"
