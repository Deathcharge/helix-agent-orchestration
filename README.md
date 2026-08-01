# Samsarix Orchestration

Samsarix Orchestration is a local-first Python library and CLI for defining, validating,
planning, and running small dependency-aware workflows. Application code registers ordinary
sync or async Python callables as actions; Samsarix supplies graph validation, bounded
concurrency, per-step timeouts and retries, failure propagation, and a JSON run report.
Schema-v3 workflows can also reverse completed external effects with durable compensating
actions after a later failure or approval rejection. Trusted local tools can run through
a bounded subprocess JSON protocol when thread cancellation is not strong enough.

It is for Python developers who want a transparent provider-neutral orchestration
primitive before adopting a distributed or hosted workflow system. It does not include
an LLM provider, execute model-generated code, expose a server, or require private
infrastructure.

Status: **0.1 alpha / local release candidate.** The implemented CLI and Python journey
are tested, including from an exact-pin external package consumer. The distribution has
not yet been published to a package index.

## What works

- Versioned JSON workflow definitions with actionable validation errors.
- Directed acyclic dependency graphs with up to 256 steps.
- Explicit sync or async Python action registration.
- Concurrent execution bounded to 1–64 in-flight actions per workflow.
- Per-step timeouts, 0–10 retries, bounded retry delays, and fail-fast behavior.
- Opt-in atomic JSON or transactional SQLite checkpoints that resume without repeating
  verified successful steps.
- Stable per-step idempotency keys for safely designed external side effects.
- Ordered, schema-versioned lifecycle events for application-owned logs and metrics.
- Schema-v2 pre-action approval gates with durable approve/reject decisions and a strict
  no-handler-before-approval barrier.
- Schema-v3 orchestrated Saga compensation with reverse dependency ordering, independent
  retry policies, interruption-safe checkpoints, and stable compensation idempotency keys.
- Side-effect-free dependency plans and offline Mermaid graph export for preflight review.
- Shell-free subprocess actions with absolute executables, bounded JSON input/output,
  explicit environment inheritance, and terminate-then-kill cancellation.
- A separately installed consumer proving resume, idempotency, and event contracts across
  a real package boundary.
- JSON-safe inputs, outputs, errors, and terminal step states.
- Provider-free CLI examples for successful, approval-gated, and compensating workflows.
- No runtime dependencies, network calls, telemetry, credentials, or implicit persistence.

Distributed workers, sandboxing, dynamic mid-handler interrupts, provider adapters, and a
remote API are deliberately out of scope for 0.1. Subprocess actions isolate lifecycle and
memory, but remain trusted local programs with the invoking user's operating-system access.

## Fastest successful path

Prerequisites: Git and Python 3.11 or newer.

```bash
git clone https://github.com/Deathcharge/samsarix-agent-orchestration.git
cd samsarix-agent-orchestration
python -m venv .venv
python -m pip install .
samsarix-orchestration init workflow.json
samsarix-orchestration validate workflow.json
samsarix-orchestration plan workflow.json
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
samsarix-orchestration init PATH [--force] [--approval | --saga]
samsarix-orchestration validate PATH [--json]
samsarix-orchestration plan PATH [--format text|json|mermaid]
samsarix-orchestration run PATH [--input JSON | --input-file PATH]
                                 [--output PATH] [--force-output]
                                 [--checkpoint-dir PATH | --checkpoint-db PATH]
                                 [--run-id ID] [--resume]
                                 [--approve REQUEST_ID] [--reject REQUEST_ID]
                                 [--decided-by LABEL] [--decision-reason TEXT]
                                 [--events]
samsarix-orchestration runs list DATABASE [--limit N] [--json]
samsarix-orchestration runs show DATABASE RUN_ID [--include-outputs]
samsarix-orchestration runs delete DATABASE RUN_ID --confirm RUN_ID
```

Exit codes are stable:

- `0`: validation or execution succeeded;
- `1`: workflow execution failed;
- `2`: usage, workflow, input, or output validation failed;
- `3`: execution paused before a gated action and awaits an approval decision;
- `4`: an operator rejected an approval request;
- `130`: the user interrupted execution.

Workflow and input files are limited to 1 MiB. Each step result is also limited to
1 MiB by default. See [the workflow format](docs/WORKFLOW_FORMAT.md) for the complete
schema and [the architecture](docs/ARCHITECTURE.md) for execution semantics.

## Inspect before execution

Build a static plan without loading handlers, running actions, reading workflow input, or
making a network request:

```bash
samsarix-orchestration plan workflow.json
samsarix-orchestration plan workflow.json --format json
samsarix-orchestration plan workflow.json --format mermaid > workflow.mmd
```

The plan preserves workflow order for its step inventory while deriving deterministic
dependency waves, roots, leaves, dependants, the longest dependency chain, maximum wave
width, retry-attempt ceilings, the canonical workflow digest, approval-barrier locations,
and compensating-action inventory. A wave marked as an
approval barrier reflects the runtime's global rule: none of that dependency-ready group
starts while a request remains pending. Mermaid output uses internal node IDs and omits
approval prompts; it is source text only, so rendering remains an explicit caller choice.
Python callers use `build_workflow_plan(definition)` and then `to_dict()`, `to_text()`, or
`to_mermaid()`.

`--events` writes one compact, privacy-minimized JSON event per line to stderr while the
final run report remains on stdout. This makes CLI progress consumable without parsing
human text or mixing it with the terminal report.

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

## Run blocking tools in bounded subprocesses

Use `subprocess_action` when a trusted command-line tool, legacy program, or blocking Python
worker needs an operating-system process boundary:

```python
import sys
from pathlib import Path

from samsarix_orchestration import WorkflowRunner, subprocess_action

worker = subprocess_action(
    (sys.executable, "-I", str(Path("worker.py").resolve())),
    environment={"APPLICATION_MODE": "production"},
)
runner = WorkflowRunner({"external-tool": worker})
```

The executable path must be absolute and is invoked directly—never through a shell. For
each attempt the child reads one UTF-8 JSON envelope from stdin and writes exactly one
finite JSON value to stdout. The version-1 envelope includes workflow/run/step identity,
parameters, input, dependency outputs, attempt, and idempotency key; compensation calls
also include the original forward output. It deliberately omits approval prompts and
reviewer metadata.

Input, stdout, and stderr are independently bounded. Nonzero exits become ordinary failed
attempts. Stderr is excluded from errors by default because reports and checkpoints may
persist error messages; `expose_stderr=True` is an explicit debugging/privacy decision.
The child receives only explicit environment entries by default, plus a small Windows
platform allowlist required to start normal programs. Set `inherit_environment=True` only
when the child is authorized to receive all parent environment variables.

When a workflow timeout or caller cancellation arrives, Samsarix terminates the direct
child, waits for a bounded grace period, then kills it if necessary before propagating
cancellation. This fixes the lifecycle problem of uninterruptible worker threads; it does
not sandbox filesystem/network access, kill arbitrary descendant processes, or make an
external side effect exactly once. Pass the protocol idempotency key to effect destinations.
The runnable [subprocess pipeline](examples/subprocess_pipeline.py) is one file that acts as
both orchestrator and isolated worker.

## Observe progress without exposing payloads

Pass one or more sync or async event handlers when constructing the runner:

```python
from samsarix_orchestration import WorkflowEvent


async def observe(event: WorkflowEvent) -> None:
    await metrics.increment(f"workflow.{event.kind.value}")


runner = WorkflowRunner(actions, event_handlers=(observe,))
```

Within each run, handlers receive monotonically sequenced events one at a time, including
attempts, retries, restored steps, checkpoint commits, failures, blocks, and cancellation. Event
payloads deliberately exclude workflow inputs, step parameters, outputs, dependency
values, error messages, and idempotency keys. Run, workflow, and step identifiers plus
error type names remain operational data and may still be sensitive.

Delivery is ordered and backpressured: the next lifecycle transition waits for every
handler. A handler exception raises `EventDeliveryError` rather than silently losing an
audit event. Wrap a non-critical telemetry sink in its own error policy if business work
must continue during a telemetry outage. The runnable
[observer example](examples/observe_workflow.py) adapts the stream to JSON logs and
counters using only the standard library.

Ordering is per run. If one runner executes multiple runs concurrently, a shared sync
handler can be called from different worker threads and must provide its own cross-run
thread safety.

## Pause before high-risk actions

Approval gates are static pre-action barriers in workflow schema version 2. Generate a
runnable example and start it with durable storage:

```bash
samsarix-orchestration init approval.json --approval
samsarix-orchestration run approval.json \
  --checkpoint-db .samsarix-runs/approvals.db \
  --run-id release-2026-08-01
```

The command exits with `3`, reports `status: "paused"`, and prints a 64-character request
ID. No handler in that ready batch starts. Review the completed preparation-step outputs,
then resume with exactly one decision:

```bash
samsarix-orchestration run approval.json \
  --checkpoint-db .samsarix-runs/approvals.db \
  --run-id release-2026-08-01 --resume \
  --approve REQUEST_ID
```

Use `--reject REQUEST_ID` to terminate the gated step without invoking its handler. When
several requests are pending, the flags may be repeated; one rejection cancels other
pending requests and fail-fast blocks remaining work.

Python applications resume with `ApprovalDecision.approve(...)` or
`ApprovalDecision.reject(...)`. The optional `decided_by` and `reason` fields are bounded
audit labels supplied by the caller; Samsarix records but does not authenticate them. An
approved handler receives the durable record as `context.approval`.

The runtime commits a decision before invoking an approved handler. Each request is bound
to the run ID and canonical workflow, input, and dependency-output state. Competing
SQLite decisions serialize, and only one divergent decision can win. Schema v2 rejects
unknown workflow fields; older Samsarix runtimes reject version 2 rather than ignoring
an approval gate.

This primitive records authorization decisions but does not authenticate the person making
them. Applications own reviewer authentication, authorization policy, presentation of
prepared outputs, and protection of checkpoint files. Approval request IDs are identifiers,
not bearer secrets.

## Roll back partial external effects

Schema-v3 steps may name a separately registered compensating action. Generate and run a
complete local Saga demonstration:

```bash
samsarix-orchestration init order-saga.json --saga
samsarix-orchestration plan order-saga.json
samsarix-orchestration run order-saga.json \
  --checkpoint-db .samsarix-runs/sagas.db \
  --run-id order-42 --events
```

The demo intentionally fails its final forward step, compensates `charge` before `reserve`,
and exits with `1` because the business workflow did not succeed. Its report separately
records `compensation_status: "succeeded"`. This distinction prevents a successful rollback
from being mistaken for successful business completion.

Python applications pass a separate `compensations` mapping to `WorkflowRunner`. A
`CompensationContext` contains the original step output, its dependency outputs, workflow
input, and a stable `run-id:step-id:compensate` idempotency key. Compensable steps in the
same reverse dependency wave may run concurrently; prerequisites are not compensated until
all still-pending compensable dependants succeed.

The runtime checkpoints the `compensating` phase before invoking a compensator and records
each successful reverse effect after its dependency wave. If a compensator exhausts its
bounded retry policy, earlier prerequisites remain untouched and a later `resume=True`
attempt retries only unfinished compensation. As with forward actions, the effect and its
checkpoint cannot be made atomic by this library: compensators must honor their idempotency
key. Compensation is application-defined semantic repair, not database rollback or proof
that the original side effect was perfectly reversible. The runnable
[compensating order example](examples/compensating_order.py) shows the same contract with
application-defined Python handlers.

## Resume expensive or side-effecting work

Checkpointing is explicit and remains local. Give a run a stable identifier and a store:

```python
from samsarix_orchestration import JsonDirectoryCheckpointStore

store = JsonDirectoryCheckpointStore(".samsarix-runs")
result = await runner.run(
    definition,
    workflow_input,
    run_id="customer-import-2026-08-01",
    checkpoint_store=store,
    resume=True,
)
```

The first attempt omits `resume=True`. A resumed attempt must use the exact same workflow
definition and JSON input; canonical SHA-256 identities prevent accidental replay against
changed work. Schema-v1/v2 forward recovery restores only successful steps, so failed steps
run again. Schema-v3 checkpoints additionally retain terminal forward results once a Saga
enters compensation, allowing resume to continue rollback without replaying forward work. Every
handler receives a stable `context.idempotency_key` of `run-id:step-id` across attempts.
Starting a new checkpointed run with an existing run id fails closed; explicitly resume
it or choose another id.

This is an at-least-once contract, not an exactly-once claim. A process can stop after an
external effect succeeds but before its checkpoint is written, so effectful handlers must
pass the idempotency key to the target system or otherwise deduplicate it. The runnable
[resumable order example](examples/resumable_order_pipeline.py) demonstrates that crash
window without duplicating a receipt. See [real use cases](docs/USE_CASES.md) for fit and
non-fit guidance and [external consumer evidence](docs/CONSUMER_EVIDENCE.md) for the
independently installed redaction pipeline.

For multiple runs in one trusted host, use the standard-library SQLite store:

```python
from samsarix_orchestration import SqliteCheckpointStore

store = SqliteCheckpointStore(".samsarix-runs/runs.db")
```

It uses short-lived connections, bounded lock waits, `BEGIN IMMEDIATE` writes, WAL mode,
and full synchronous durability. Distinct run IDs may be saved from multiple threads or
processes on the same machine. SQLite serializes writers; competing divergent saves for
one run fail closed. It is not a cross-host coordinator and must live on a local filesystem,
not a network filesystem. Run summaries exclude outputs, and `runs show` also omits outputs
unless `--include-outputs` is explicit. Deletion requires the run ID twice.

The [SQLite batch example](examples/sqlite_batch_runs.py) executes and inspects several
independent runs. SQLite's upstream documentation describes the
[WAL concurrency model](https://www.sqlite.org/wal.html) and
[runtime pragmas](https://www.sqlite.org/pragma.html) used here.

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

The supported runtime performs no network requests, loads no dynamic modules from workflow
data, and executes no workflow strings as code. Subprocess environment access follows the
host application's explicit `subprocess_action` policy; the built-in CLI path does not use
that adapter.
Workflow JSON selects only action names that the host application explicitly registered.
Concurrency, step count, timeouts, retries, input size, and output size are bounded.
Cancellation propagates to running async actions.

Action and compensation handlers are trusted application code. In-process handlers have
the Python process's privileges; subprocess handlers run as the same operating-system user.
Samsarix Orchestration is not a sandbox. A handler that calls a model or external API owns
its authentication, destination validation, timeout, cancellation, privacy, and cost
controls. The built-in CLI path has no API or operating cost beyond local compute and disk
space for explicitly requested reports or checkpoints.

No telemetry is collected implicitly. Lifecycle events are delivered only to handlers
the application explicitly registers or when the CLI's `--events` flag is present. Run
inputs and outputs stay in memory unless `--output` is
provided or checkpointing is explicitly enabled. Both stores contain successful step
outputs in plaintext; SQLite may also create `-wal` and `-shm` sidecars. The caller controls
filesystem permissions, encryption, backups, retention, and deletion.

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
