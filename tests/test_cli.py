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
