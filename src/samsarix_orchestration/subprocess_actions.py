# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded JSON-protocol actions executed in application-registered subprocesses."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import ActionContext, CompensationContext

SUBPROCESS_PROTOCOL_VERSION = 1
DEFAULT_MAX_SUBPROCESS_INPUT_BYTES = 1_048_576
DEFAULT_MAX_SUBPROCESS_STDOUT_BYTES = 1_048_576
DEFAULT_MAX_SUBPROCESS_STDERR_BYTES = 16_384
MAX_SUBPROCESS_STREAM_BYTES = 16_777_216
MAX_SUBPROCESS_COMMAND_PARTS = 64
MAX_SUBPROCESS_COMMAND_CHARACTERS = 32_768
MAX_SUBPROCESS_ENVIRONMENT_ENTRIES = 128
MAX_SUBPROCESS_ENVIRONMENT_CHARACTERS = 65_536
SubprocessContext = ActionContext | CompensationContext
SubprocessActionHandler = Callable[[SubprocessContext], Awaitable[Any]]


class SubprocessActionError(RuntimeError):
    """Raised when a subprocess action violates its execution or JSON contract."""


@dataclass(frozen=True, slots=True)
class _SubprocessConfiguration:
    command: tuple[str, ...]
    cwd: str | None
    environment: tuple[tuple[str, str], ...]
    inherit_environment: bool
    max_input_bytes: int
    max_stdout_bytes: int
    max_stderr_bytes: int
    terminate_grace_seconds: float
    expose_stderr: bool


def subprocess_action(
    command: Iterable[str],
    *,
    cwd: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
    inherit_environment: bool = False,
    max_input_bytes: int = DEFAULT_MAX_SUBPROCESS_INPUT_BYTES,
    max_stdout_bytes: int = DEFAULT_MAX_SUBPROCESS_STDOUT_BYTES,
    max_stderr_bytes: int = DEFAULT_MAX_SUBPROCESS_STDERR_BYTES,
    terminate_grace_seconds: float = 1.0,
    expose_stderr: bool = False,
) -> SubprocessActionHandler:
    """Build an async action that exchanges one bounded JSON value with a child process.

    The command is passed directly to the operating system without a shell. The child
    receives one protocol envelope on standard input and must emit exactly one finite JSON
    value on standard output. Cancellation terminates the child before it propagates.
    """
    configuration = _validated_configuration(
        command=command,
        cwd=cwd,
        environment=environment,
        inherit_environment=inherit_environment,
        max_input_bytes=max_input_bytes,
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=max_stderr_bytes,
        terminate_grace_seconds=terminate_grace_seconds,
        expose_stderr=expose_stderr,
    )

    async def run(context: SubprocessContext) -> Any:
        return await _run_subprocess(configuration, context)

    return run


def subprocess_envelope(context: SubprocessContext) -> dict[str, Any]:
    """Return the stable protocol envelope for a handler context."""
    if isinstance(context, CompensationContext):
        kind = "compensation"
        output = context.output
        compensation_action = (
            context.step.compensation.action if context.step.compensation is not None else None
        )
    else:
        kind = "action"
        output = None
        compensation_action = None
    return {
        "schema_version": SUBPROCESS_PROTOCOL_VERSION,
        "kind": kind,
        "workflow": context.workflow_name,
        "run_id": context.run_id,
        "idempotency_key": context.idempotency_key,
        "attempt": context.attempt,
        "step": {
            "id": context.step.id,
            "agent": context.step.agent,
            "action": context.step.action,
            "parameters": context.step.parameters,
            "compensation_action": compensation_action,
        },
        "workflow_input": context.workflow_input,
        "dependencies": dict(context.dependencies),
        "output": output,
    }


def _validated_configuration(
    *,
    command: Iterable[str],
    cwd: str | Path | None,
    environment: Mapping[str, str] | None,
    inherit_environment: bool,
    max_input_bytes: int,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
    terminate_grace_seconds: float,
    expose_stderr: bool,
) -> _SubprocessConfiguration:
    if isinstance(command, (str, bytes)):
        raise ValueError("command must be an iterable of argument strings, not a shell command")
    try:
        parts = tuple(command)
    except TypeError as exc:
        raise ValueError("command must be an iterable of argument strings") from exc
    if not parts or len(parts) > MAX_SUBPROCESS_COMMAND_PARTS:
        raise ValueError(
            f"command must contain between 1 and {MAX_SUBPROCESS_COMMAND_PARTS} arguments"
        )
    if any(not isinstance(part, str) or not part or "\0" in part for part in parts):
        raise ValueError("command arguments must be non-empty strings without null bytes")
    if not Path(parts[0]).is_absolute():
        raise ValueError("command executable must be an absolute path")
    if sum(len(part) for part in parts) > MAX_SUBPROCESS_COMMAND_CHARACTERS:
        raise ValueError(
            f"command may contain at most {MAX_SUBPROCESS_COMMAND_CHARACTERS} characters"
        )
    if not isinstance(inherit_environment, bool):
        raise ValueError("inherit_environment must be a boolean")
    if not isinstance(expose_stderr, bool):
        raise ValueError("expose_stderr must be a boolean")
    for name, value in {
        "max_input_bytes": max_input_bytes,
        "max_stdout_bytes": max_stdout_bytes,
        "max_stderr_bytes": max_stderr_bytes,
    }.items():
        if type(value) is not int or not 1 <= value <= MAX_SUBPROCESS_STREAM_BYTES:
            raise ValueError(
                f"{name} must be an integer from 1 to {MAX_SUBPROCESS_STREAM_BYTES}"
            )
    if (
        isinstance(terminate_grace_seconds, bool)
        or not isinstance(terminate_grace_seconds, (int, float))
        or not 0 <= terminate_grace_seconds <= 30
    ):
        raise ValueError("terminate_grace_seconds must be between 0 and 30")

    normalized_cwd: str | None = None
    if cwd is not None:
        normalized_cwd = os.fspath(cwd)
        if not normalized_cwd or "\0" in normalized_cwd:
            raise ValueError("cwd must be a non-empty filesystem path without null bytes")

    if environment is not None and not isinstance(environment, Mapping):
        raise ValueError("environment must be a string mapping")
    raw_items = tuple((environment or {}).items())
    if len(raw_items) > MAX_SUBPROCESS_ENVIRONMENT_ENTRIES:
        raise ValueError(
            f"environment may contain at most {MAX_SUBPROCESS_ENVIRONMENT_ENTRIES} entries"
        )
    if any(
        not isinstance(key, str)
        or not key
        or "=" in key
        or "\0" in key
        or not isinstance(value, str)
        or "\0" in value
        for key, value in raw_items
    ):
        raise ValueError(
            "environment names and values must be strings; names cannot contain '='; "
            "neither may contain null bytes"
        )
    if (
        sum(len(key) + len(value) for key, value in raw_items)
        > MAX_SUBPROCESS_ENVIRONMENT_CHARACTERS
    ):
        raise ValueError(
            "environment may contain at most "
            f"{MAX_SUBPROCESS_ENVIRONMENT_CHARACTERS} characters"
        )
    normalized_names = tuple(os.path.normcase(key) for key, _value in raw_items)
    if len(normalized_names) != len(set(normalized_names)):
        raise ValueError("environment names must be unique for this operating system")
    items = tuple(sorted(raw_items))
    return _SubprocessConfiguration(
        command=parts,
        cwd=normalized_cwd,
        environment=items,
        inherit_environment=inherit_environment,
        max_input_bytes=max_input_bytes,
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=max_stderr_bytes,
        terminate_grace_seconds=float(terminate_grace_seconds),
        expose_stderr=expose_stderr,
    )


async def _run_subprocess(
    configuration: _SubprocessConfiguration,
    context: SubprocessContext,
) -> Any:
    input_bytes = _encode_input(context, configuration.max_input_bytes)
    child_environment = _child_environment(configuration)
    try:
        process = await asyncio.create_subprocess_exec(
            *configuration.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=configuration.cwd,
            env=child_environment,
            limit=max(configuration.max_stdout_bytes, configuration.max_stderr_bytes) + 1,
        )
    except (OSError, ValueError) as exc:
        raise SubprocessActionError(f"Cannot start subprocess action: {exc}") from exc

    if process.stdin is None or process.stdout is None or process.stderr is None:
        await _terminate_process(process, configuration.terminate_grace_seconds)
        raise SubprocessActionError("Subprocess action could not open its standard streams.")

    stdout_task = asyncio.create_task(
        _read_bounded(process.stdout, configuration.max_stdout_bytes, "standard output")
    )
    stderr_task = asyncio.create_task(
        _read_bounded(process.stderr, configuration.max_stderr_bytes, "standard error")
    )
    wait_task = asyncio.create_task(process.wait())
    tasks = (stdout_task, stderr_task, wait_task)
    try:
        await _write_input(process.stdin, input_bytes)
        stdout, stderr, return_code = await asyncio.gather(*tasks)
    except BaseException:
        await _terminate_process(process, configuration.terminate_grace_seconds)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    if return_code != 0:
        message = f"Subprocess action exited with code {return_code}."
        if configuration.expose_stderr and stderr:
            message += f" stderr={_escaped_text(stderr)}"
        raise SubprocessActionError(message)
    return _decode_output(stdout)


def _encode_input(context: SubprocessContext, maximum: int) -> bytes:
    try:
        encoded = json.dumps(
            subprocess_envelope(context),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SubprocessActionError("Subprocess action input must be finite JSON data.") from exc
    payload = encoded + b"\n"
    if len(payload) > maximum:
        raise SubprocessActionError(
            f"Subprocess action input is {len(payload)} bytes; the limit is {maximum} bytes."
        )
    return payload


async def _write_input(writer: asyncio.StreamWriter, value: bytes) -> None:
    try:
        writer.write(value)
        await writer.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass


async def _read_bounded(
    reader: asyncio.StreamReader,
    maximum: int,
    label: str,
) -> bytes:
    value = bytearray()
    while True:
        chunk = await reader.read(min(65_536, maximum + 1 - len(value)))
        if not chunk:
            return bytes(value)
        value.extend(chunk)
        if len(value) > maximum:
            raise SubprocessActionError(
                f"Subprocess action {label} exceeded its {maximum}-byte limit."
            )


async def _terminate_process(
    process: asyncio.subprocess.Process,
    grace_seconds: float,
) -> None:
    if process.returncode is not None:
        await process.wait()
        return
    try:
        process.terminate()
    except ProcessLookupError:
        await process.wait()
        return
    try:
        await asyncio.wait_for(asyncio.shield(process.wait()), timeout=grace_seconds)
    except TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()


def _decode_output(value: bytes) -> Any:
    if not value.strip():
        raise SubprocessActionError("Subprocess action emitted no JSON output.")
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SubprocessActionError("Subprocess action output must be UTF-8 JSON.") from exc
    try:
        return json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SubprocessActionError("Subprocess action emitted invalid JSON output.") from exc


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"Non-finite JSON constant is not allowed: {value}")


def _escaped_text(value: bytes) -> str:
    text = value.decode("utf-8", errors="replace").strip()
    return json.dumps(text, ensure_ascii=True)


def _child_environment(configuration: _SubprocessConfiguration) -> dict[str, str]:
    environment = dict(os.environ) if configuration.inherit_environment else {}
    for key, value in configuration.environment:
        normalized = os.path.normcase(key)
        for inherited in tuple(environment):
            if os.path.normcase(inherited) == normalized:
                del environment[inherited]
        environment[key] = value
    return environment


__all__ = [
    "DEFAULT_MAX_SUBPROCESS_INPUT_BYTES",
    "DEFAULT_MAX_SUBPROCESS_STDERR_BYTES",
    "DEFAULT_MAX_SUBPROCESS_STDOUT_BYTES",
    "MAX_SUBPROCESS_STREAM_BYTES",
    "SUBPROCESS_PROTOCOL_VERSION",
    "SubprocessActionError",
    "SubprocessActionHandler",
    "subprocess_action",
    "subprocess_envelope",
]
