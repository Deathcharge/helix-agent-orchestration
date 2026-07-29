# Samsarix Orchestration

Samsarix Orchestration is a local-first Python library and CLI for defining, validating,
and running small dependency-aware workflows. Application code registers ordinary
sync or async Python callables as actions; Samsarix supplies graph validation, bounded
concurrency, per-step timeouts and retries, failure propagation, and a JSON run report.

It is for Python developers who want a transparent provider-neutral orchestration
primitive before adopting a distributed or hosted workflow system. It does not include
an LLM provider, execute model-generated code, expose a server, or require private
infrastructure.

Status: **0.1 alpha / local release candidate.** The implemented CLI and Python journey
are tested. The distribution has not yet been published to a package index.

## What works

- Versioned JSON workflow definitions with actionable validation errors.
- Directed acyclic dependency graphs with up to 256 steps.
- Explicit sync or async Python action registration.
- Concurrent execution bounded to 1–64 in-flight actions per workflow.
- Per-step timeouts, 0–10 retries, bounded retry delays, and fail-fast behavior.
- JSON-safe inputs, outputs, errors, and terminal step states.
- A provider-free CLI example using four deterministic built-in actions.
- No runtime dependencies, network calls, telemetry, credentials, or hidden persistence.

Durable checkpoints, process isolation, distributed workers, human approval pauses,
provider adapters, and a remote API are deliberately out of scope for 0.1.

## Fastest successful path

Prerequisites: Git and Python 3.11 or newer.

```bash
git clone https://github.com/Deathcharge/samsarix-agent-orchestration.git
cd samsarix-agent-orchestration
python -m venv .venv
python -m pip install .
samsarix-orchestration init workflow.json
samsarix-orchestration validate workflow.json
samsarix-orchestration run workflow.json --output run.json
```

The final command exits with `0` and prints a JSON report whose workflow status is
`succeeded`. It also writes the same report to `run.json`. Existing workflow and
report files are never replaced unless `--force` or `--force-output` is explicit.

You can use `python -m samsarix_orchestration` instead of the installed command.

## CLI

```text
samsarix-orchestration --version
samsarix-orchestration actions
samsarix-orchestration init PATH [--force]
samsarix-orchestration validate PATH [--json]
samsarix-orchestration run PATH [--input JSON | --input-file PATH]
                                 [--output PATH] [--force-output]
```

Exit codes are stable:

- `0`: validation or execution succeeded;
- `1`: workflow execution failed;
- `2`: usage, workflow, input, or output validation failed;
- `130`: the user interrupted execution.

Workflow and input files are limited to 1 MiB. Each step result is also limited to
1 MiB by default. See [the workflow format](docs/WORKFLOW_FORMAT.md) for the complete
schema and [the architecture](docs/ARCHITECTURE.md) for execution semantics.

## Python API

```python
import asyncio

from samsarix_orchestration import ActionContext, WorkflowDefinition, WorkflowRunner


async def fetch(_context: ActionContext) -> dict[str, list[int]]:
    return {"values": [2, 3, 5]}


def total(context: ActionContext) -> int:
    return sum(context.dependencies["fetch"]["values"])


async def main() -> None:
    definition = WorkflowDefinition.from_dict(
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
    result = await WorkflowRunner({"fetch": fetch, "total": total}).run(definition)
    print(result.to_dict())


asyncio.run(main())
```

The same runnable example is in [examples/python_workflow.py](examples/python_workflow.py).
An action receives an `ActionContext` containing the workflow input, its validated step
definition, dependency outputs, workflow name, and current attempt number. Handlers run
with the privileges of the Python process; only register trusted code.

## Development

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy
python -m pytest
python -m bandit -q -r src
python -m build
python -m twine check dist/*
```

The test command enforces at least 85% branch-aware coverage. CI runs linting, strict
typing, tests, package builds, and an installed-wheel smoke test on Python 3.11–3.13.
Python libraries do not normally lock their consumers' dependency graph; this package
has no runtime dependencies, while bounded development ranges live in `pyproject.toml`.

## Distribution

The supported artifact is the `samsarix_orchestration` package built from the
`src` layout and the `samsarix-orchestration` console script:

```bash
python -m build
python -m pip install --force-reinstall --no-deps dist/samsarix_orchestration-0.1.0-py3-none-any.whl
samsarix-orchestration --version
```

The `helix_orchestration` import, `python -m helix_orchestration`, and
`helix-orchestration` command are compatibility aliases during the `0.1.x` series.
They delegate to the Samsarix implementation and do not maintain a second runtime. See
[the migration guide](docs/MIGRATION.md). Unsupported historical research modules were
removed from the active tree and remain recoverable from Git revision `6e10c5b`.

## Security, privacy, and cost

The supported runtime performs no network requests, reads no environment variables,
loads no dynamic modules from workflow data, and executes no workflow strings as code.
Workflow JSON selects only action names that the host application explicitly registered.
Concurrency, step count, timeouts, retries, input size, and output size are bounded.
Cancellation propagates to running async actions.

Action handlers are trusted application code and have the full privileges of the Python
process. Samsarix Orchestration is not a sandbox. A handler that calls a model or external
API owns its authentication, destination validation, timeout, cancellation, privacy,
and cost controls. The built-in CLI path has no API or operating cost beyond local
compute and disk space for an explicitly requested report.

No telemetry is collected. Run inputs and outputs stay in memory unless `--output` is
provided; the caller controls report retention and file permissions.

## Project and license status

Copyright 2026 Samsarix LLC and contributors. Source code is licensed under the
[Mozilla Public License 2.0](LICENSE). MPL-2.0 permits commercial use and combination
with proprietary applications while requiring distributed modifications to covered
source files to remain available under MPL-2.0.

See [LICENSING.md](LICENSING.md) for the model and historical-license note,
[TRADEMARKS.md](TRADEMARKS.md) for brand use, and
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution terms.

- General and licensing questions: contact@samsarix.com
- Product support and private security reports: support@samsarix.com
