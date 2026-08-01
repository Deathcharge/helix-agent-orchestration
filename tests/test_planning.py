# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samsarix_orchestration import (
    PLAN_SCHEMA_VERSION,
    ApprovalPolicy,
    InMemoryCheckpointStore,
    WorkflowDefinition,
    WorkflowRunner,
    WorkflowSpecError,
    WorkflowStep,
    build_workflow_plan,
)
from samsarix_orchestration.cli import main


def planning_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        version=2,
        name="release-plan",
        max_concurrency=2,
        steps=(
            WorkflowStep(
                id="publish",
                action="publish",
                agent="release",
                dependencies=("transform",),
                approval=ApprovalPolicy(prompt="Publish the release?"),
            ),
            WorkflowStep(id="source", action="load", agent="reader"),
            WorkflowStep(
                id="audit",
                action="audit",
                agent="reviewer",
                dependencies=("source",),
            ),
            WorkflowStep(
                id="transform",
                action="transform",
                agent="builder",
                dependencies=("source",),
                retries=2,
                timeout_seconds=12.5,
            ),
        ),
    )


def test_plan_derives_deterministic_waves_and_graph_metadata() -> None:
    plan = build_workflow_plan(planning_workflow())

    assert plan.schema_version == PLAN_SCHEMA_VERSION == 1
    assert len(plan.workflow_digest) == 64
    assert plan.roots == ("source",)
    assert plan.leaves == ("publish", "audit")
    assert plan.approval_steps == ("publish",)
    assert plan.longest_dependency_chain == ("source", "transform", "publish")
    assert plan.edge_count == 3
    assert plan.max_wave_width == 2
    assert [(wave.index, wave.step_ids, wave.approval_barrier) for wave in plan.waves] == [
        (1, ("source",), False),
        (2, ("audit", "transform"), False),
        (3, ("publish",), True),
    ]
    assert [step.id for step in plan.steps] == ["publish", "source", "audit", "transform"]
    transform = next(step for step in plan.steps if step.id == "transform")
    assert transform.wave == 2
    assert transform.max_attempts == 3
    assert transform.timeout_seconds == 12.5
    assert transform.dependents == ("publish",)

    rendered = plan.to_dict()
    assert rendered["step_count"] == 4
    assert rendered["workflow_digest"] == plan.workflow_digest
    assert rendered["wave_count"] == 3
    assert rendered["max_concurrency"] == 2
    assert rendered["waves"][-1] == {
        "index": 3,
        "step_ids": ["publish"],
        "approval_barrier": True,
    }


def test_plan_text_and_mermaid_are_stable_and_omit_approval_prompt() -> None:
    plan = build_workflow_plan(planning_workflow())

    text = plan.to_text()
    assert 'Workflow: "release-plan" (schema 2)' in text
    assert "Wave 3 [approval barrier]:" in text
    assert "publish: action=publish | agent=release" in text
    assert "Longest dependency chain: source -> transform -> publish" in text

    mermaid = plan.to_mermaid()
    assert mermaid.startswith("flowchart TD\n")
    assert 'n0["publish<br/>publish · release<br/>(approval)"]' in mermaid
    assert "n1 --> n3" in mermaid
    assert "n3 --> n0" in mermaid
    assert "class n0 approval" in mermaid
    assert "Publish the release?" not in mermaid


@pytest.mark.asyncio
async def test_plan_digest_matches_runtime_checkpoint_identity() -> None:
    workflow = planning_workflow()
    plan = build_workflow_plan(workflow)
    store = InMemoryCheckpointStore()
    actions = {
        name: (lambda context: context.step.id)
        for name in ("publish", "load", "audit", "transform")
    }

    paused = await WorkflowRunner(actions).run(
        workflow,
        run_id="plan-digest",
        checkpoint_store=store,
    )

    assert paused.status == "paused"
    checkpoint = store.load("plan-digest")
    assert checkpoint is not None
    assert plan.workflow_digest == checkpoint.workflow_digest


def test_plan_revalidates_programmatic_workflows() -> None:
    invalid = WorkflowDefinition(
        name="cycle",
        steps=(
            WorkflowStep(id="first", action="run", dependencies=("second",)),
            WorkflowStep(id="second", action="run", dependencies=("first",)),
        ),
    )
    with pytest.raises(WorkflowSpecError, match="validation failed"):
        build_workflow_plan(invalid)


def test_cli_plan_supports_text_json_and_mermaid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "approval.json"
    assert main(["init", str(workflow), "--approval"]) == 0
    capsys.readouterr()

    assert main(["plan", str(workflow)]) == 0
    text = capsys.readouterr().out
    assert "Wave 2 [approval barrier]:" in text

    assert main(["plan", str(workflow), "--format", "json"]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workflow"] == "production-release-approval"
    assert rendered["approval_steps"] == ["publish"]

    assert main(["plan", str(workflow), "--format", "mermaid"]) == 0
    mermaid = capsys.readouterr().out
    assert mermaid.startswith("flowchart TD\n")
    assert "class n1 approval" in mermaid
