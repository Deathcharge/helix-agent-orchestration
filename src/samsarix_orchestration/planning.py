# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Deterministic, side-effect-free workflow planning and visualization."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from typing import Any

from .spec import WorkflowDefinition

PLAN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """One validated step annotated with its static dependency wave."""

    position: int
    id: str
    action: str
    agent: str
    dependencies: tuple[str, ...]
    dependents: tuple[str, ...]
    wave: int
    approval_required: bool
    timeout_seconds: float
    max_attempts: int

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        return {
            "position": self.position,
            "id": self.id,
            "action": self.action,
            "agent": self.agent,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "wave": self.wave,
            "approval_required": self.approval_required,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True, slots=True)
class PlanWave:
    """A dependency-ready group considered together by the local runner."""

    index: int
    step_ids: tuple[str, ...]
    approval_barrier: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON representation."""
        return {
            "index": self.index,
            "step_ids": list(self.step_ids),
            "approval_barrier": self.approval_barrier,
        }


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    """Static execution surface derived from one validated workflow."""

    workflow: str
    workflow_digest: str
    workflow_schema_version: int
    max_concurrency: int
    roots: tuple[str, ...]
    leaves: tuple[str, ...]
    longest_dependency_chain: tuple[str, ...]
    steps: tuple[PlannedStep, ...]
    waves: tuple[PlanWave, ...]
    schema_version: int = PLAN_SCHEMA_VERSION

    @property
    def edge_count(self) -> int:
        """Return the number of dependency edges."""
        return sum(len(step.dependencies) for step in self.steps)

    @property
    def approval_steps(self) -> tuple[str, ...]:
        """Return gated step identifiers in workflow order."""
        return tuple(step.id for step in self.steps if step.approval_required)

    @property
    def max_wave_width(self) -> int:
        """Return the widest static dependency wave."""
        return max(len(wave.step_ids) for wave in self.waves)

    def to_dict(self) -> dict[str, Any]:
        """Return the stable machine-readable plan representation."""
        return {
            "schema_version": self.schema_version,
            "workflow": self.workflow,
            "workflow_digest": self.workflow_digest,
            "workflow_schema_version": self.workflow_schema_version,
            "step_count": len(self.steps),
            "edge_count": self.edge_count,
            "wave_count": len(self.waves),
            "max_wave_width": self.max_wave_width,
            "max_concurrency": self.max_concurrency,
            "roots": list(self.roots),
            "leaves": list(self.leaves),
            "approval_steps": list(self.approval_steps),
            "longest_dependency_chain": list(self.longest_dependency_chain),
            "waves": [wave.to_dict() for wave in self.waves],
            "steps": [step.to_dict() for step in self.steps],
        }

    def to_text(self) -> str:
        """Render a compact offline review of dependency waves and gates."""
        lines = [
            f"Workflow: {json.dumps(self.workflow, ensure_ascii=False)} "
            f"(schema {self.workflow_schema_version})",
            f"Workflow digest: {self.workflow_digest}",
            f"Steps: {len(self.steps)} | Edges: {self.edge_count} | "
            f"Waves: {len(self.waves)} | Max concurrency: {self.max_concurrency}",
            f"Roots: {', '.join(self.roots)}",
            f"Leaves: {', '.join(self.leaves)}",
            f"Longest dependency chain: {' -> '.join(self.longest_dependency_chain)}",
        ]
        by_id = {step.id: step for step in self.steps}
        for wave in self.waves:
            suffix = " [approval barrier]" if wave.approval_barrier else ""
            lines.append(f"Wave {wave.index}{suffix}:")
            for step_id in wave.step_ids:
                step = by_id[step_id]
                gate = " | approval required" if step.approval_required else ""
                lines.append(
                    f"  - {step.id}: action={step.action} | agent={step.agent} | "
                    f"attempts<={step.max_attempts} | timeout={step.timeout_seconds:g}s{gate}"
                )
        return "\n".join(lines) + "\n"

    def to_mermaid(self) -> str:
        """Render dependency edges as safe, deterministic Mermaid source."""
        node_ids = {step.id: f"n{index}" for index, step in enumerate(self.steps)}
        lines = ["flowchart TD", '  start(("start"))', '  finish(("finish"))']
        for step in self.steps:
            label = (
                f"{html.escape(step.id, quote=True)}<br/>"
                f"{html.escape(step.action, quote=True)} · "
                f"{html.escape(step.agent, quote=True)}"
            )
            if step.approval_required:
                label += "<br/>(approval)"
            lines.append(f'  {node_ids[step.id]}["{label}"]')
        for root in self.roots:
            lines.append(f"  start --> {node_ids[root]}")
        for step in self.steps:
            for dependency in step.dependencies:
                lines.append(f"  {node_ids[dependency]} --> {node_ids[step.id]}")
        for leaf in self.leaves:
            lines.append(f"  {node_ids[leaf]} --> finish")
        if self.approval_steps:
            lines.append("  classDef approval fill:#fff3cd,stroke:#9a6700,stroke-width:2px")
            gated = ",".join(node_ids[step_id] for step_id in self.approval_steps)
            lines.append(f"  class {gated} approval")
        return "\n".join(lines) + "\n"


def build_workflow_plan(workflow: WorkflowDefinition) -> WorkflowPlan:
    """Validate a workflow and derive deterministic dependency waves without running it."""
    workflow.require_valid()
    ordered = {step.id: step for step in workflow.steps}
    remaining = set(ordered)
    completed: set[str] = set()
    waves: list[PlanWave] = []
    wave_by_step: dict[str, int] = {}
    while remaining:
        ready = tuple(
            step
            for step in workflow.steps
            if step.id in remaining and set(step.dependencies) <= completed
        )
        if not ready:
            raise RuntimeError("Validated workflow unexpectedly has no dependency-ready step.")
        wave_index = len(waves) + 1
        waves.append(
            PlanWave(
                index=wave_index,
                step_ids=tuple(step.id for step in ready),
                approval_barrier=any(step.approval is not None for step in ready),
            )
        )
        for step in ready:
            wave_by_step[step.id] = wave_index
            remaining.remove(step.id)
            completed.add(step.id)

    dependents: dict[str, list[str]] = {step.id: [] for step in workflow.steps}
    for step in workflow.steps:
        for dependency in step.dependencies:
            dependents[dependency].append(step.id)

    planned_steps = tuple(
        PlannedStep(
            position=position,
            id=step.id,
            action=step.action,
            agent=step.agent,
            dependencies=step.dependencies,
            dependents=tuple(dependents[step.id]),
            wave=wave_by_step[step.id],
            approval_required=step.approval is not None,
            timeout_seconds=step.timeout_seconds,
            max_attempts=step.retries + 1,
        )
        for position, step in enumerate(workflow.steps, start=1)
    )

    best_chain: dict[str, tuple[str, ...]] = {}
    for wave in waves:
        for step_id in wave.step_ids:
            step = ordered[step_id]
            prefix = max(
                (best_chain[dependency] for dependency in step.dependencies),
                key=len,
                default=(),
            )
            best_chain[step_id] = (*prefix, step_id)
    longest = max(best_chain.values(), key=len)

    return WorkflowPlan(
        workflow=workflow.name,
        workflow_digest=_json_digest(workflow.to_dict()),
        workflow_schema_version=workflow.version,
        max_concurrency=workflow.max_concurrency,
        roots=tuple(step.id for step in workflow.steps if not step.dependencies),
        leaves=tuple(step.id for step in workflow.steps if not dependents[step.id]),
        longest_dependency_chain=longest,
        steps=planned_steps,
        waves=tuple(waves),
    )


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "PLAN_SCHEMA_VERSION",
    "PlanWave",
    "PlannedStep",
    "WorkflowPlan",
    "build_workflow_plan",
]
