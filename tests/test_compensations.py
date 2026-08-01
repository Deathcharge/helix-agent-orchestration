# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import copy
from typing import Any

import pytest

from samsarix_orchestration import (
    ApprovalDecision,
    ApprovalPolicy,
    CheckpointPhase,
    CompensationContext,
    CompensationPolicy,
    InMemoryCheckpointStore,
    SqliteCheckpointStore,
    StepResult,
    StepState,
    WorkflowCheckpoint,
    WorkflowDefinition,
    WorkflowEventKind,
    WorkflowExecutionError,
    WorkflowRunner,
    WorkflowStep,
)


def saga_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        version=3,
        name="order-saga",
        max_concurrency=2,
        steps=(
            WorkflowStep(
                id="reserve",
                action="reserve",
                compensation=CompensationPolicy(action="release"),
            ),
            WorkflowStep(
                id="charge",
                action="charge",
                dependencies=("reserve",),
                compensation=CompensationPolicy(action="refund", retries=1),
            ),
            WorkflowStep(id="notify", action="fail", dependencies=("charge",)),
        ),
    )


@pytest.mark.asyncio
async def test_failure_compensates_successful_effects_in_reverse_dependency_order() -> None:
    calls: list[str] = []
    contexts: list[CompensationContext] = []
    events: list[WorkflowEventKind] = []

    async def forward(context: Any) -> dict[str, str]:
        calls.append(context.step.id)
        return {"created": context.step.id}

    async def fail(context: Any) -> None:
        calls.append(context.step.id)
        raise RuntimeError("delivery unavailable")

    async def compensate(context: CompensationContext) -> dict[str, bool]:
        calls.append(f"undo:{context.step.id}")
        contexts.append(context)
        return {"reversed": True}

    store = InMemoryCheckpointStore()
    result = await WorkflowRunner(
        {"reserve": forward, "charge": forward, "fail": fail},
        compensations={"release": compensate, "refund": compensate},
        event_handlers=(lambda event: events.append(event.kind),),
    ).run(saga_workflow(), {"order": 42}, run_id="order-42", checkpoint_store=store)

    assert result.status == "failed"
    assert result.compensation_status == "succeeded"
    assert calls == ["reserve", "charge", "notify", "undo:charge", "undo:reserve"]
    assert [item.step.id for item in contexts] == ["charge", "reserve"]
    assert contexts[0].output == {"created": "charge"}
    assert contexts[0].dependencies == {"reserve": {"created": "reserve"}}
    assert contexts[0].workflow_input == {"order": 42}
    assert contexts[0].idempotency_key == "order-42:charge:compensate"
    assert [item.action for item in result.compensations] == ["release", "refund"]
    assert events.count(WorkflowEventKind.COMPENSATION_SUCCEEDED) == 2
    checkpoint = store.load("order-42")
    assert checkpoint is not None
    assert checkpoint.phase is CheckpointPhase.COMPLETE
    assert [item.step_id for item in checkpoint.compensations] == ["reserve", "charge"]


@pytest.mark.asyncio
async def test_failed_compensation_stops_prerequisites_and_resumes_durably() -> None:
    store = InMemoryCheckpointStore()
    first_calls: list[str] = []

    async def forward(context: Any) -> str:
        return context.step.id

    async def fail(context: Any) -> None:
        raise ValueError(context.step.id)

    async def broken(context: CompensationContext) -> None:
        first_calls.append(context.step.id)
        raise ConnectionError("refund service offline")

    initial = await WorkflowRunner(
        {"reserve": forward, "charge": forward, "fail": fail},
        compensations={"release": broken, "refund": broken},
    ).run(saga_workflow(), run_id="resume-saga", checkpoint_store=store)

    assert initial.compensation_status == "failed"
    assert first_calls == ["charge", "charge"]
    assert initial.compensations[0].state.value == "failed"
    checkpoint = store.load("resume-saga")
    assert checkpoint is not None
    assert checkpoint.phase is CheckpointPhase.COMPENSATING
    assert checkpoint.compensations == ()

    resumed_calls: list[str] = []

    async def restored_forward(context: Any) -> None:
        raise AssertionError("forward handlers must not replay during compensation")

    async def repaired(context: CompensationContext) -> str:
        resumed_calls.append(context.step.id)
        return "ok"

    resumed = await WorkflowRunner(
        {"reserve": restored_forward, "charge": restored_forward, "fail": restored_forward},
        compensations={"release": repaired, "refund": repaired},
    ).run(
        saga_workflow(),
        run_id="resume-saga",
        checkpoint_store=store,
        resume=True,
    )

    assert resumed.status == "failed"
    assert resumed.compensation_status == "succeeded"
    assert resumed.restored_steps == 3
    assert resumed_calls == ["charge", "reserve"]
    completed = store.load("resume-saga")
    assert completed is not None and completed.phase is CheckpointPhase.COMPLETE


@pytest.mark.asyncio
async def test_compensation_configuration_requires_durable_explicit_execution() -> None:
    runner = WorkflowRunner(
        {"reserve": lambda context: None, "charge": lambda context: None, "fail": lambda c: None},
        compensations={"release": lambda context: None, "refund": lambda context: None},
    )
    with pytest.raises(WorkflowExecutionError, match="checkpoint store"):
        await runner.run(saga_workflow(), run_id="missing-store")
    with pytest.raises(WorkflowExecutionError, match="explicit run_id"):
        await runner.run(saga_workflow(), checkpoint_store=InMemoryCheckpointStore())

    missing = WorkflowRunner(
        {"reserve": lambda context: None, "charge": lambda context: None, "fail": lambda c: None},
        compensations={"release": lambda context: None},
    )
    with pytest.raises(WorkflowExecutionError, match="refund"):
        await missing.run(
            saga_workflow(),
            run_id="missing-handler",
            checkpoint_store=InMemoryCheckpointStore(),
        )


@pytest.mark.asyncio
async def test_successful_saga_completes_without_running_compensation() -> None:
    calls: list[str] = []
    workflow = WorkflowDefinition(
        version=3,
        name="successful-saga",
        steps=(
            WorkflowStep(
                id="create",
                action="create",
                compensation=CompensationPolicy(action="delete"),
            ),
        ),
    )
    store = InMemoryCheckpointStore()
    result = await WorkflowRunner(
        {"create": lambda context: {"id": 1}},
        compensations={"delete": lambda context: calls.append(context.step.id)},
    ).run(workflow, run_id="successful-saga", checkpoint_store=store)

    assert result.succeeded is True
    assert result.compensation_status == "not_requested"
    assert result.compensations == ()
    assert calls == []
    checkpoint = store.load("successful-saga")
    assert checkpoint is not None and checkpoint.phase is CheckpointPhase.COMPLETE

    policy_free = WorkflowDefinition(
        version=3,
        name="v3-without-durable-policy",
        steps=(WorkflowStep(id="plain", action="plain"),),
    )
    plain = await WorkflowRunner({"plain": lambda context: "ok"}).run(policy_free)
    assert plain.succeeded is True


@pytest.mark.asyncio
async def test_rejected_approval_compensates_prior_success() -> None:
    workflow = WorkflowDefinition(
        version=3,
        name="approval-saga",
        steps=(
            WorkflowStep(
                id="prepare",
                action="prepare",
                compensation=CompensationPolicy(action="cleanup"),
            ),
            WorkflowStep(
                id="publish",
                action="publish",
                dependencies=("prepare",),
                approval=ApprovalPolicy("Publish?"),
            ),
        ),
    )
    cleaned: list[str] = []
    store = InMemoryCheckpointStore()
    runner = WorkflowRunner(
        {"prepare": lambda context: "prepared", "publish": lambda context: "published"},
        compensations={"cleanup": lambda context: cleaned.append(context.output)},
    )
    paused = await runner.run(workflow, run_id="reject-saga", checkpoint_store=store)
    resumed = await runner.run(
        workflow,
        run_id="reject-saga",
        checkpoint_store=store,
        resume=True,
        approval_decisions=(ApprovalDecision.reject(paused.approvals[0].request_id),),
    )

    assert resumed.status == "rejected"
    assert resumed.compensation_status == "succeeded"
    assert cleaned == ["prepared"]


@pytest.mark.asyncio
async def test_sqlite_persists_complete_compensation_state(tmp_path: Any) -> None:
    store = SqliteCheckpointStore(tmp_path / "sagas.db")

    async def fail(context: Any) -> None:
        raise RuntimeError(context.step.id)

    result = await WorkflowRunner(
        {
            "reserve": lambda context: "reserved",
            "charge": lambda context: "charged",
            "fail": fail,
        },
        compensations={
            "release": lambda context: "released",
            "refund": lambda context: "refunded",
        },
    ).run(saga_workflow(), run_id="sqlite-saga", checkpoint_store=store)

    assert result.compensation_status == "succeeded"
    restored = SqliteCheckpointStore(tmp_path / "sagas.db", create=False).load("sqlite-saga")
    assert restored is not None
    assert restored.phase is CheckpointPhase.COMPLETE
    assert [item.output for item in restored.compensations] == ["released", "refunded"]
    assert store.list_summaries()[0].successful_steps == 2


@pytest.mark.asyncio
async def test_cancellation_leaves_resumable_compensation_checkpoint() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    events: list[WorkflowEventKind] = []
    store = InMemoryCheckpointStore()

    async def fail(context: Any) -> None:
        raise RuntimeError(context.step.id)

    async def wait_to_compensate(context: CompensationContext) -> None:
        started.set()
        await release.wait()

    task = asyncio.create_task(
        WorkflowRunner(
            {
                "reserve": lambda context: "reserved",
                "charge": lambda context: "charged",
                "fail": fail,
            },
            compensations={"release": wait_to_compensate, "refund": wait_to_compensate},
            event_handlers=(lambda event: events.append(event.kind),),
        ).run(saga_workflow(), run_id="cancel-saga", checkpoint_store=store)
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    checkpoint = store.load("cancel-saga")
    assert checkpoint is not None
    assert checkpoint.phase is CheckpointPhase.COMPENSATING
    assert checkpoint.compensations == ()
    assert WorkflowEventKind.COMPENSATION_CANCELLED in events
    assert events[-1] is WorkflowEventKind.RUN_CANCELLED


@pytest.mark.asyncio
async def test_resume_skips_successful_parallel_compensation_and_emits_restored_event() -> None:
    workflow = WorkflowDefinition(
        version=3,
        name="parallel-saga",
        steps=(
            WorkflowStep(
                id="root",
                action="ok",
                compensation=CompensationPolicy("undo"),
            ),
            WorkflowStep(
                id="left",
                action="ok",
                dependencies=("root",),
                compensation=CompensationPolicy("undo"),
            ),
            WorkflowStep(
                id="right",
                action="ok",
                dependencies=("root",),
                compensation=CompensationPolicy("undo"),
            ),
            WorkflowStep(id="end", action="fail", dependencies=("left", "right")),
        ),
    )
    store = InMemoryCheckpointStore()
    initial_calls: list[str] = []

    async def fail(context: Any) -> None:
        raise RuntimeError(context.step.id)

    async def partial(context: CompensationContext) -> str:
        initial_calls.append(context.step.id)
        if context.step.id == "right":
            raise RuntimeError("right unavailable")
        return "undone"

    initial = await WorkflowRunner(
        {"ok": lambda context: context.step.id, "fail": fail},
        compensations={"undo": partial},
    ).run(workflow, run_id="parallel-saga", checkpoint_store=store)
    assert initial.compensation_status == "failed"
    assert set(initial_calls) == {"left", "right"}
    assert "root" not in initial_calls
    checkpoint = store.load("parallel-saga")
    assert checkpoint is not None
    assert [item.step_id for item in checkpoint.compensations] == ["left"]

    resumed_calls: list[str] = []
    events: list[WorkflowEventKind] = []

    async def repaired(context: CompensationContext) -> str:
        resumed_calls.append(context.step.id)
        return "undone"

    resumed = await WorkflowRunner(
        {"ok": lambda context: context.step.id, "fail": fail},
        compensations={"undo": repaired},
        event_handlers=(lambda event: events.append(event.kind),),
    ).run(
        workflow,
        run_id="parallel-saga",
        checkpoint_store=store,
        resume=True,
    )
    assert resumed.compensation_status == "succeeded"
    assert resumed_calls == ["right", "root"]
    assert events.count(WorkflowEventKind.COMPENSATION_RESTORED) == 1


@pytest.mark.asyncio
async def test_resume_rejects_inconsistent_compensation_phases() -> None:
    source = InMemoryCheckpointStore()

    async def fail(context: Any) -> None:
        raise RuntimeError(context.step.id)

    runner = WorkflowRunner(
        {
            "reserve": lambda context: "reserved",
            "charge": lambda context: "charged",
            "fail": fail,
        },
        compensations={"release": lambda context: "released", "refund": lambda c: "refunded"},
    )
    await runner.run(saga_workflow(), run_id="tamper-saga", checkpoint_store=source)
    complete = source.load("tamper-saga")
    assert complete is not None

    cases: list[tuple[dict[str, Any], str]] = []
    incomplete = copy.deepcopy(complete.to_dict())
    incomplete["phase"] = "compensating"
    incomplete["compensations"] = []
    incomplete["steps"].pop()
    cases.append((incomplete, "every terminal forward"))

    missing = copy.deepcopy(complete.to_dict())
    missing["compensations"].pop()
    cases.append((missing, "missing successful compensation"))

    no_unfinished = copy.deepcopy(complete.to_dict())
    no_unfinished["phase"] = "compensating"
    cases.append((no_unfinished, "no valid unfinished"))

    class ForgedStore:
        def __init__(self, value: dict[str, Any]) -> None:
            self.checkpoint = WorkflowCheckpoint.from_dict(value)

        def load(self, _run_id: str) -> WorkflowCheckpoint:
            return self.checkpoint

        def save(self, _checkpoint: WorkflowCheckpoint) -> None:
            raise AssertionError("forged state must fail before saving")

    for value, message in cases:
        with pytest.raises(WorkflowExecutionError, match=message):
            await runner.run(
                saga_workflow(),
                run_id="tamper-saga",
                checkpoint_store=ForgedStore(value),
                resume=True,
            )


@pytest.mark.asyncio
async def test_restore_applies_current_output_bound_to_compensations() -> None:
    store = InMemoryCheckpointStore()

    async def fail(context: Any) -> None:
        raise RuntimeError(context.step.id)

    await WorkflowRunner(
        {
            "reserve": lambda context: context.step.id,
            "charge": lambda context: context.step.id,
            "fail": fail,
        },
        compensations={"release": lambda context: "x" * 100, "refund": lambda c: "ok"},
    ).run(saga_workflow(), run_id="bounded-restore", checkpoint_store=store)

    bounded = WorkflowRunner(
        {
            "reserve": lambda context: context.step.id,
            "charge": lambda context: context.step.id,
            "fail": fail,
        },
        compensations={"release": lambda context: "ok", "refund": lambda context: "ok"},
        max_result_bytes=20,
    )
    with pytest.raises(WorkflowExecutionError, match="checkpoint compensation output.*limit"):
        await bounded.run(
            saga_workflow(),
            run_id="bounded-restore",
            checkpoint_store=store,
            resume=True,
        )


def test_forward_checkpoint_defers_terminal_failures_until_saga_transition() -> None:
    successful = StepResult(
        step_id="reserve",
        agent="local",
        action="reserve",
        state=StepState.SUCCEEDED,
        attempts=1,
        started_at="2026-08-01T00:00:00Z",
        finished_at="2026-08-01T00:00:01Z",
        duration_ms=1.0,
        output="reserved",
    )
    failed = StepResult(
        step_id="notify",
        agent="local",
        action="fail",
        state=StepState.FAILED,
        attempts=1,
        started_at="2026-08-01T00:00:01Z",
        finished_at="2026-08-01T00:00:02Z",
        duration_ms=1.0,
        error={"type": "RuntimeError", "message": "offline"},
    )
    results = {"reserve": successful, "notify": failed}
    identity = {
        "workflow_digest": "a" * 64,
        "input_digest": "b" * 64,
    }

    forward = WorkflowRunner._build_checkpoint(
        saga_workflow(),
        "phase-filter",
        **identity,
        results=results,
        approvals={},
    )
    compensating = WorkflowRunner._build_checkpoint(
        saga_workflow(),
        "phase-filter",
        **identity,
        results=results,
        approvals={},
        phase=CheckpointPhase.COMPENSATING,
    )

    assert [result.step_id for result in forward.steps] == ["reserve"]
    assert [result.step_id for result in compensating.steps] == ["reserve", "notify"]
