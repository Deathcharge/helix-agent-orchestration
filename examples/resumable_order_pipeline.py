# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Run a resumable order pipeline with an idempotent file side effect.

First run (intentionally fails after writing the receipt):

    python examples/resumable_order_pipeline.py --fail-after-publish

Resume without repeating completed pricing or duplicating the receipt:

    python examples/resumable_order_pipeline.py --resume
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from samsarix_orchestration import (
    ActionContext,
    JsonDirectoryCheckpointStore,
    WorkflowDefinition,
    WorkflowRunner,
)


def build_workflow() -> WorkflowDefinition:
    """Build a small order workflow with an externally visible final step."""
    return WorkflowDefinition.from_dict(
        {
            "version": 1,
            "name": "resumable-order",
            "steps": [
                {"id": "load", "action": "load"},
                {"id": "price", "action": "price", "dependencies": ["load"]},
                {"id": "publish", "action": "publish", "dependencies": ["price"]},
            ],
        }
    )


async def execute(args: argparse.Namespace) -> int:
    """Execute one attempt and return a process exit code."""
    state_dir: Path = args.state_dir
    receipt_dir = state_dir / "receipts"

    def load(context: ActionContext) -> dict[str, Any]:
        if not isinstance(context.workflow_input, dict):
            raise TypeError("order input must be an object")
        return dict(context.workflow_input)

    def price(context: ActionContext) -> dict[str, Any]:
        order = context.dependencies["load"]
        total_cents = sum(item["quantity"] * item["unit_cents"] for item in order["items"])
        return {"order_id": order["order_id"], "total_cents": total_cents}

    def publish(context: ActionContext) -> dict[str, Any]:
        receipt = dict(context.dependencies["price"])
        receipt_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(context.idempotency_key.encode("utf-8")).hexdigest()
        path = receipt_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        if args.fail_after_publish:
            raise RuntimeError("simulated lost response after the receipt was written")
        return receipt

    runner = WorkflowRunner({"load": load, "price": price, "publish": publish})
    result = await runner.run(
        build_workflow(),
        {
            "order_id": args.run_id,
            "items": [
                {"quantity": 2, "unit_cents": 1_250},
                {"quantity": 1, "unit_cents": 499},
            ],
        },
        run_id=args.run_id,
        checkpoint_store=JsonDirectoryCheckpointStore(state_dir / "checkpoints"),
        resume=args.resume,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.succeeded else 1


def main() -> int:
    """Parse arguments and run the example."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=Path(".samsarix-order-demo"))
    parser.add_argument("--run-id", default="order-42")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-after-publish", action="store_true")
    return asyncio.run(execute(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
