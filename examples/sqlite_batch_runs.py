# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Run and inspect independent workflows in one local SQLite checkpoint database."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from samsarix_orchestration import (
    ActionContext,
    SqliteCheckpointStore,
    WorkflowDefinition,
    WorkflowRunner,
)


def normalize(context: ActionContext) -> dict[str, str]:
    return {"value": str(context.workflow_input["value"]).strip().casefold()}


async def main() -> None:
    workflow = WorkflowDefinition.from_dict(
        {
            "version": 1,
            "name": "normalize-import",
            "steps": [{"id": "normalize", "action": "normalize"}],
        }
    )
    store = SqliteCheckpointStore(Path(".samsarix-runs") / "imports.db")
    runner = WorkflowRunner({"normalize": normalize})
    batch = uuid.uuid4().hex[:8]
    await asyncio.gather(
        *(
            runner.run(
                workflow,
                {"value": value},
                run_id=f"import-{batch}-{index}",
                checkpoint_store=store,
            )
            for index, value in enumerate((" Alpha ", " BETA ", " Gamma "), start=1)
        )
    )
    for summary in store.list_summaries():
        print(summary.to_dict())


if __name__ == "__main__":
    asyncio.run(main())
