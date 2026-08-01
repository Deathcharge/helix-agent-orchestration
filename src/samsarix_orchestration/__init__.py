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
    CheckpointPhase,
    CheckpointStore,
    CompensationContext,
    CompensationHandler,
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

# Bandit B404 matches this internal module name; it is not a stdlib subprocess import.
from .subprocess_actions import (  # nosec B404
    DEFAULT_MAX_SUBPROCESS_INPUT_BYTES,
    DEFAULT_MAX_SUBPROCESS_STDERR_BYTES,
    DEFAULT_MAX_SUBPROCESS_STDOUT_BYTES,
    MAX_SUBPROCESS_STREAM_BYTES,
    SUBPROCESS_PROTOCOL_VERSION,
    SubprocessActionError,
    SubprocessActionHandler,
    subprocess_action,
    subprocess_envelope,
)

__all__ = [
    "MAX_CHECKPOINT_BYTES",
    "MAX_APPROVAL_PROMPT_CHARACTERS",
    "MAX_APPROVAL_ACTOR_CHARACTERS",
    "MAX_APPROVAL_REASON_CHARACTERS",
    "MAX_LIST_LIMIT",
    "MAX_WORKFLOW_BYTES",
    "DEFAULT_MAX_SUBPROCESS_INPUT_BYTES",
    "DEFAULT_MAX_SUBPROCESS_STDERR_BYTES",
    "DEFAULT_MAX_SUBPROCESS_STDOUT_BYTES",
    "MAX_SUBPROCESS_STREAM_BYTES",
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
    "CheckpointPhase",
    "CompensationContext",
    "CompensationHandler",
    "EventDeliveryError",
    "EventHandler",
    "InMemoryCheckpointStore",
    "JsonDirectoryCheckpointStore",
    "PlanWave",
    "PlannedStep",
    "SQLITE_APPLICATION_ID",
    "SQLITE_SCHEMA_VERSION",
    "SqliteCheckpointStore",
    "SUBPROCESS_PROTOCOL_VERSION",
    "SubprocessActionError",
    "SubprocessActionHandler",
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
    "subprocess_action",
    "subprocess_envelope",
]

__version__ = "0.1.0"
