# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

import helix_orchestration
import samsarix_orchestration
from helix_orchestration.cli import build_parser as build_legacy_parser


def test_public_api_has_release_version() -> None:
    assert samsarix_orchestration.__version__ == "0.1.0"
    assert helix_orchestration.__version__ == samsarix_orchestration.__version__
    assert helix_orchestration.WorkflowRunner is samsarix_orchestration.WorkflowRunner
    assert (
        helix_orchestration.JsonDirectoryCheckpointStore
        is samsarix_orchestration.JsonDirectoryCheckpointStore
    )
    assert helix_orchestration.SqliteCheckpointStore is samsarix_orchestration.SqliteCheckpointStore
    assert helix_orchestration.WorkflowEvent is samsarix_orchestration.WorkflowEvent
    assert helix_orchestration.ApprovalDecision is samsarix_orchestration.ApprovalDecision
    assert helix_orchestration.ApprovalPolicy is samsarix_orchestration.ApprovalPolicy
    assert helix_orchestration.CompensationPolicy is samsarix_orchestration.CompensationPolicy
    assert helix_orchestration.CompensationContext is samsarix_orchestration.CompensationContext
    assert helix_orchestration.CheckpointPhase is samsarix_orchestration.CheckpointPhase
    assert helix_orchestration.WorkflowPlan is samsarix_orchestration.WorkflowPlan
    assert helix_orchestration.subprocess_action is samsarix_orchestration.subprocess_action
    assert helix_orchestration.build_workflow_plan is samsarix_orchestration.build_workflow_plan
    assert build_legacy_parser().prog == "helix-orchestration"
