# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Feed ordered lifecycle events into application-owned logs and metrics."""

from __future__ import annotations

import asyncio
import json
from collections import Counter

from samsarix_orchestration import (
    ActionContext,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowEventKind,
    WorkflowRunner,
)


class OperationsObserver:
    """Minimal adapter an application can replace with its telemetry client."""

    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def __call__(self, event: WorkflowEvent) -> None:
        self.counts[event.kind.value] += 1
        print(json.dumps(event.to_dict(), separators=(",", ":")))


async def main() -> None:
    """Execute a retrying API-style pipeline and report lifecycle counts."""
    calls = 0

    async def fetch(_context: ActionContext) -> dict[str, int]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("simulated transient API failure")
        return {"records": 12}

    def publish(context: ActionContext) -> dict[str, int]:
        return dict(context.dependencies["fetch"])

    definition = WorkflowDefinition.from_dict(
        {
            "name": "observed-import",
            "steps": [
                {"id": "fetch", "action": "fetch", "retries": 1},
                {"id": "publish", "action": "publish", "dependencies": ["fetch"]},
            ],
        }
    )
    observer = OperationsObserver()
    result = await WorkflowRunner(
        {"fetch": fetch, "publish": publish},
        event_handlers=(observer,),
    ).run(definition, run_id="observed-import-1")
    assert result.succeeded
    assert observer.counts[WorkflowEventKind.STEP_RETRY_SCHEDULED.value] == 1


if __name__ == "__main__":
    asyncio.run(main())
