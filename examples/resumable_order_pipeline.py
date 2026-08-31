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
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from samsarix_orchestration import (
    ActionContext,
    JsonDirectoryCheckpointStore,
    WorkflowDefinition,
    WorkflowRunner,
)

MAX_RECEIPT_BYTES = 4_096


def _publish_receipt(path: Path, receipt: dict[str, Any]) -> bool:
    """Publish complete content without replacement; return whether it was newly created.

    Requires an application-owned directory and a local filesystem supporting hard links.
    This is an idempotent destination example, not a lock for concurrent checkpoint writers
    or a guarantee of persistence after power loss. An abrupt process exit may leave a
    hidden staging file, but never exposes that partially written file as the receipt.
    """
    expected = (json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(expected) > MAX_RECEIPT_BYTES:
        raise ValueError("receipt exceeds the example's size limit")

    def matches_existing() -> bool:
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(mode):
            raise ValueError("existing receipt must be a regular file, not a symbolic link")
        with path.open("rb") as stream:
            existing = stream.read(MAX_RECEIPT_BYTES + 1)
        # The earlier example used write_text, which emitted CRLF on Windows.
        if existing not in (expected, expected[:-1] + b"\r\n"):
            raise ValueError("existing receipt conflicts with the expected order")
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    if matches_existing():
        return False
    staged: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".receipt-", suffix=".tmp", dir=path.parent, delete=False
        ) as stream:
            staged = Path(stream.name)
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Unlike replace/rename, a hard link must not replace a race winner.
            os.link(staged, path)
        except FileExistsError:
            if not matches_existing():
                raise ValueError(
                    "receipt changed during publication; retry after reconciliation"
                ) from None
            return False
        return True
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


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
        key = hashlib.sha256(context.idempotency_key.encode("utf-8")).hexdigest()
        path = receipt_dir / f"{key}.json"
        created = _publish_receipt(path, receipt)
        if created and args.fail_after_publish:
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
