# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Validated, JSON-serializable workflow specifications."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_WORKFLOW_BYTES = 1_048_576
MAX_STEPS = 256
MAX_APPROVAL_PROMPT_CHARACTERS = 500
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_STRICT_WORKFLOW_FIELDS = {"version", "name", "description", "max_concurrency", "steps"}
_STRICT_STEP_FIELDS = {
    "id",
    "action",
    "agent",
    "dependencies",
    "parameters",
    "timeout_seconds",
    "retries",
    "retry_delay_seconds",
    "approval",
    "compensation",
}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One actionable workflow validation problem."""

    code: str
    path: str
    message: str


class WorkflowSpecError(ValueError):
    """Raised when a workflow document is unreadable or invalid."""

    def __init__(self, message: str, issues: tuple[ValidationIssue, ...] = ()) -> None:
        super().__init__(message)
        self.issues = issues


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    """A static pre-action approval barrier for a strict schema-v2/v3 step."""

    prompt: str

    def to_dict(self) -> dict[str, str]:
        """Return the stable JSON representation."""
        return {"prompt": self.prompt}


@dataclass(frozen=True, slots=True)
class CompensationPolicy:
    """A schema-v3 action that reverses one successful step's external effect."""

    action: str
    timeout_seconds: float = 30.0
    retries: int = 0
    retry_delay_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        return {
            "action": self.action,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "retry_delay_seconds": self.retry_delay_seconds,
        }


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    """A bounded unit of work executed by a registered action handler."""

    id: str
    action: str
    agent: str = "local"
    dependencies: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    retries: int = 0
    retry_delay_seconds: float = 0.0
    approval: ApprovalPolicy | None = None
    compensation: CompensationPolicy | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation of this step."""
        value: dict[str, Any] = {
            "id": self.id,
            "agent": self.agent,
            "action": self.action,
            "dependencies": list(self.dependencies),
            "parameters": self.parameters,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "retry_delay_seconds": self.retry_delay_seconds,
        }
        if self.approval is not None:
            value["approval"] = self.approval.to_dict()
        if self.compensation is not None:
            value["compensation"] = self.compensation.to_dict()
        return value


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    """A validated directed acyclic workflow graph."""

    name: str
    steps: tuple[WorkflowStep, ...]
    description: str = ""
    version: int = 1
    max_concurrency: int = 4

    @classmethod
    def from_dict(cls, value: Any) -> WorkflowDefinition:
        """Validate and construct a workflow from decoded JSON data."""
        issues = validate_workflow_data(value)
        if issues:
            raise WorkflowSpecError(
                f"Workflow validation failed with {len(issues)} issue(s).",
                issues,
            )

        if not isinstance(value, dict):
            raise WorkflowSpecError("Workflow must be a JSON object.")
        raw_steps = value["steps"]
        if not isinstance(raw_steps, list):
            raise WorkflowSpecError("Workflow steps must be a JSON array.")
        steps = tuple(
            WorkflowStep(
                id=raw["id"],
                agent=raw.get("agent", "local"),
                action=raw["action"],
                dependencies=tuple(raw.get("dependencies", [])),
                parameters=dict(raw.get("parameters", {})),
                timeout_seconds=float(raw.get("timeout_seconds", 30.0)),
                retries=raw.get("retries", 0),
                retry_delay_seconds=float(raw.get("retry_delay_seconds", 0.0)),
                approval=(
                    ApprovalPolicy(prompt=raw["approval"]["prompt"])
                    if isinstance(raw.get("approval"), dict)
                    else None
                ),
                compensation=(
                    CompensationPolicy(
                        action=raw["compensation"]["action"],
                        timeout_seconds=float(raw["compensation"].get("timeout_seconds", 30.0)),
                        retries=raw["compensation"].get("retries", 0),
                        retry_delay_seconds=float(
                            raw["compensation"].get("retry_delay_seconds", 0.0)
                        ),
                    )
                    if isinstance(raw.get("compensation"), dict)
                    else None
                ),
            )
            for raw in raw_steps
        )
        return cls(
            name=value["name"],
            description=value.get("description", ""),
            version=value.get("version", 1),
            max_concurrency=value.get("max_concurrency", 4),
            steps=steps,
        )

    def validate(self) -> tuple[ValidationIssue, ...]:
        """Revalidate a programmatically constructed workflow."""
        return validate_workflow_data(self.to_dict())

    def require_valid(self) -> None:
        """Raise :class:`WorkflowSpecError` unless this workflow is valid."""
        issues = self.validate()
        if issues:
            raise WorkflowSpecError(
                f"Workflow validation failed with {len(issues)} issue(s).",
                issues,
            )

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation of this workflow."""
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "max_concurrency": self.max_concurrency,
            "steps": [step.to_dict() for step in self.steps],
        }


def load_workflow(path: str | Path, *, max_bytes: int = MAX_WORKFLOW_BYTES) -> WorkflowDefinition:
    """Load a UTF-8 JSON workflow with an explicit size bound."""
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise WorkflowSpecError(f"Cannot read workflow {source}: {exc}") from exc
    if not source.is_file():
        raise WorkflowSpecError(f"Workflow path is not a regular file: {source}")
    if size > max_bytes:
        raise WorkflowSpecError(f"Workflow is {size} bytes; the limit is {max_bytes} bytes.")
    try:
        raw = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise WorkflowSpecError(f"Cannot read workflow {source}: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowSpecError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return WorkflowDefinition.from_dict(value)


def validate_workflow_data(value: Any) -> tuple[ValidationIssue, ...]:
    """Return every structural and graph validation issue in decoded JSON data."""
    issues: list[ValidationIssue] = []

    def add(code: str, path: str, message: str) -> None:
        issues.append(ValidationIssue(code=code, path=path, message=message))

    if not isinstance(value, dict):
        return (ValidationIssue("type", "$", "Workflow must be a JSON object."),)

    version = value.get("version", 1)
    if type(version) is not int or version not in (1, 2, 3):
        add("version", "$.version", "Only workflow versions 1, 2, and 3 are supported.")
    if version in (2, 3):
        for field_name in sorted(value.keys() - _STRICT_WORKFLOW_FIELDS):
            add(
                "unknown_field",
                f"$.{field_name}",
                f"Unknown fields are not allowed in workflow version {version}.",
            )

    name = value.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 128:
        add("name", "$.name", "Name must be a non-empty string of at most 128 characters.")

    description = value.get("description", "")
    if not isinstance(description, str) or len(description) > 2_000:
        add(
            "description",
            "$.description",
            "Description must be a string of at most 2,000 characters.",
        )

    max_concurrency = value.get("max_concurrency", 4)
    if type(max_concurrency) is not int or max_concurrency < 1 or max_concurrency > 64:
        add(
            "max_concurrency",
            "$.max_concurrency",
            "max_concurrency must be an integer between 1 and 64.",
        )

    steps = value.get("steps")
    if not isinstance(steps, list):
        add("steps", "$.steps", "Steps must be a JSON array.")
        return tuple(issues)
    if not steps:
        add("steps_empty", "$.steps", "A workflow must contain at least one step.")
    if len(steps) > MAX_STEPS:
        add("steps_limit", "$.steps", f"A workflow may contain at most {MAX_STEPS} steps.")

    valid_ids: list[str] = []
    dependency_rows: list[tuple[int, str, list[str]]] = []
    seen: set[str] = set()
    for index, step in enumerate(steps):
        path = f"$.steps[{index}]"
        if not isinstance(step, dict):
            add("step_type", path, "Each step must be a JSON object.")
            continue
        if version in (2, 3):
            for field_name in sorted(step.keys() - _STRICT_STEP_FIELDS):
                add(
                    "unknown_field",
                    f"{path}.{field_name}",
                    f"Unknown step fields are not allowed in workflow version {version}.",
                )

        step_id = step.get("id")
        if not isinstance(step_id, str) or not _IDENTIFIER.fullmatch(step_id):
            add(
                "step_id",
                f"{path}.id",
                "Step id must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}.",
            )
        elif step_id in seen:
            add("duplicate_step", f"{path}.id", f"Duplicate step id: {step_id}.")
        else:
            seen.add(step_id)
            valid_ids.append(step_id)

        action = step.get("action")
        if not isinstance(action, str) or not _IDENTIFIER.fullmatch(action):
            add(
                "action",
                f"{path}.action",
                "Action must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}.",
            )

        agent = step.get("agent", "local")
        if not isinstance(agent, str) or not _IDENTIFIER.fullmatch(agent):
            add(
                "agent",
                f"{path}.agent",
                "Agent must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}.",
            )

        dependencies = step.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(
            isinstance(item, str) for item in dependencies
        ):
            add("dependencies", f"{path}.dependencies", "Dependencies must be strings.")
            dependencies = []
        elif len(dependencies) != len(set(dependencies)):
            add(
                "duplicate_dependency",
                f"{path}.dependencies",
                "A dependency may be listed only once.",
            )
        if isinstance(step_id, str):
            dependency_rows.append((index, step_id, dependencies))

        parameters = step.get("parameters", {})
        if not isinstance(parameters, dict):
            add("parameters", f"{path}.parameters", "Parameters must be a JSON object.")
        else:
            try:
                json.dumps(parameters, allow_nan=False)
            except (TypeError, ValueError):
                add(
                    "parameters_json",
                    f"{path}.parameters",
                    "Parameters must contain finite JSON values.",
                )

        timeout = step.get("timeout_seconds", 30.0)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
            or timeout > 3_600
        ):
            add(
                "timeout",
                f"{path}.timeout_seconds",
                "timeout_seconds must be greater than 0 and at most 3,600.",
            )

        retries = step.get("retries", 0)
        if type(retries) is not int or retries < 0 or retries > 10:
            add("retries", f"{path}.retries", "retries must be an integer from 0 to 10.")

        retry_delay = step.get("retry_delay_seconds", 0.0)
        if (
            isinstance(retry_delay, bool)
            or not isinstance(retry_delay, (int, float))
            or retry_delay < 0
            or retry_delay > 300
        ):
            add(
                "retry_delay",
                f"{path}.retry_delay_seconds",
                "retry_delay_seconds must be between 0 and 300.",
            )

        if "approval" in step:
            approval = step["approval"]
            if version not in (2, 3):
                add(
                    "approval_version",
                    f"{path}.approval",
                    "Approval gates require workflow version 2 or 3.",
                )
            if not isinstance(approval, dict):
                add(
                    "approval_type",
                    f"{path}.approval",
                    "Approval must be a JSON object.",
                )
            else:
                for field_name in sorted(approval.keys() - {"prompt"}):
                    add(
                        "unknown_field",
                        f"{path}.approval.{field_name}",
                        "Unknown approval fields are not allowed.",
                    )
                prompt = approval.get("prompt")
                if (
                    not isinstance(prompt, str)
                    or not prompt.strip()
                    or len(prompt) > MAX_APPROVAL_PROMPT_CHARACTERS
                ):
                    add(
                        "approval_prompt",
                        f"{path}.approval.prompt",
                        "Approval prompt must be a non-empty string of at most "
                        f"{MAX_APPROVAL_PROMPT_CHARACTERS} characters.",
                    )

        if "compensation" in step:
            compensation = step["compensation"]
            if version != 3:
                add(
                    "compensation_version",
                    f"{path}.compensation",
                    "Compensating actions require workflow version 3.",
                )
            if not isinstance(compensation, dict):
                add(
                    "compensation_type",
                    f"{path}.compensation",
                    "Compensation must be a JSON object.",
                )
            else:
                allowed = {
                    "action",
                    "timeout_seconds",
                    "retries",
                    "retry_delay_seconds",
                }
                for field_name in sorted(compensation.keys() - allowed):
                    add(
                        "unknown_field",
                        f"{path}.compensation.{field_name}",
                        "Unknown compensation fields are not allowed.",
                    )
                compensation_action = compensation.get("action")
                if not isinstance(compensation_action, str) or not _IDENTIFIER.fullmatch(
                    compensation_action
                ):
                    add(
                        "compensation_action",
                        f"{path}.compensation.action",
                        "Compensation action must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}.",
                    )
                compensation_timeout = compensation.get("timeout_seconds", 30.0)
                if (
                    isinstance(compensation_timeout, bool)
                    or not isinstance(compensation_timeout, (int, float))
                    or compensation_timeout <= 0
                    or compensation_timeout > 3_600
                ):
                    add(
                        "compensation_timeout",
                        f"{path}.compensation.timeout_seconds",
                        "Compensation timeout_seconds must be greater than 0 and at most 3,600.",
                    )
                compensation_retries = compensation.get("retries", 0)
                if (
                    type(compensation_retries) is not int
                    or compensation_retries < 0
                    or compensation_retries > 10
                ):
                    add(
                        "compensation_retries",
                        f"{path}.compensation.retries",
                        "Compensation retries must be an integer from 0 to 10.",
                    )
                compensation_delay = compensation.get("retry_delay_seconds", 0.0)
                if (
                    isinstance(compensation_delay, bool)
                    or not isinstance(compensation_delay, (int, float))
                    or compensation_delay < 0
                    or compensation_delay > 300
                ):
                    add(
                        "compensation_retry_delay",
                        f"{path}.compensation.retry_delay_seconds",
                        "Compensation retry_delay_seconds must be between 0 and 300.",
                    )

    known = set(valid_ids)
    graph: dict[str, list[str]] = {step_id: [] for step_id in valid_ids}
    for index, step_id, dependencies in dependency_rows:
        for dependency in dependencies:
            if dependency == step_id:
                add(
                    "self_dependency",
                    f"$.steps[{index}].dependencies",
                    f"Step {step_id} cannot depend on itself.",
                )
            elif dependency not in known:
                add(
                    "unknown_dependency",
                    f"$.steps[{index}].dependencies",
                    f"Unknown dependency: {dependency}.",
                )
            elif step_id in graph:
                graph[step_id].append(dependency)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> bool:
        if step_id in visiting:
            return True
        if step_id in visited:
            return False
        visiting.add(step_id)
        for dependency in graph.get(step_id, []):
            if visit(dependency):
                return True
        visiting.remove(step_id)
        visited.add(step_id)
        return False

    if any(visit(step_id) for step_id in graph):
        add("cycle", "$.steps", "Workflow dependencies must form an acyclic graph.")

    return tuple(issues)
