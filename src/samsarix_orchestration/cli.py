# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Command-line interface for Samsarix Orchestration."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import __version__
from .actions import builtin_actions
from .checkpoints import JsonDirectoryCheckpointStore
from .runtime import WorkflowExecutionError, WorkflowRunner
from .spec import WorkflowSpecError, load_workflow

MAX_INPUT_BYTES = 1_048_576
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
    run_parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        help="Atomically save successful steps for a resumable run.",
    )
    run_parser.add_argument(
        "--run-id",
        help="Stable run identifier used for checkpoints and idempotency keys.",
    )
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a matching checkpoint; requires --checkpoint-dir and --run-id.",
    )

    subparsers.add_parser("actions", help="List the safe built-in CLI actions.")
    return parser


def main(argv: list[str] | None = None, *, prog: str = "samsarix-orchestration") -> int:
    """Run the CLI and return a stable process exit code."""
    parser = build_parser(prog=prog)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            _write_json(args.path, EXAMPLE_WORKFLOW, overwrite=args.force)
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
        if args.command == "run":
            if args.resume and args.checkpoint_dir is None:
                raise WorkflowSpecError("--resume requires --checkpoint-dir.")
            if args.resume and args.run_id is None:
                raise WorkflowSpecError("--resume requires --run-id.")
            workflow = load_workflow(args.path)
            workflow_input = _load_input(args.input, args.input_file)
            checkpoint_store = (
                JsonDirectoryCheckpointStore(args.checkpoint_dir)
                if args.checkpoint_dir is not None
                else None
            )
            result = asyncio.run(
                WorkflowRunner(builtin_actions()).run(
                    workflow,
                    workflow_input,
                    run_id=args.run_id,
                    checkpoint_store=checkpoint_store,
                    resume=args.resume,
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
