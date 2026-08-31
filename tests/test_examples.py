# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize(
    "name",
    [
        "python_workflow.py",
        "observe_workflow.py",
        "sqlite_batch_runs.py",
        "compensating_order.py",
        "subprocess_pipeline.py",
    ],
)
def test_documented_examples_run_outside_the_checkout(tmp_path: Path, name: str) -> None:
    """Shipped examples must use the installed package and produce their claimed outcome."""
    result = subprocess.run(
        [sys.executable, "-I", str(EXAMPLES / name)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    if name == "python_workflow.py":
        report = ast.literal_eval(result.stdout)
        assert report["status"] == "succeeded"
        assert report["steps"][-1]["output"] == 10
    elif name == "observe_workflow.py":
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert events[0]["kind"] == "run_started"
        assert events[-1]["kind"] == "run_succeeded"
        assert sum(event["kind"] == "step_retry_scheduled" for event in events) == 1
    elif name == "sqlite_batch_runs.py":
        summaries = [ast.literal_eval(line) for line in result.stdout.splitlines()]
        assert len(summaries) == 3
        assert len({summary["run_id"] for summary in summaries}) == 3
        assert all(summary["successful_steps"] == 1 for summary in summaries)
        assert (tmp_path / ".samsarix-runs/imports.db").is_file()
    elif name == "compensating_order.py":
        report = json.loads(result.stdout)
        assert report["status"] == "failed"
        assert report["compensation_status"] == "succeeded"
        # Reports retain definition order, not reverse-handler execution order.
        assert [step["step_id"] for step in report["compensations"]] == ["reserve", "charge"]
        assert all(
            step["state"] == "succeeded" and step["output"]["reversed"] == step["step_id"]
            for step in report["compensations"]
        )
    else:
        report = json.loads(result.stdout)
        assert report["status"] == "succeeded"
        assert report["steps"][-1]["output"]["summary"] == "validated 5 words"
