# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from samsarix_orchestration import (
    ActionContext,
    ApprovalDecision,
    ApprovalDecisionKind,
    ApprovalPolicy,
    ApprovalStatus,
    EventDeliveryError,
    InMemoryCheckpointStore,
    JsonDirectoryCheckpointStore,
    SqliteCheckpointStore,
    StepState,
    WorkflowCheckpoint,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowExecutionError,
    WorkflowRunner,
    WorkflowStep,
)


def gated_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        version=2,
        name="approval-test",
        steps=(
            WorkflowStep(id="prepare", action="prepare"),
            WorkflowStep(
                id="publish",
                action="publish",
                dependencies=("prepare",),
                approval=ApprovalPolicy(prompt="Publish the prepared result?"),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_schema_v2_without_a_gate_needs_no_checkpoint_store() -> None:
    workflow = WorkflowDefinition(
        version=2,
        name="strict-without-gates",
        steps=(WorkflowStep(id="work", action="work"),),
    )

    result = await WorkflowRunner({"work": lambda _context: "done"}).run(workflow)

    assert result.succeeded
    assert result.approvals == ()
    assert result.to_dict()["schema_version"] == 2
    assert result.to_dict()["approvals"] == []


@pytest.mark.asyncio
async def test_approval_pause_and_resume_is_durable_and_bound() -> None:
    calls = {"prepare": 0, "publish": 0}
    events: list[WorkflowEvent] = []

    def prepare(_context: ActionContext) -> dict[str, int]:
        calls["prepare"] += 1
        return {"value": 42}

    def publish(context: ActionContext) -> str:
        calls["publish"] += 1
        assert context.dependencies == {"prepare": {"value": 42}}
        assert context.approval is not None
        assert context.approval.status is ApprovalStatus.APPROVED
        durable = store.load("approval-42")
        assert durable is not None
        assert durable.approvals[0].status is ApprovalStatus.APPROVED
        return "published"

    store = InMemoryCheckpointStore()
    runner = WorkflowRunner(
        {"prepare": prepare, "publish": publish},
        event_handlers=(events.append,),
    )
    first = await runner.run(
        gated_workflow(),
        {"tenant": "acme"},
        run_id="approval-42",
        checkpoint_store=store,
    )

    assert first.status == "paused"
    assert first.succeeded is False
    assert [step.step_id for step in first.steps] == ["prepare"]
    assert calls == {"prepare": 1, "publish": 0}
    assert len(first.approvals) == 1
    request = first.approvals[0]
    assert request.status is ApprovalStatus.PENDING
    assert len(request.request_id) == 64
    assert first.to_dict()["schema_version"] == 2
    assert [event.kind for event in events][-2:] == [
        WorkflowEventKind.APPROVAL_REQUESTED,
        WorkflowEventKind.RUN_PAUSED,
    ]
    assert all(event.schema_version == 2 for event in events)

    events.clear()
    inspected = await runner.run(
        gated_workflow(),
        {"tenant": "acme"},
        run_id="approval-42",
        checkpoint_store=store,
        resume=True,
    )
    assert inspected.status == "paused"
    assert inspected.approvals[0].request_id == request.request_id
    assert calls == {"prepare": 1, "publish": 0}

    events.clear()
    completed = await runner.run(
        gated_workflow(),
        {"tenant": "acme"},
        run_id="approval-42",
        checkpoint_store=store,
        resume=True,
        approval_decisions=(
            ApprovalDecision(
                request_id=request.request_id,
                decision=ApprovalDecisionKind.APPROVE,
                decided_by="operator-7",
                reason="Validated the prepared output.",
            ),
        ),
    )

    assert completed.succeeded
    assert completed.restored_steps == 1
    assert completed.approvals[0].status is ApprovalStatus.APPROVED
    assert calls == {"prepare": 1, "publish": 1}
    assert WorkflowEventKind.APPROVAL_RECORDED in [event.kind for event in events]
    recorded = next(event for event in events if event.kind is WorkflowEventKind.APPROVAL_RECORDED)
    assert recorded.approval_id == request.request_id
    assert recorded.decision == "approve"
    rendered_events = json.dumps([event.to_dict() for event in events])
    assert "operator-7" not in rendered_events
    assert "Validated the prepared output" not in rendered_events
    assert "Publish the prepared result" not in rendered_events
    checkpoint = store.load("approval-42")
    assert checkpoint is not None
    assert checkpoint.version == 2
    assert checkpoint.approvals[0].status is ApprovalStatus.APPROVED
    assert [step.step_id for step in checkpoint.steps] == ["prepare", "publish"]


@pytest.mark.asyncio
async def test_rejection_is_a_terminal_barrier_and_never_calls_handler() -> None:
    publish_calls = 0

    def publish(_context: ActionContext) -> None:
        nonlocal publish_calls
        publish_calls += 1

    workflow = WorkflowDefinition(
        version=2,
        name="rejection",
        steps=(
            WorkflowStep(
                id="publish",
                action="publish",
                approval=ApprovalPolicy(prompt="Publish externally?"),
            ),
            WorkflowStep(id="notify", action="publish", dependencies=("publish",)),
        ),
    )
    store = InMemoryCheckpointStore()
    runner = WorkflowRunner({"publish": publish})
    paused = await runner.run(
        workflow,
        run_id="reject-run",
        checkpoint_store=store,
    )
    request_id = paused.approvals[0].request_id

    rejected = await runner.run(
        workflow,
        run_id="reject-run",
        checkpoint_store=store,
        resume=True,
        approval_decisions=(
            ApprovalDecision(
                request_id=request_id,
                decision=ApprovalDecisionKind.REJECT,
                reason="Destination is not approved.",
            ),
        ),
    )

    assert rejected.status == "rejected"
    assert [step.state for step in rejected.steps] == [
        StepState.REJECTED,
        StepState.BLOCKED,
    ]
    assert rejected.steps[0].attempts == 0
    assert publish_calls == 0
    assert rejected.approvals[0].status is ApprovalStatus.REJECTED


@pytest.mark.asyncio
async def test_pending_gate_pauses_all_ready_work_before_side_effects() -> None:
    calls: list[str] = []
    workflow = WorkflowDefinition(
        version=2,
        name="global-barrier",
        steps=(
            WorkflowStep(id="ungated", action="run"),
            WorkflowStep(
                id="gated",
                action="run",
                approval=ApprovalPolicy(prompt="Allow this batch?"),
            ),
        ),
    )
    result = await WorkflowRunner({"run": lambda context: calls.append(context.step.id)}).run(
        workflow,
        run_id="barrier-run",
        checkpoint_store=InMemoryCheckpointStore(),
    )
    assert result.status == "paused"
    assert result.steps == ()
    assert calls == []


@pytest.mark.asyncio
async def test_decision_survives_observer_failure_before_handler_dispatch() -> None:
    calls = 0

    def effect(_context: ActionContext) -> str:
        nonlocal calls
        calls += 1
        return "done"

    def observer(event: WorkflowEvent) -> None:
        if event.kind is WorkflowEventKind.APPROVAL_RECORDED:
            raise RuntimeError("observer unavailable")

    workflow = WorkflowDefinition(
        version=2,
        name="observer-recovery",
        steps=(
            WorkflowStep(
                id="effect",
                action="effect",
                approval=ApprovalPolicy(prompt="Run the effect?"),
            ),
        ),
    )
    store = InMemoryCheckpointStore()
    runner = WorkflowRunner({"effect": effect}, event_handlers=(observer,))
    paused = await runner.run(
        workflow,
        run_id="observer-recovery",
        checkpoint_store=store,
    )

    with pytest.raises(EventDeliveryError, match="approval_recorded"):
        await runner.run(
            workflow,
            run_id="observer-recovery",
            checkpoint_store=store,
            resume=True,
            approval_decisions=(ApprovalDecision.approve(paused.approvals[0].request_id),),
        )

    assert calls == 0
    checkpoint = store.load("observer-recovery")
    assert checkpoint is not None
    assert checkpoint.approvals[0].status is ApprovalStatus.APPROVED

    completed = await WorkflowRunner({"effect": effect}).run(
        workflow,
        run_id="observer-recovery",
        checkpoint_store=store,
        resume=True,
    )
    assert completed.succeeded
    assert calls == 1


@pytest.mark.asyncio
async def test_rejection_cancels_other_pending_requests() -> None:
    workflow = WorkflowDefinition(
        version=2,
        name="multiple-approvals",
        steps=(
            WorkflowStep(
                id="first",
                action="run",
                approval=ApprovalPolicy(prompt="Approve first?"),
            ),
            WorkflowStep(
                id="second",
                action="run",
                approval=ApprovalPolicy(prompt="Approve second?"),
            ),
        ),
    )
    calls = 0

    def run(_context: ActionContext) -> None:
        nonlocal calls
        calls += 1

    store = InMemoryCheckpointStore()
    runner = WorkflowRunner({"run": run})
    paused = await runner.run(
        workflow,
        run_id="multiple",
        checkpoint_store=store,
    )
    rejected = await runner.run(
        workflow,
        run_id="multiple",
        checkpoint_store=store,
        resume=True,
        approval_decisions=(
            ApprovalDecision(
                paused.approvals[0].request_id,
                ApprovalDecisionKind.REJECT,
            ),
        ),
    )
    assert rejected.status == "rejected"
    assert calls == 0
    assert [record.status for record in rejected.approvals] == [
        ApprovalStatus.REJECTED,
        ApprovalStatus.CANCELLED,
    ]

    repeated = await runner.run(
        workflow,
        run_id="multiple",
        checkpoint_store=store,
        resume=True,
    )
    assert repeated.status == "rejected"
    assert calls == 0


@pytest.mark.asyncio
async def test_approval_configuration_and_decisions_fail_closed() -> None:
    workflow = gated_workflow()
    runner = WorkflowRunner({"prepare": lambda _context: None, "publish": lambda _: None})
    with pytest.raises(WorkflowExecutionError, match="checkpoint store"):
        await runner.run(workflow, run_id="no-store")
    with pytest.raises(WorkflowExecutionError, match="explicit run_id"):
        await runner.run(workflow, checkpoint_store=InMemoryCheckpointStore())
    with pytest.raises(WorkflowExecutionError, match="resume=True"):
        await runner.run(
            workflow,
            run_id="early-decision",
            checkpoint_store=InMemoryCheckpointStore(),
            approval_decisions=(ApprovalDecision("a" * 64, ApprovalDecisionKind.APPROVE),),
        )

    store = InMemoryCheckpointStore()
    paused = await runner.run(workflow, run_id="invalid-decision", checkpoint_store=store)
    with pytest.raises(WorkflowExecutionError, match="not pending"):
        await runner.run(
            workflow,
            run_id="invalid-decision",
            checkpoint_store=store,
            resume=True,
            approval_decisions=(ApprovalDecision("f" * 64, ApprovalDecisionKind.APPROVE),),
        )
    decision = ApprovalDecision(
        paused.approvals[0].request_id,
        ApprovalDecisionKind.APPROVE,
    )
    with pytest.raises(WorkflowExecutionError, match="duplicate"):
        await runner.run(
            workflow,
            run_id="invalid-decision",
            checkpoint_store=store,
            resume=True,
            approval_decisions=(decision, decision),
        )


@pytest.mark.asyncio
async def test_tampered_approval_context_is_rejected_on_restore() -> None:
    workflow = gated_workflow()
    backing = InMemoryCheckpointStore()
    runner = WorkflowRunner({"prepare": lambda _context: 1, "publish": lambda _: None})
    paused = await runner.run(
        workflow,
        run_id="tampered",
        checkpoint_store=backing,
    )
    checkpoint = backing.load("tampered")
    assert checkpoint is not None
    corrupt = replace(
        checkpoint,
        approvals=(replace(paused.approvals[0], context_digest="0" * 64),),
    )

    class TamperedStore:
        def load(self, _run_id: str) -> WorkflowCheckpoint:
            return corrupt

        def save(self, _checkpoint: WorkflowCheckpoint) -> None:
            raise AssertionError("tampered state must not save")

    with pytest.raises(WorkflowExecutionError, match="does not match"):
        await runner.run(
            workflow,
            run_id="tampered",
            checkpoint_store=TamperedStore(),
            resume=True,
        )


def test_approval_decision_and_checkpoint_validation_are_bounded() -> None:
    with pytest.raises(WorkflowExecutionError, match="request_id"):
        ApprovalDecision.from_dict(
            {
                "request_id": "bad",
                "decision": "approve",
                "decided_by": None,
                "reason": None,
            }
        )
    with pytest.raises(WorkflowExecutionError, match="decided_by"):
        ApprovalDecision.from_dict(
            {
                "request_id": "a" * 64,
                "decision": "approve",
                "decided_by": "x" * 129,
                "reason": None,
            }
        )

    checkpoint = {
        "version": 2,
        "run_id": "run",
        "workflow_digest": "a" * 64,
        "input_digest": "b" * 64,
        "saved_at": "2026-08-01T00:00:00Z",
        "steps": [],
        "approvals": [],
    }
    assert WorkflowCheckpoint.from_dict(checkpoint).version == 2
    missing_approvals = dict(checkpoint)
    missing_approvals.pop("approvals")
    with pytest.raises(WorkflowExecutionError, match="invalid shape"):
        WorkflowCheckpoint.from_dict(missing_approvals)
    extra_field = {**checkpoint, "future": True}
    with pytest.raises(WorkflowExecutionError, match="invalid shape"):
        WorkflowCheckpoint.from_dict(extra_field)
    checkpoint["approvals"] = {}
    with pytest.raises(WorkflowExecutionError, match="JSON array"):
        WorkflowCheckpoint.from_dict(checkpoint)


@pytest.mark.asyncio
@pytest.mark.parametrize("store_kind", ["json", "sqlite"])
async def test_persistent_stores_round_trip_approval_state(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store = (
        JsonDirectoryCheckpointStore(tmp_path / "json")
        if store_kind == "json"
        else SqliteCheckpointStore(tmp_path / "runs.db")
    )
    runner = WorkflowRunner({"prepare": lambda _context: 1, "publish": lambda _: "done"})
    paused = await runner.run(
        gated_workflow(),
        run_id=f"persistent-{store_kind}",
        checkpoint_store=store,
    )
    pending_checkpoint = store.load(f"persistent-{store_kind}")
    assert pending_checkpoint is not None
    completed = await runner.run(
        gated_workflow(),
        run_id=f"persistent-{store_kind}",
        checkpoint_store=store,
        resume=True,
        approval_decisions=(
            ApprovalDecision(
                paused.approvals[0].request_id,
                ApprovalDecisionKind.APPROVE,
            ),
        ),
    )
    assert completed.succeeded
    loaded = store.load(f"persistent-{store_kind}")
    assert loaded is not None
    assert loaded.approvals[0].status is ApprovalStatus.APPROVED
    regressed_approval = replace(
        loaded,
        approvals=(replace(loaded.approvals[0], status=ApprovalStatus.PENDING, decided_at=None),),
    )
    with pytest.raises(WorkflowExecutionError, match="decided approval"):
        store.save(regressed_approval)


@pytest.mark.asyncio
async def test_concurrent_divergent_decisions_have_one_durable_winner(
    tmp_path: Path,
) -> None:
    store = SqliteCheckpointStore(tmp_path / "runs.db")
    workflow = WorkflowDefinition(
        version=2,
        name="decision-race",
        steps=(
            WorkflowStep(
                id="effect",
                action="effect",
                approval=ApprovalPolicy(prompt="Run the external effect?"),
            ),
        ),
    )
    calls = 0

    def effect(_context: ActionContext) -> str:
        nonlocal calls
        calls += 1
        return "done"

    runner = WorkflowRunner({"effect": effect})
    paused = await runner.run(
        workflow,
        run_id="decision-race",
        checkpoint_store=store,
    )
    request_id = paused.approvals[0].request_id

    async def decide(kind: ApprovalDecisionKind) -> object:
        try:
            return await runner.run(
                workflow,
                run_id="decision-race",
                checkpoint_store=store,
                resume=True,
                approval_decisions=(ApprovalDecision(request_id, kind),),
            )
        except WorkflowExecutionError as exc:
            return exc

    outcomes = await asyncio.gather(
        decide(ApprovalDecisionKind.APPROVE),
        decide(ApprovalDecisionKind.REJECT),
    )

    assert sum(isinstance(outcome, WorkflowExecutionError) for outcome in outcomes) == 1
    checkpoint = store.load("decision-race")
    assert checkpoint is not None
    assert checkpoint.approvals[0].status in (
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
    )
    assert calls in (0, 1)
