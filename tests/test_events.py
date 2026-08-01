# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from samsarix_orchestration import (
    ActionContext,
    EventDeliveryError,
    InMemoryCheckpointStore,
    StepState,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowRunner,
    WorkflowStep,
)


def workflow(*steps: WorkflowStep, max_concurrency: int = 4) -> WorkflowDefinition:
    return WorkflowDefinition(
        name="events-test",
        steps=steps,
        max_concurrency=max_concurrency,
    )


@pytest.mark.asyncio
async def test_success_events_have_stable_schema_and_sequence() -> None:
    events: list[WorkflowEvent] = []
    runner = WorkflowRunner(
        {"ok": lambda _context: "done"},
        event_handlers=(events.append,),
    )

    result = await runner.run(
        workflow(WorkflowStep(id="one", action="ok")),
        run_id="event-run",
    )

    assert result.succeeded
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    assert [event.kind for event in events] == [
        WorkflowEventKind.RUN_STARTED,
        WorkflowEventKind.STEP_ATTEMPT_STARTED,
        WorkflowEventKind.STEP_SUCCEEDED,
        WorkflowEventKind.RUN_SUCCEEDED,
    ]
    assert events[1].state is StepState.RUNNING
    assert events[2].duration_ms is not None
    assert events[0].to_dict() == {
        "schema_version": 1,
        "sequence": 1,
        "kind": "run_started",
        "run_id": "event-run",
        "workflow": "events-test",
        "occurred_at": events[0].occurred_at,
        "step_id": None,
        "attempt": None,
        "state": None,
        "duration_ms": None,
        "error_type": None,
        "resumed": False,
    }


@pytest.mark.asyncio
async def test_retry_failure_and_blocking_events_are_explicit() -> None:
    events: list[WorkflowEvent] = []

    async def fail(_context: ActionContext) -> None:
        raise ConnectionError("private failure detail")

    result = await WorkflowRunner(
        {"fail": fail, "unused": lambda _context: None},
        event_handlers=(events.append,),
        fail_fast=False,
    ).run(
        workflow(
            WorkflowStep(id="bad", action="fail", retries=1),
            WorkflowStep(id="later", action="unused", dependencies=("bad",)),
            WorkflowStep(id="last", action="unused", dependencies=("bad",)),
        )
    )

    assert not result.succeeded
    assert [event.kind for event in events] == [
        WorkflowEventKind.RUN_STARTED,
        WorkflowEventKind.STEP_ATTEMPT_STARTED,
        WorkflowEventKind.STEP_RETRY_SCHEDULED,
        WorkflowEventKind.STEP_ATTEMPT_STARTED,
        WorkflowEventKind.STEP_FAILED,
        WorkflowEventKind.STEP_BLOCKED,
        WorkflowEventKind.STEP_BLOCKED,
        WorkflowEventKind.RUN_FAILED,
    ]
    retry = events[2]
    assert retry.attempt == 1
    assert retry.error_type == "ConnectionError"
    assert [event.step_id for event in events[-3:-1]] == ["later", "last"]
    assert all(event.error_type == "DependencyFailed" for event in events[-3:-1])


@pytest.mark.asyncio
async def test_resume_emits_restored_steps_and_checkpoint_commits() -> None:
    store = InMemoryCheckpointStore()
    first_events: list[WorkflowEvent] = []
    definition = workflow(WorkflowStep(id="cached", action="ok"))
    await WorkflowRunner(
        {"ok": lambda _context: {"value": 1}},
        event_handlers=(first_events.append,),
    ).run(definition, run_id="resume-events", checkpoint_store=store)

    assert WorkflowEventKind.CHECKPOINT_SAVED in [event.kind for event in first_events]

    resumed_events: list[WorkflowEvent] = []
    resumed = await WorkflowRunner(
        {"ok": lambda _context: pytest.fail("restored action must not run")},
        event_handlers=(resumed_events.append,),
    ).run(
        definition,
        run_id="resume-events",
        checkpoint_store=store,
        resume=True,
    )

    assert resumed.succeeded
    assert [event.kind for event in resumed_events] == [
        WorkflowEventKind.RUN_STARTED,
        WorkflowEventKind.STEP_RESTORED,
        WorkflowEventKind.RUN_SUCCEEDED,
    ]
    assert resumed_events[0].resumed is True
    assert resumed_events[1].resumed is True
    assert resumed_events[1].state is StepState.SUCCEEDED


@pytest.mark.asyncio
async def test_events_exclude_sensitive_payload_values() -> None:
    events: list[WorkflowEvent] = []

    def source(_context: ActionContext) -> str:
        return "secret-output-value"

    def fail(_context: ActionContext) -> None:
        raise RuntimeError("secret-error-message")

    await WorkflowRunner(
        {"source": source, "fail": fail},
        event_handlers=(events.append,),
    ).run(
        workflow(
            WorkflowStep(
                id="source",
                action="source",
                parameters={"credential": "secret-parameter-value"},
            ),
            WorkflowStep(id="fail", action="fail", dependencies=("source",)),
        ),
        {"token": "secret-input-value"},
        run_id="privacy-test",
    )

    rendered = json.dumps([event.to_dict() for event in events])
    for secret in (
        "secret-output-value",
        "secret-error-message",
        "secret-parameter-value",
        "secret-input-value",
        "privacy-test:source",
    ):
        assert secret not in rendered
    assert "RuntimeError" in rendered


@pytest.mark.asyncio
async def test_async_event_handler_is_serialized_across_concurrent_steps() -> None:
    events: list[WorkflowEvent] = []
    active = 0
    peak = 0

    async def observe(event: WorkflowEvent) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.001)
        events.append(event)
        active -= 1

    definition = workflow(
        *(WorkflowStep(id=f"step-{index}", action="ok") for index in range(4)),
        max_concurrency=4,
    )
    result = await WorkflowRunner(
        {"ok": lambda _context: None},
        event_handlers=(observe,),
    ).run(definition)

    assert result.succeeded
    assert peak == 1
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_event_handler_failure_is_explicit_and_stops_before_actions() -> None:
    action_calls = 0

    def action(_context: ActionContext) -> None:
        nonlocal action_calls
        action_calls += 1

    def broken(_event: WorkflowEvent) -> None:
        raise OSError("sink unavailable")

    runner = WorkflowRunner({"action": action}, event_handlers=(broken,))
    with pytest.raises(EventDeliveryError, match="run_started") as raised:
        await runner.run(workflow(WorkflowStep(id="one", action="action")))

    assert isinstance(raised.value.__cause__, OSError)
    assert action_calls == 0
    with pytest.raises(TypeError, match="callable"):
        runner.register_event_handler(None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cancellation_emits_step_and_run_terminal_events() -> None:
    events: list[WorkflowEvent] = []
    started = asyncio.Event()

    async def wait(_context: ActionContext) -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        WorkflowRunner(
            {"wait": wait},
            event_handlers=(events.append,),
        ).run(workflow(WorkflowStep(id="waiting", action="wait")))
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [event.kind for event in events][-2:] == [
        WorkflowEventKind.STEP_CANCELLED,
        WorkflowEventKind.RUN_CANCELLED,
    ]
    assert events[-2].state is StepState.CANCELLED


def test_event_handler_type_accepts_awaitable_factory() -> None:
    observed: list[str] = []

    def factory(event: WorkflowEvent) -> Any:
        async def record() -> None:
            observed.append(event.kind.value)

        return record()

    result = asyncio.run(
        WorkflowRunner(
            {"ok": lambda _context: None},
            event_handlers=(factory,),
        ).run(workflow(WorkflowStep(id="one", action="ok")))
    )
    assert result.succeeded
    assert observed[0] == "run_started"
