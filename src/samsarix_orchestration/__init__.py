# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Public API for Samsarix Orchestration."""

from .checkpoints import (
    MAX_CHECKPOINT_BYTES,
    InMemoryCheckpointStore,
    JsonDirectoryCheckpointStore,
)
from .events import EventHandler, StepState, WorkflowEvent, WorkflowEventKind
from .planning import (
    PLAN_SCHEMA_VERSION,
    PlannedStep,
    PlanWave,
    WorkflowPlan,
    build_workflow_plan,
)
from .runtime import (
    MAX_APPROVAL_ACTOR_CHARACTERS,
    MAX_APPROVAL_REASON_CHARACTERS,
    ActionContext,
    ApprovalDecision,
    ApprovalDecisionKind,
    ApprovalRecord,
    ApprovalStatus,
    CheckpointStore,
    EventDeliveryError,
    StepResult,
    WorkflowCheckpoint,
    WorkflowExecutionError,
    WorkflowRunner,
    WorkflowRunResult,
)
from .spec import (
    MAX_APPROVAL_PROMPT_CHARACTERS,
    MAX_WORKFLOW_BYTES,
    ApprovalPolicy,
    CompensationPolicy,
    ValidationIssue,
    WorkflowDefinition,
    WorkflowSpecError,
    WorkflowStep,
    load_workflow,
)
from .sqlite_store import (
    MAX_LIST_LIMIT,
    SQLITE_APPLICATION_ID,
    SQLITE_SCHEMA_VERSION,
    CheckpointSummary,
    SqliteCheckpointStore,
)

__all__ = [
    "MAX_CHECKPOINT_BYTES",
    "MAX_APPROVAL_PROMPT_CHARACTERS",
    "MAX_APPROVAL_ACTOR_CHARACTERS",
    "MAX_APPROVAL_REASON_CHARACTERS",
    "MAX_LIST_LIMIT",
    "MAX_WORKFLOW_BYTES",
    "PLAN_SCHEMA_VERSION",
    "ActionContext",
    "ApprovalDecision",
    "ApprovalDecisionKind",
    "ApprovalPolicy",
    "ApprovalRecord",
    "ApprovalStatus",
    "CompensationPolicy",
    "CheckpointSummary",
    "CheckpointStore",
    "EventDeliveryError",
    "EventHandler",
    "InMemoryCheckpointStore",
    "JsonDirectoryCheckpointStore",
    "PlanWave",
    "PlannedStep",
    "SQLITE_APPLICATION_ID",
    "SQLITE_SCHEMA_VERSION",
    "SqliteCheckpointStore",
    "StepResult",
    "StepState",
    "ValidationIssue",
    "WorkflowDefinition",
    "WorkflowEvent",
    "WorkflowEventKind",
    "WorkflowPlan",
    "WorkflowCheckpoint",
    "WorkflowExecutionError",
    "WorkflowRunResult",
    "WorkflowRunner",
    "WorkflowSpecError",
    "WorkflowStep",
    "build_workflow_plan",
    "load_workflow",
]

__version__ = "0.1.0"
