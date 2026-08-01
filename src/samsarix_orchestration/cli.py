# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Command-line interface for Samsarix Orchestration."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .actions import builtin_actions
from .checkpoints import JsonDirectoryCheckpointStore
from .events import WorkflowEvent
from .runtime import (
    MAX_APPROVAL_ACTOR_CHARACTERS,
    MAX_APPROVAL_REASON_CHARACTERS,
    ApprovalDecision,
    ApprovalDecisionKind,
    CheckpointStore,
    WorkflowCheckpoint,
    WorkflowExecutionError,
    WorkflowRunner,
)
from .spec import WorkflowSpecError, load_workflow
from .sqlite_store import MAX_LIST_LIMIT, SqliteCheckpointStore

MAX_INPUT_BYTES = 1_048_576
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
EXAMPLE_WORKFLOW: dict[str, Any] = {
    "version": 1,
    "name": "hello-samsarix",
    "description": "A deterministic provider-free workflow.",
    "max_concurrency": 2,
    "steps": [
        {
            "id": "message",
            "agent": "writer",
            "action": "echo",
            "parameters": {"value": "hello from samsarix"},
        },
        {
            "id": "uppercase",
            "agent": "editor",
            "action": "uppercase",
            "dependencies": ["message"],
        },
        {
            "id": "count",
            "agent": "analyst",
            "action": "word_count",
            "dependencies": ["uppercase"],
        },
    ],
}
APPROVAL_EXAMPLE_WORKFLOW: dict[str, Any] = {
    "version": 2,
    "name": "production-release-approval",
    "description": "Prepare a release plan, then pause before publishing it.",
    "max_concurrency": 2,
    "steps": [
        {
            "id": "prepare",
            "agent": "release",
            "action": "echo",
            "parameters": {
                "value": {
                    "artifact": "samsarix-orchestration-0.1.0",
                    "target": "production",
                }
            },
        },
        {
            "id": "publish",
            "agent": "release",
            "action": "collect",
            "dependencies": ["prepare"],
            "approval": {"prompt": "Publish this release plan to production?"},
        },
    ],
}


def build_parser(*, prog: str = "samsarix-orchestration") -> argparse.ArgumentParser:
    """Create the CLI parser without reading process-global state."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Validate and run bounded, provider-neutral workflows using registered Python actions."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Write a runnable example workflow.")
    init_parser.add_argument("path", type=Path)
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Explicitly replace an existing file.",
    )
    init_parser.add_argument(
        "--approval",
        action="store_true",
        help="Generate a schema-v2 workflow with a pre-action approval gate.",
    )

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a workflow without executing it."
    )
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument("--json", action="store_true", dest="as_json")

    run_parser = subparsers.add_parser("run", help="Run a workflow with built-in actions.")
    run_parser.add_argument("path", type=Path)
    input_group = run_parser.add_mutually_exclusive_group()
    input_group.add_argument("--input", help="Inline JSON input (maximum 1 MiB).")
    input_group.add_argument("--input-file", type=Path, help="UTF-8 JSON input file.")
    run_parser.add_argument("--output", type=Path, help="Also write the JSON run report.")
    run_parser.add_argument(
        "--force-output",
        action="store_true",
        help="Explicitly replace an existing output file.",
    )
    checkpoint_group = run_parser.add_mutually_exclusive_group()
    checkpoint_group.add_argument(
        "--checkpoint-dir",
        type=Path,
        help="Save one JSON file per resumable run.",
    )
    checkpoint_group.add_argument(
        "--checkpoint-db",
        type=Path,
        help="Transactionally save resumable runs in a same-host SQLite database.",
    )
    run_parser.add_argument(
        "--run-id",
        type=_run_id,
        help="Stable run identifier used for checkpoints and idempotency keys.",
    )
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a matching checkpoint; requires checkpoint storage and --run-id.",
    )
    run_parser.add_argument(
        "--events",
        action="store_true",
        help="Stream privacy-minimized lifecycle events as JSON Lines to stderr.",
    )
    run_parser.add_argument(
        "--approve",
        action="append",
        default=[],
        metavar="REQUEST_ID",
        type=_approval_id,
        help="Approve a pending request while resuming; may be repeated.",
    )
    run_parser.add_argument(
        "--reject",
        action="append",
        default=[],
        metavar="REQUEST_ID",
        type=_approval_id,
        help="Reject a pending request while resuming; may be repeated.",
    )
    run_parser.add_argument(
        "--decided-by",
        type=_decision_actor,
        help="Optional unauthenticated reviewer label recorded on every supplied decision.",
    )
    run_parser.add_argument(
        "--decision-reason",
        type=_decision_reason,
        help="Optional reason recorded on every supplied decision.",
    )

    subparsers.add_parser("actions", help="List the safe built-in CLI actions.")

    runs_parser = subparsers.add_parser("runs", help="Inspect or delete SQLite checkpoint runs.")
    runs_subparsers = runs_parser.add_subparsers(dest="runs_command", required=True)
    list_parser = runs_subparsers.add_parser("list", help="List payload-free run metadata.")
    list_parser.add_argument("database", type=Path)
    list_parser.add_argument("--limit", type=_list_limit, default=50)
    list_parser.add_argument("--json", action="store_true", dest="as_json")

    show_parser = runs_subparsers.add_parser("show", help="Show one checkpoint.")
    show_parser.add_argument("database", type=Path)
    show_parser.add_argument("run_id", type=_run_id)
    show_parser.add_argument(
        "--include-outputs",
        action="store_true",
        help="Explicitly include stored step outputs, which may contain sensitive data.",
    )

    delete_parser = runs_subparsers.add_parser("delete", help="Delete one checkpoint.")
    delete_parser.add_argument("database", type=Path)
    delete_parser.add_argument("run_id", type=_run_id)
    delete_parser.add_argument(
        "--confirm",
        required=True,
        metavar="RUN_ID",
        help="Required exact run ID confirmation.",
    )
    return parser


def main(argv: list[str] | None = None, *, prog: str = "samsarix-orchestration") -> int:
    """Run the CLI and return a stable process exit code."""
    parser = build_parser(prog=prog)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            _write_json(
                args.path,
                APPROVAL_EXAMPLE_WORKFLOW if args.approval else EXAMPLE_WORKFLOW,
                overwrite=args.force,
            )
            print(f"Created {args.path}")
            print(f"Next: {parser.prog} validate {args.path}")
            return 0
        if args.command == "validate":
            workflow = load_workflow(args.path)
            if args.as_json:
                print(
                    json.dumps(
                        {
                            "valid": True,
                            "name": workflow.name,
                            "steps": len(workflow.steps),
                            "max_concurrency": workflow.max_concurrency,
                        },
                        sort_keys=True,
                    )
                )
            else:
                print(
                    f"Valid workflow: {workflow.name} "
                    f"({len(workflow.steps)} steps, "
                    f"max concurrency {workflow.max_concurrency})"
                )
            return 0
        if args.command == "actions":
            for name in sorted(builtin_actions()):
                print(name)
            return 0
        if args.command == "runs":
            return _manage_runs(args)
        if args.command == "run":
            if args.resume and args.checkpoint_dir is None and args.checkpoint_db is None:
                raise WorkflowSpecError("--resume requires --checkpoint-dir or --checkpoint-db.")
            if args.resume and args.run_id is None:
                raise WorkflowSpecError("--resume requires --run-id.")
            if (args.approve or args.reject) and not args.resume:
                raise WorkflowSpecError("--approve and --reject require --resume.")
            if (args.decided_by is not None or args.decision_reason is not None) and not (
                args.approve or args.reject
            ):
                raise WorkflowSpecError("--decided-by and --decision-reason require a decision.")
            decision_ids = [*args.approve, *args.reject]
            if len(decision_ids) != len(set(decision_ids)):
                raise WorkflowSpecError("Each approval request may be decided only once.")
            approval_decisions = (
                *(
                    ApprovalDecision(
                        request_id,
                        ApprovalDecisionKind.APPROVE,
                        decided_by=args.decided_by,
                        reason=args.decision_reason,
                    )
                    for request_id in args.approve
                ),
                *(
                    ApprovalDecision(
                        request_id,
                        ApprovalDecisionKind.REJECT,
                        decided_by=args.decided_by,
                        reason=args.decision_reason,
                    )
                    for request_id in args.reject
                ),
            )
            workflow = load_workflow(args.path)
            workflow_input = _load_input(args.input, args.input_file)
            checkpoint_store: CheckpointStore | None
            if args.checkpoint_dir is not None:
                checkpoint_store = JsonDirectoryCheckpointStore(args.checkpoint_dir)
            elif args.checkpoint_db is not None:
                checkpoint_store = _sqlite_store(args.checkpoint_db)
            else:
                checkpoint_store = None
            result = asyncio.run(
                WorkflowRunner(
                    builtin_actions(),
                    event_handlers=(_print_event,) if args.events else (),
                ).run(
                    workflow,
                    workflow_input,
                    run_id=args.run_id,
                    checkpoint_store=checkpoint_store,
                    resume=args.resume,
                    approval_decisions=approval_decisions,
                )
            )
            report = result.to_dict()
            rendered = json.dumps(report, indent=2, sort_keys=True)
            if args.output:
                _write_text(
                    args.output,
                    rendered + "\n",
                    overwrite=args.force_output,
                )
            print(rendered)
            if result.status == "paused":
                return 3
            if result.status == "rejected":
                return 4
            return 0 if result.succeeded else 1
    except WorkflowSpecError as exc:
        _print_spec_error(exc)
        return 2
    except WorkflowExecutionError as exc:
        print(f"Execution error: {exc}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Input/output error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    parser.error(f"Unknown command: {args.command}")
    return 2


def legacy_main(argv: list[str] | None = None) -> int:
    """Run the historical command name during the 0.1 compatibility window."""
    return main(argv, prog="helix-orchestration")


def _list_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be an integer") from exc
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise argparse.ArgumentTypeError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
    return limit


def _run_id(value: str) -> str:
    if not _RUN_ID.fullmatch(value):
        raise argparse.ArgumentTypeError("run ID must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    return value


def _approval_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("approval request ID must be 64 lowercase hex characters")
    return value


def _decision_actor(value: str) -> str:
    if len(value) > MAX_APPROVAL_ACTOR_CHARACTERS:
        raise argparse.ArgumentTypeError(
            f"reviewer label must be at most {MAX_APPROVAL_ACTOR_CHARACTERS} characters"
        )
    return value


def _decision_reason(value: str) -> str:
    if len(value) > MAX_APPROVAL_REASON_CHARACTERS:
        raise argparse.ArgumentTypeError(
            f"decision reason must be at most {MAX_APPROVAL_REASON_CHARACTERS} characters"
        )
    return value


def _manage_runs(args: argparse.Namespace) -> int:
    store = _sqlite_store(args.database, create=False)
    if args.runs_command == "list":
        summaries = store.list_summaries(limit=args.limit)
        if args.as_json:
            print(json.dumps([summary.to_dict() for summary in summaries], sort_keys=True))
        elif not summaries:
            print("No checkpoints.")
        else:
            for summary in summaries:
                print(
                    f"{summary.run_id}\t{summary.successful_steps} steps\t"
                    f"{summary.saved_at}\t{summary.checkpoint_bytes} bytes"
                )
        return 0
    if args.runs_command == "show":
        checkpoint = store.load(args.run_id)
        if checkpoint is None:
            raise WorkflowExecutionError(f"Checkpoint run {args.run_id!r} does not exist.")
        value = (
            checkpoint.to_dict() if args.include_outputs else _privacy_safe_checkpoint(checkpoint)
        )
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    if args.runs_command == "delete":
        if args.confirm != args.run_id:
            raise WorkflowSpecError("--confirm must exactly match RUN_ID.")
        if not store.delete(args.run_id):
            raise WorkflowExecutionError(f"Checkpoint run {args.run_id!r} does not exist.")
        print(f"Deleted checkpoint {args.run_id}")
        return 0
    raise WorkflowSpecError(f"Unknown runs command: {args.runs_command}")


def _sqlite_store(database: Path, *, create: bool = True) -> SqliteCheckpointStore:
    try:
        return SqliteCheckpointStore(database, create=create)
    except ValueError as exc:
        raise WorkflowSpecError(str(exc)) from exc


def _privacy_safe_checkpoint(checkpoint: WorkflowCheckpoint) -> dict[str, Any]:
    value: dict[str, Any] = {
        "version": checkpoint.version,
        "run_id": checkpoint.run_id,
        "workflow_digest": checkpoint.workflow_digest,
        "input_digest": checkpoint.input_digest,
        "saved_at": checkpoint.saved_at,
        "successful_steps": len(checkpoint.steps),
        "steps": [
            {
                "step_id": step.step_id,
                "agent": step.agent,
                "action": step.action,
                "state": step.state.value,
                "attempts": step.attempts,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
                "duration_ms": step.duration_ms,
            }
            for step in checkpoint.steps
        ],
    }
    if checkpoint.version >= 2:
        value["approvals"] = [
            {
                "request_id": approval.request_id,
                "step_id": approval.step_id,
                "prompt": approval.prompt,
                "context_digest": approval.context_digest,
                "requested_at": approval.requested_at,
                "status": approval.status.value,
                "decided_at": approval.decided_at,
            }
            for approval in checkpoint.approvals
        ]
    return value


def _load_input(inline: str | None, input_file: Path | None) -> Any:
    if inline is not None:
        encoded = inline.encode("utf-8")
        if len(encoded) > MAX_INPUT_BYTES:
            raise WorkflowSpecError(f"Inline input exceeds the {MAX_INPUT_BYTES}-byte limit.")
        try:
            return json.loads(inline)
        except json.JSONDecodeError as exc:
            raise WorkflowSpecError(
                f"Invalid input JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
    if input_file is None:
        return None
    try:
        size = input_file.stat().st_size
    except OSError as exc:
        raise WorkflowSpecError(f"Cannot read input file {input_file}: {exc}") from exc
    if not input_file.is_file():
        raise WorkflowSpecError(f"Input path is not a regular file: {input_file}")
    if size > MAX_INPUT_BYTES:
        raise WorkflowSpecError(f"Input is {size} bytes; the limit is {MAX_INPUT_BYTES} bytes.")
    try:
        return json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowSpecError(
            f"Invalid input JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def _print_spec_error(exc: WorkflowSpecError) -> None:
    print(f"Validation error: {exc}", file=sys.stderr)
    for issue in exc.issues:
        print(f"  {issue.path}: {issue.message} [{issue.code}]", file=sys.stderr)


def _print_event(event: WorkflowEvent) -> None:
    print(json.dumps(event.to_dict(), separators=(",", ":")), file=sys.stderr, flush=True)


def _write_json(path: Path, value: Any, *, overwrite: bool) -> None:
    _write_text(
        path,
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        overwrite=overwrite,
    )


def _write_text(path: Path, content: str, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise WorkflowSpecError(
            f"Refusing to replace existing file {path}; use the explicit force option."
        )
    if not overwrite:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        return

    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
