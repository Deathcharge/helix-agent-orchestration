# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Run a real two-step workflow with application-defined Python actions."""

import asyncio

from samsarix_orchestration import ActionContext, WorkflowDefinition, WorkflowRunner


async def fetch(_context: ActionContext) -> dict[str, list[int]]:
    return {"values": [2, 3, 5]}


def total(context: ActionContext) -> int:
    values = context.dependencies["fetch"]["values"]
    return sum(values)


async def main() -> None:
    workflow = WorkflowDefinition.from_dict(
        {
            "version": 1,
            "name": "sum-values",
            "steps": [
                {"id": "fetch", "agent": "source", "action": "fetch"},
                {
                    "id": "total",
                    "agent": "calculator",
                    "action": "total",
                    "dependencies": ["fetch"],
                },
            ],
        }
    )
    result = await WorkflowRunner({"fetch": fetch, "total": total}).run(workflow)
    print(result.to_dict())


if __name__ == "__main__":
    asyncio.run(main())
