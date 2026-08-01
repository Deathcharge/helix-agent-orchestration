# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Run a provider-free order Saga and print its reverse-effect evidence."""

from __future__ import annotations

import asyncio
import json

from samsarix_orchestration import (
    ActionContext,
    CompensationContext,
    InMemoryCheckpointStore,
    WorkflowDefinition,
    WorkflowRunner,
)


async def create_effect(context: ActionContext) -> dict[str, str]:
    return {"effect": context.step.id, "key": context.idempotency_key}


async def fail_delivery(_context: ActionContext) -> None:
    raise RuntimeError("The downstream delivery service is unavailable.")


async def reverse_effect(context: CompensationContext) -> dict[str, str]:
    return {
        "reversed": context.output["effect"],
        "key": context.idempotency_key,
    }


async def main() -> None:
    workflow = WorkflowDefinition.from_dict(
        {
            "version": 3,
            "name": "compensating-order",
            "steps": [
                {
                    "id": "reserve",
                    "action": "effect",
                    "compensation": {"action": "reverse"},
                },
                {
                    "id": "charge",
                    "action": "effect",
                    "dependencies": ["reserve"],
                    "compensation": {"action": "reverse", "retries": 2},
                },
                {"id": "deliver", "action": "fail", "dependencies": ["charge"]},
            ],
        }
    )
    result = await WorkflowRunner(
        {"effect": create_effect, "fail": fail_delivery},
        compensations={"reverse": reverse_effect},
    ).run(
        workflow,
        {"order_id": 42},
        run_id="order-42",
        checkpoint_store=InMemoryCheckpointStore(),
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
