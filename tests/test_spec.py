# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samsarix_orchestration import (
    ApprovalPolicy,
    WorkflowDefinition,
    WorkflowSpecError,
    WorkflowStep,
    load_workflow,
)
from samsarix_orchestration.spec import MAX_STEPS, validate_workflow_data


def valid_data() -> dict[str, object]:
    return {
        "version": 1,
        "name": "test-workflow",
        "description": "A real workflow.",
        "max_concurrency": 2,
        "steps": [
            {"id": "first", "agent": "one", "action": "echo"},
            {
                "id": "second",
                "agent": "two",
                "action": "collect",
                "dependencies": ["first"],
                "parameters": {"enabled": True},
                "timeout_seconds": 2,
                "retries": 1,
                "retry_delay_seconds": 0.01,
            },
        ],
    }


def test_workflow_round_trip() -> None:
    workflow = WorkflowDefinition.from_dict(valid_data())

    assert workflow.name == "test-workflow"
    assert workflow.steps[1].dependencies == ("first",)
    assert workflow.to_dict() == {
        **valid_data(),
        "steps": [
            {
                "id": "first",
                "agent": "one",
                "action": "echo",
                "dependencies": [],
                "parameters": {},
                "timeout_seconds": 30.0,
                "retries": 0,
                "retry_delay_seconds": 0.0,
            },
            {
                "id": "second",
                "agent": "two",
                "action": "collect",
                "dependencies": ["first"],
                "parameters": {"enabled": True},
                "timeout_seconds": 2.0,
                "retries": 1,
                "retry_delay_seconds": 0.01,
            },
        ],
    }


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda data: data.update(version=3), "version"),
        (lambda data: data.update(name=""), "name"),
        (lambda data: data.update(description="x" * 2_001), "description"),
        (lambda data: data.update(max_concurrency=0), "max_concurrency"),
        (lambda data: data.update(steps=[]), "steps_empty"),
        (lambda data: data["steps"].append(data["steps"][0]), "duplicate_step"),
        (
            lambda data: data["steps"][1].update(dependencies=["missing"]),
            "unknown_dependency",
        ),
        (
            lambda data: data["steps"][0].update(dependencies=["second"]),
            "cycle",
        ),
        (lambda data: data["steps"][0].update(id="bad id"), "step_id"),
        (lambda data: data["steps"][0].update(action=""), "action"),
        (lambda data: data["steps"][0].update(agent="/bad"), "agent"),
        (
            lambda data: data["steps"][0].update(dependencies=["first"]),
            "self_dependency",
        ),
        (
            lambda data: data["steps"][1].update(dependencies=["first", "first"]),
            "duplicate_dependency",
        ),
        (lambda data: data["steps"][0].update(parameters=[]), "parameters"),
        (lambda data: data["steps"][0].update(timeout_seconds=0), "timeout"),
        (lambda data: data["steps"][0].update(retries=11), "retries"),
        (
            lambda data: data["steps"][0].update(retry_delay_seconds=-1),
            "retry_delay",
        ),
    ],
)
def test_validation_reports_actionable_codes(mutate: object, expected_code: str) -> None:
    data = valid_data()
    assert callable(mutate)
    mutate(data)

    issues = validate_workflow_data(data)

    assert expected_code in {issue.code for issue in issues}
    with pytest.raises(WorkflowSpecError) as raised:
        WorkflowDefinition.from_dict(data)
    assert raised.value.issues == issues


def test_validation_rejects_wrong_root_and_step_shapes() -> None:
    assert validate_workflow_data([])[0].code == "type"
    data = valid_data()
    data["steps"] = ["not-an-object"]
    assert validate_workflow_data(data)[0].code == "step_type"
    data["steps"] = "not-an-array"
    assert any(issue.code == "steps" for issue in validate_workflow_data(data))


def test_step_limit_is_bounded() -> None:
    data = valid_data()
    data["steps"] = [{"id": f"s{index}", "action": "echo"} for index in range(MAX_STEPS + 1)]
    assert any(issue.code == "steps_limit" for issue in validate_workflow_data(data))


def test_programmatic_workflow_is_revalidated() -> None:
    workflow = WorkflowDefinition(name="bad", steps=(WorkflowStep(id="a", action=""),))
    with pytest.raises(WorkflowSpecError):
        workflow.require_valid()


def test_load_workflow_errors_are_bounded_and_clear(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(WorkflowSpecError, match="Invalid JSON"):
        load_workflow(invalid)

    oversized = tmp_path / "large.json"
    oversized.write_text("x" * 20, encoding="utf-8")
    with pytest.raises(WorkflowSpecError, match="limit"):
        load_workflow(oversized, max_bytes=10)

    with pytest.raises(WorkflowSpecError, match="Cannot read"):
        load_workflow(tmp_path / "missing.json")
    with pytest.raises(WorkflowSpecError, match="not a regular file"):
        load_workflow(tmp_path)


def test_load_valid_workflow(tmp_path: Path) -> None:
    source = tmp_path / "workflow.json"
    source.write_text(json.dumps(valid_data()), encoding="utf-8")
    assert load_workflow(source).name == "test-workflow"


def test_version_two_approval_round_trip_is_strict() -> None:
    data = valid_data()
    data["version"] = 2
    steps = data["steps"]
    assert isinstance(steps, list)
    steps[1]["approval"] = {"prompt": "Publish this validated result?"}

    workflow = WorkflowDefinition.from_dict(data)

    assert workflow.version == 2
    assert workflow.steps[1].approval == ApprovalPolicy(prompt="Publish this validated result?")
    assert workflow.to_dict()["steps"][1]["approval"] == {
        "prompt": "Publish this validated result?"
    }


@pytest.mark.parametrize(
    ("version", "approval", "expected_code"),
    [
        (1, {"prompt": "Approve?"}, "approval_version"),
        (2, "Approve?", "approval_type"),
        (2, {}, "approval_prompt"),
        (2, {"prompt": " "}, "approval_prompt"),
        (2, {"prompt": "x" * 501}, "approval_prompt"),
        (2, {"prompt": "Approve?", "future": True}, "unknown_field"),
    ],
)
def test_approval_validation_fails_closed(
    version: int,
    approval: object,
    expected_code: str,
) -> None:
    data = valid_data()
    data["version"] = version
    steps = data["steps"]
    assert isinstance(steps, list)
    steps[0]["approval"] = approval
    assert expected_code in {issue.code for issue in validate_workflow_data(data)}


def test_version_two_rejects_unknown_fields_while_version_one_preserves_annotations() -> None:
    legacy = valid_data()
    legacy["annotation"] = "allowed"
    steps = legacy["steps"]
    assert isinstance(steps, list)
    steps[0]["annotation"] = "allowed"
    assert not validate_workflow_data(legacy)

    strict = valid_data()
    strict["version"] = 2
    strict["annotation"] = "rejected"
    strict_steps = strict["steps"]
    assert isinstance(strict_steps, list)
    strict_steps[0]["annotation"] = "rejected"
    issues = validate_workflow_data(strict)
    assert [issue.code for issue in issues].count("unknown_field") == 2
