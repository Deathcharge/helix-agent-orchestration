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
    assert helix_orchestration.WorkflowEvent is samsarix_orchestration.WorkflowEvent
    assert build_legacy_parser().prog == "helix-orchestration"
