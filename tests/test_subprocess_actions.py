# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from samsarix_orchestration import (
    ActionContext,
    CompensationPolicy,
    InMemoryCheckpointStore,
    StepState,
    SubprocessActionError,
    WorkflowDefinition,
    WorkflowRunner,
    WorkflowStep,
    subprocess_action,
)


def action_context(*, workflow_input: Any = None) -> ActionContext:
    return ActionContext(
        workflow_name="subprocess-test",
        step=WorkflowStep(
            id="work",
            action="external",
            agent="worker",
            parameters={"mode": "safe"},
        ),
        workflow_input=workflow_input,
        dependencies={"prepare": {"ready": True}},
        attempt=2,
        run_id="process-run",
        idempotency_key="process-run:work",
    )


def python_action(
    source: str,
    *arguments: str,
    **options: Any,
) -> Any:
    return subprocess_action((sys.executable, "-I", "-c", source, *arguments), **options)


@pytest.mark.asyncio
async def test_json_protocol_round_trip_and_explicit_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAMSARIX_TEST_SECRET", "must-not-inherit")
    handler = python_action(
        "import json,os,sys; value=json.load(sys.stdin); "
        "json.dump({'input':value,'visible':os.getenv('VISIBLE'),"
        "'hidden':os.getenv('SAMSARIX_TEST_SECRET')},sys.stdout)",
        environment={"VISIBLE": "yes"},
    )

    output = await handler(action_context(workflow_input={"value": 7}))

    assert output["visible"] == "yes"
    assert output["hidden"] is None
    envelope = output["input"]
    assert envelope == {
        "schema_version": 1,
        "kind": "action",
        "workflow": "subprocess-test",
        "run_id": "process-run",
        "idempotency_key": "process-run:work",
        "attempt": 2,
        "step": {
            "id": "work",
            "agent": "worker",
            "action": "external",
            "parameters": {"mode": "safe"},
            "compensation_action": None,
        },
        "workflow_input": {"value": 7},
        "dependencies": {"prepare": {"ready": True}},
        "output": None,
    }


@pytest.mark.asyncio
async def test_environment_inheritance_and_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAMSARIX_INHERITED", "parent")
    handler = python_action(
        "import json,os,sys; json.load(sys.stdin); "
        "json.dump(os.getenv('SAMSARIX_INHERITED'),sys.stdout)",
        inherit_environment=True,
        environment={"SAMSARIX_INHERITED": "explicit"},
    )

    assert await handler(action_context()) == "explicit"


@pytest.mark.asyncio
async def test_command_arguments_are_not_interpreted_by_a_shell() -> None:
    value = '$(echo injected); & | "quoted"'
    handler = python_action(
        "import json,sys; json.dump(sys.argv[1],sys.stdout)",
        value,
    )

    assert await handler(action_context()) == value


@pytest.mark.asyncio
async def test_workflow_retries_a_failed_process_with_protocol_attempt() -> None:
    handler = python_action(
        "import json,sys; value=json.load(sys.stdin); "
        "sys.exit(9) if value['attempt']==1 else json.dump(value['attempt'],sys.stdout)"
    )
    workflow = WorkflowDefinition(
        name="process-retry",
        steps=(WorkflowStep(id="work", action="external", retries=1),),
    )

    result = await WorkflowRunner({"external": handler}).run(workflow, run_id="retry-process")

    assert result.succeeded
    assert result.steps[0].attempts == 2
    assert result.steps[0].output == 2


@pytest.mark.asyncio
async def test_nonzero_exit_hides_stderr_unless_explicitly_exposed() -> None:
    source = "import sys; sys.stderr.write('TOKEN=ultra-secret'); sys.exit(23)"
    hidden = await WorkflowRunner({"external": python_action(source)}).run(
        WorkflowDefinition(
            name="hidden-stderr",
            steps=(WorkflowStep(id="work", action="external"),),
        )
    )
    exposed = await WorkflowRunner(
        {"external": python_action(source, expose_stderr=True)}
    ).run(
        WorkflowDefinition(
            name="exposed-stderr",
            steps=(WorkflowStep(id="work", action="external"),),
        )
    )

    assert hidden.steps[0].state is StepState.FAILED
    assert hidden.steps[0].error is not None
    assert hidden.steps[0].error["type"] == "SubprocessActionError"
    assert "code 23" in hidden.steps[0].error["message"]
    assert "ultra-secret" not in hidden.steps[0].error["message"]
    assert exposed.steps[0].error is not None
    assert "ultra-secret" in exposed.steps[0].error["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("pass", "no JSON output"),
        ("import sys; sys.stdout.write('{')", "invalid JSON"),
        ("import sys; sys.stdout.write('NaN')", "invalid JSON"),
        ("import sys; sys.stdout.buffer.write(bytes([255]))", "UTF-8 JSON"),
    ],
)
async def test_invalid_child_output_fails_closed(source: str, message: str) -> None:
    with pytest.raises(SubprocessActionError, match=message):
        await python_action(source)(action_context())


@pytest.mark.asyncio
async def test_input_stdout_and_stderr_are_bounded() -> None:
    with pytest.raises(SubprocessActionError, match="input.*limit"):
        await subprocess_action(
            (sys.executable, "-c", "raise AssertionError('must not start')"),
            max_input_bytes=10,
        )(action_context(workflow_input="large"))

    with pytest.raises(SubprocessActionError, match="standard output.*limit"):
        await python_action(
            "import sys; sys.stdout.write('x'*100)",
            max_stdout_bytes=16,
        )(action_context())

    with pytest.raises(SubprocessActionError, match="standard error.*limit"):
        await python_action(
            "import json,sys; sys.stderr.write('x'*100); json.dump('ok',sys.stdout)",
            max_stderr_bytes=16,
        )(action_context())


@pytest.mark.asyncio
async def test_workflow_timeout_terminates_child_before_it_can_continue(tmp_path: Path) -> None:
    marker = tmp_path / "escaped.txt"
    handler = python_action(
        "import json,pathlib,signal,sys,time; json.load(sys.stdin); "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(0.8); "
        "pathlib.Path(sys.argv[1]).write_text('escaped'); json.dump('late',sys.stdout)",
        str(marker),
        terminate_grace_seconds=0.05,
    )
    workflow = WorkflowDefinition(
        name="terminating-timeout",
        steps=(WorkflowStep(id="work", action="external", timeout_seconds=0.2),),
    )

    result = await WorkflowRunner({"external": handler}).run(workflow)
    await asyncio.sleep(0.9)

    assert result.steps[0].state is StepState.FAILED
    assert result.steps[0].error is not None
    assert result.steps[0].error["type"] == "TimeoutError"
    assert not marker.exists()


@pytest.mark.asyncio
async def test_external_cancellation_terminates_child_before_propagating(
    tmp_path: Path,
) -> None:
    started = tmp_path / "started.txt"
    marker = tmp_path / "escaped.txt"
    handler = python_action(
        "import json,pathlib,signal,sys,time; json.load(sys.stdin); "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).write_text('started'); time.sleep(0.8); "
        "pathlib.Path(sys.argv[2]).write_text('escaped'); json.dump('late',sys.stdout)",
        str(started),
        str(marker),
        terminate_grace_seconds=0.05,
    )
    workflow = WorkflowDefinition(
        name="cancel-subprocess",
        steps=(WorkflowStep(id="work", action="external"),),
    )
    run_task = asyncio.create_task(WorkflowRunner({"external": handler}).run(workflow))

    for _ in range(500):
        if started.exists():
            break
        await asyncio.sleep(0.01)
    if not started.exists():
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
    assert started.exists()
    run_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await run_task
    await asyncio.sleep(0.9)

    assert not marker.exists()


@pytest.mark.asyncio
async def test_timeout_retry_starts_only_after_previous_child_is_dead(tmp_path: Path) -> None:
    marker = tmp_path / "overlap.txt"
    handler = python_action(
        "import json,pathlib,signal,sys,time; value=json.load(sys.stdin); "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "(time.sleep(1.2),pathlib.Path(sys.argv[1]).write_text('overlap')) "
        "if value['attempt']==1 else json.dump('recovered',sys.stdout)",
        str(marker),
        terminate_grace_seconds=0.05,
    )
    workflow = WorkflowDefinition(
        name="process-timeout-retry",
        steps=(
            WorkflowStep(
                id="work",
                action="external",
                timeout_seconds=0.7,
                retries=1,
            ),
        ),
    )

    result = await WorkflowRunner({"external": handler}).run(workflow)
    await asyncio.sleep(1.3)

    assert result.succeeded
    assert result.steps[0].attempts == 2
    assert result.steps[0].output == "recovered"
    assert not marker.exists()


@pytest.mark.asyncio
async def test_subprocess_handler_can_compensate_with_original_output() -> None:
    store = InMemoryCheckpointStore()
    forward = python_action(
        "import json,sys; value=json.load(sys.stdin); "
        "json.dump({'created':value['step']['id']},sys.stdout)"
    )
    compensate = python_action(
        "import json,sys; value=json.load(sys.stdin); "
        "json.dump({'kind':value['kind'],'output':value['output'],"
        "'key':value['idempotency_key']},sys.stdout)"
    )

    async def fail(_context: ActionContext) -> None:
        raise RuntimeError("force rollback")

    workflow = WorkflowDefinition(
        version=3,
        name="process-saga",
        steps=(
            WorkflowStep(
                id="create",
                action="create",
                compensation=CompensationPolicy(action="remove"),
            ),
            WorkflowStep(id="fail", action="fail", dependencies=("create",)),
        ),
    )
    result = await WorkflowRunner(
        {"create": forward, "fail": fail},
        compensations={"remove": compensate},
    ).run(workflow, run_id="process-saga", checkpoint_store=store)

    assert result.compensation_status == "succeeded"
    assert result.compensations[0].output == {
        "kind": "compensation",
        "output": {"created": "create"},
        "key": "process-saga:create:compensate",
    }


@pytest.mark.asyncio
async def test_configured_working_directory_is_used(tmp_path: Path) -> None:
    handler = python_action(
        "import json,os,sys; json.load(sys.stdin); json.dump(os.getcwd(),sys.stdout)",
        cwd=tmp_path,
    )

    assert Path(await handler(action_context())).resolve() == tmp_path.resolve()


@pytest.mark.asyncio
async def test_spawn_failure_and_non_finite_input_are_bounded_errors(tmp_path: Path) -> None:
    with pytest.raises(SubprocessActionError, match="Cannot start"):
        await subprocess_action((str((tmp_path / "missing-executable").resolve()),))(
            action_context()
        )
    with pytest.raises(SubprocessActionError, match="finite JSON"):
        await python_action("pass")(action_context(workflow_input=float("nan")))


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("echo value",), "not a shell command"),
        ((None,), "iterable"),
        (((),), "between 1"),
        ((("",),), "non-empty strings"),
        ((("relative-executable",),), "absolute path"),
        ((("ok",),), "integer from 1"),
    ],
)
def test_invalid_configuration_is_rejected(
    arguments: tuple[Any, ...],
    message: str,
) -> None:
    if arguments == (("ok",),):
        with pytest.raises(ValueError, match=message):
            subprocess_action((sys.executable,), max_stdout_bytes=0)
        return
    with pytest.raises(ValueError, match=message):
        subprocess_action(*arguments)


@pytest.mark.parametrize(
    "options",
    [
        {"environment": {"BAD=NAME": "value"}},
        {"environment": {"NAME": "bad\0value"}},
        {"inherit_environment": 1},
        {"expose_stderr": 1},
        {"terminate_grace_seconds": -1},
        {"cwd": b"not-text"},
    ],
)
def test_invalid_environment_and_lifecycle_options_are_rejected(
    options: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        subprocess_action((sys.executable,), **options)
