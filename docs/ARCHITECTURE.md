# Architecture

## Product boundary

Helix Orchestration 0.1 is an in-process Python workflow library plus a local CLI.
It is not a model framework, hosted control plane, durable queue, or security sandbox.
The supported distribution contains one import package:

```text
helix_orchestration
├── spec.py       JSON schema validation and graph checks
├── runtime.py    bounded dependency-aware execution
├── actions.py    deterministic CLI demonstration actions
├── cli.py        local file/input/output boundary and exit codes
└── __main__.py   python -m entry point
```

Only these root modules are included in the wheel. Historical subpackages in the source
tree are deliberately outside the package manifest and release quality gate.

## Execution model

1. `load_workflow` bounds the workflow file to 1 MiB, decodes UTF-8 JSON, and returns
   every discoverable structural or graph validation issue.
2. `WorkflowDefinition` requires unique bounded identifiers, known dependencies,
   finite JSON parameters, a directed acyclic graph, 1–256 steps, and concurrency,
   timeout, retry, and delay limits.
3. `WorkflowRunner` rejects unregistered actions and non-JSON or oversized inputs
   before starting work.
4. Steps whose dependencies succeeded become ready. Ready steps run concurrently under
   an `asyncio.Semaphore`; result order always follows definition order.
5. Each attempt is wrapped in `asyncio.wait_for`. A failure is retried only within the
   step's declared retry and delay bounds.
6. A terminal step result contains state, attempts, timestamps, duration, JSON output,
   or a bounded structured error. With the default fail-fast policy, steps not yet
   started become `blocked` after the first failed batch.
7. Cancellation cancels the active batch and propagates `CancelledError` to the caller.
   The CLI translates a user interrupt to exit code 130.

The runtime stores no hidden global workflow state. A `WorkflowRunner` contains only
the host application's explicit action registry and configuration.

## Trust boundaries

- Workflow definitions, inline input, and input files are untrusted data. They cannot
  select Python modules or executable code; action names resolve only against the
  registry supplied by the host application.
- Registered handlers are trusted code with the process's full filesystem, network,
  environment, and subprocess privileges. The runtime is not an isolation boundary.
- Dependency outputs remain in memory and are passed only to declared dependants. They
  must be finite JSON and are limited to 1 MiB per step by default.
- The CLI writes only explicit target paths. Existing files require explicit force
  flags. Forced writes use a same-directory temporary file, flush, `fsync`, and atomic
  replacement.
- No network, telemetry, credential, database, or provider boundary exists in the
  supported package. Applications that add one own its policy and operational controls.

## Reliability properties and limits

- Validation occurs again when programmatically constructed definitions reach the
  runner.
- Sync actions run in worker threads so they do not directly block the event loop.
- Async actions receive cancellation; Python cannot forcibly stop a sync worker thread,
  so sync handlers must cooperate with their own external timeouts.
- A run report is returned only after all started work reaches a terminal state.
- There is no checkpoint/resume. A process crash requires a new run, and handlers with
  external side effects must provide their own idempotency.
- Timestamps and durations are observations, not a durable audit log.

## Why this scope

The original repository mixed a fake CLI, incomplete Helix-specific agent code, local
simulations, packaging metadata, and deployment documents for a service that did not
exist. The reusable core was its workflow graph intent. The 0.1 boundary preserves that
intent as a small product that can be installed, tested, understood, and adopted without
private services.

Current low-level orchestration tools emphasize durable execution, persistence,
streaming, and human approval, while general workflow tools expose explicit task states,
timeouts, and retries. Helix 0.1 implements only the transparent local subset it can
support honestly. Durable state and distributed execution remain explicit non-goals
rather than simulated features.
