# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Run blocking or legacy-style work through the bounded subprocess JSON protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def worker_main() -> int:
    """Serve one protocol request without importing the orchestration package."""
    request = json.load(sys.stdin)
    if request.get("schema_version") != 1:
        print("unsupported protocol", file=sys.stderr)
        return 2
    operation = request["step"]["parameters"]["operation"]
    if operation == "inspect":
        words = request["workflow_input"]["text"].split()
        output: Any = {
            "word_count": len(words),
            "idempotency_key": request["idempotency_key"],
        }
    elif operation == "summarize":
        inspected = request["dependencies"]["inspect"]
        output = {
            "summary": f"validated {inspected['word_count']} words",
            "worker_kind": request["kind"],
        }
    else:
        print(f"unknown operation: {operation}", file=sys.stderr)
        return 3
    json.dump(output, sys.stdout, separators=(",", ":"), sort_keys=True)
    return 0


async def run_example() -> None:
    """Register one fixed executable and orchestrate two isolated invocations."""
    from samsarix_orchestration import (  # Imported only by the parent process.
        WorkflowDefinition,
        WorkflowRunner,
        WorkflowStep,
        subprocess_action,
    )

    worker = subprocess_action(
        (
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "--worker",
        )
    )
    workflow = WorkflowDefinition(
        name="isolated-document-pipeline",
        max_concurrency=2,
        steps=(
            WorkflowStep(
                id="inspect",
                action="external-tool",
                parameters={"operation": "inspect"},
            ),
            WorkflowStep(
                id="summarize",
                action="external-tool",
                dependencies=("inspect",),
                parameters={"operation": "summarize"},
            ),
        ),
    )
    result = await WorkflowRunner({"external-tool": worker}).run(
        workflow,
        {"text": "bounded local tools remain inspectable"},
        run_id="subprocess-example",
    )
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        raise SystemExit(worker_main())
    import asyncio

    asyncio.run(run_example())
