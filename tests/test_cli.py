# Copyright (c) 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from samsarix_orchestration.cli import MAX_INPUT_BYTES, build_parser, legacy_main, main


def test_complete_cli_journey(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workflow = tmp_path / "workflow.json"
    report = tmp_path / "run.json"

    assert main(["init", str(workflow)]) == 0
    assert workflow.exists()
    capsys.readouterr()

    assert main(["validate", str(workflow), "--json"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation == {
        "max_concurrency": 2,
        "name": "hello-samsarix",
        "steps": 3,
        "valid": True,
    }

    assert main(["run", str(workflow), "--output", str(report)]) == 0
    run = json.loads(capsys.readouterr().out)
    assert run["status"] == "succeeded"
    assert run["steps"][-1]["output"] == {"characters": 19, "words": 3}
    assert json.loads(report.read_text(encoding="utf-8")) == run


def test_init_and_output_refuse_implicit_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text("keep", encoding="utf-8")
    assert main(["init", str(workflow)]) == 2
    assert workflow.read_text(encoding="utf-8") == "keep"
    assert "Refusing" in capsys.readouterr().err

    assert main(["init", str(workflow), "--force"]) == 0
    capsys.readouterr()
    output = tmp_path / "run.json"
    output.write_text("keep", encoding="utf-8")
    assert main(["run", str(workflow), "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "keep"
    capsys.readouterr()
    assert (
        main(
            [
                "run",
                str(workflow),
                "--output",
                str(output),
                "--force-output",
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "succeeded"


def test_init_can_generate_a_valid_approval_workflow(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "approval.json"
    assert main(["init", str(workflow), "--approval"]) == 0
    capsys.readouterr()
    value = json.loads(workflow.read_text(encoding="utf-8"))
    assert value["version"] == 2
    assert value["steps"][1]["approval"]["prompt"]
    assert main(["validate", str(workflow), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_cli_reports_validation_and_execution_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"name": "", "steps": []}', encoding="utf-8")
    assert main(["validate", str(invalid)]) == 2
    error = capsys.readouterr().err
    assert "$.name" in error
    assert "$.steps" in error

    unknown = tmp_path / "unknown.json"
    unknown.write_text(
        json.dumps(
            {
                "name": "unknown-action",
                "steps": [{"id": "x", "action": "not-registered"}],
            }
        ),
        encoding="utf-8",
    )
    assert main(["run", str(unknown)]) == 1
    assert "No handler registered" in capsys.readouterr().err


def test_cli_input_modes_and_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "input.json"
    workflow.write_text(
        json.dumps(
            {
                "name": "input",
                "steps": [{"id": "x", "action": "uppercase"}],
            }
        ),
        encoding="utf-8",
    )
    assert main(["run", str(workflow), "--input", '{"text":"hello"}']) == 0
    assert json.loads(capsys.readouterr().out)["steps"][0]["output"] == "HELLO"

    input_file = tmp_path / "payload.json"
    input_file.write_text('{"text":"from file"}', encoding="utf-8")
    assert main(["run", str(workflow), "--input-file", str(input_file)]) == 0
    assert json.loads(capsys.readouterr().out)["steps"][0]["output"] == "FROM FILE"

    assert main(["run", str(workflow), "--input", "{"]) == 2
    assert "Invalid input JSON" in capsys.readouterr().err

    large = tmp_path / "large.json"
    large.write_text("x" * (MAX_INPUT_BYTES + 1), encoding="utf-8")
    assert main(["run", str(workflow), "--input-file", str(large)]) == 2
    assert "limit" in capsys.readouterr().err


def test_actions_parser_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["actions"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "collect",
        "echo",
        "uppercase",
        "word_count",
    ]

    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(["--version"])
    assert raised.value.code == 0
    assert "0.1.0" in capsys.readouterr().out

    with pytest.raises(SystemExit) as legacy:
        build_parser(prog="helix-orchestration").parse_args(["--version"])
    assert legacy.value.code == 0
    assert "helix-orchestration 0.1.0" in capsys.readouterr().out

    assert legacy_main(["actions"]) == 0
    assert "word_count" in capsys.readouterr().out


def test_cli_checkpoint_resume_journey(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "workflow.json"
    checkpoints = tmp_path / "checkpoints"
    assert main(["init", str(workflow)]) == 0
    capsys.readouterr()

    common = [
        "run",
        str(workflow),
        "--checkpoint-dir",
        str(checkpoints),
        "--run-id",
        "demo-run",
    ]
    assert main(common) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["run_id"] == "demo-run"
    assert first["resumed"] is False
    assert first["restored_steps"] == 0

    assert main(common) == 1
    assert "already exists" in capsys.readouterr().err

    assert main([*common, "--resume"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["resumed"] is True
    assert resumed["restored_steps"] == 3

    assert main(["run", str(workflow), "--resume"]) == 2
    assert "--checkpoint-dir" in capsys.readouterr().err


def test_cli_sqlite_run_inspection_resume_and_delete(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "workflow.json"
    database = tmp_path / "runs.db"
    assert main(["init", str(workflow)]) == 0
    capsys.readouterr()

    common = [
        "run",
        str(workflow),
        "--checkpoint-db",
        str(database),
        "--run-id",
        "sqlite-run",
        "--input",
        '{"secret":"PRIVATE"}',
    ]
    assert main(common) == 0
    capsys.readouterr()

    assert main(["runs", "list", str(database), "--json"]) == 0
    summaries = json.loads(capsys.readouterr().out)
    assert summaries[0]["run_id"] == "sqlite-run"
    assert "PRIVATE" not in json.dumps(summaries)

    assert main(["runs", "show", str(database), "sqlite-run"]) == 0
    safe = json.loads(capsys.readouterr().out)
    assert safe["successful_steps"] == 3
    assert all("output" not in step for step in safe["steps"])

    assert (
        main(
            [
                "runs",
                "show",
                str(database),
                "sqlite-run",
                "--include-outputs",
            ]
        )
        == 0
    )
    complete = json.loads(capsys.readouterr().out)
    assert "output" in complete["steps"][0]

    assert main([*common, "--resume"]) == 0
    assert json.loads(capsys.readouterr().out)["restored_steps"] == 3

    assert (
        main(
            [
                "runs",
                "delete",
                str(database),
                "sqlite-run",
                "--confirm",
                "wrong",
            ]
        )
        == 2
    )
    assert "exactly match" in capsys.readouterr().err
    assert (
        main(
            [
                "runs",
                "delete",
                str(database),
                "sqlite-run",
                "--confirm",
                "sqlite-run",
            ]
        )
        == 0
    )
    assert "Deleted" in capsys.readouterr().out


def test_cli_sqlite_errors_and_storage_exclusion(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "workflow.json"
    assert main(["init", str(workflow)]) == 0
    capsys.readouterr()

    with pytest.raises(SystemExit) as mutually_exclusive:
        main(
            [
                "run",
                str(workflow),
                "--checkpoint-dir",
                str(tmp_path / "dir"),
                "--checkpoint-db",
                str(tmp_path / "db"),
            ]
        )
    assert mutually_exclusive.value.code == 2
    capsys.readouterr()

    assert main(["runs", "list", str(tmp_path / "missing.db")]) == 1
    assert "does not exist" in capsys.readouterr().err

    assert main(["runs", "list", ":memory:"]) == 2
    assert "filesystem path" in capsys.readouterr().err

    with pytest.raises(SystemExit) as invalid_run_id:
        main(["runs", "show", str(tmp_path / "missing.db"), "../escape"])
    assert invalid_run_id.value.code == 2


def test_cli_streams_privacy_minimized_json_events(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "workflow.json"
    assert main(["init", str(workflow)]) == 0
    capsys.readouterr()

    assert main(["run", str(workflow), "--events", "--input", '{"secret":"hidden"}']) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    events = [json.loads(line) for line in captured.err.splitlines()]

    assert report["status"] == "succeeded"
    assert events[0]["kind"] == "run_started"
    assert events[-1]["kind"] == "run_succeeded"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert "hidden" not in captured.err


def test_cli_approval_pause_approve_and_reject_journeys(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "approval.json"
    workflow.write_text(
        json.dumps(
            {
                "version": 2,
                "name": "approval-cli",
                "steps": [
                    {
                        "id": "publish",
                        "action": "echo",
                        "parameters": {"value": "prepared"},
                        "approval": {"prompt": "Publish this result?"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    database = tmp_path / "approvals.db"
    common = [
        "run",
        str(workflow),
        "--checkpoint-db",
        str(database),
        "--run-id",
        "approval-cli-run",
        "--events",
    ]

    assert main(common) == 3
    captured = capsys.readouterr()
    paused = json.loads(captured.out)
    request_id = paused["approvals"][0]["request_id"]
    assert paused["status"] == "paused"
    assert paused["steps"] == []
    events = [json.loads(line) for line in captured.err.splitlines()]
    assert events[-1]["kind"] == "run_paused"
    assert all(event["schema_version"] == 2 for event in events)
    assert "Publish this result?" not in captured.err

    assert (
        main(
            [
                *common,
                "--resume",
                "--approve",
                request_id,
                "--decided-by",
                "release-manager",
                "--decision-reason",
                "Reviewed prepared output.",
            ]
        )
        == 0
    )
    approved = json.loads(capsys.readouterr().out)
    assert approved["status"] == "succeeded"
    assert approved["approvals"][0]["status"] == "approved"
    assert approved["approvals"][0]["decided_by"] == "release-manager"
    assert approved["steps"][0]["output"] == "prepared"

    reject_common = [
        "run",
        str(workflow),
        "--checkpoint-db",
        str(database),
        "--run-id",
        "rejected-cli-run",
    ]
    assert main(reject_common) == 3
    rejected_request = json.loads(capsys.readouterr().out)["approvals"][0]["request_id"]
    assert main([*reject_common, "--resume", "--reject", rejected_request]) == 1
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["status"] == "rejected"
    assert rejected["steps"][0]["state"] == "rejected"


def test_cli_approval_decision_usage_is_validated(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "workflow.json"
    assert main(["init", str(workflow)]) == 0
    capsys.readouterr()
    request_id = "a" * 64
    with pytest.raises(SystemExit) as invalid_id:
        main(["run", str(workflow), "--approve", "bad"])
    assert invalid_id.value.code == 2
    capsys.readouterr()

    assert main(["run", str(workflow), "--approve", request_id]) == 2
    assert "require --resume" in capsys.readouterr().err
