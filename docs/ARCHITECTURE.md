# Architecture

## Product boundary

Samsarix Orchestration 0.1 is an in-process Python workflow library plus a local CLI.
It is not a model framework, hosted control plane, durable queue, or security sandbox.
The supported implementation is exposed through one primary import package:

```text
samsarix_orchestration
├── spec.py       JSON schema validation and graph checks
├── runtime.py    bounded dependency-aware execution
├── actions.py    deterministic CLI demonstration actions
├── checkpoints.py bounded in-memory and atomic JSON checkpoint stores
├── sqlite_store.py transactional same-host SQLite checkpoints and inspection
├── events.py     versioned privacy-minimized lifecycle event contract
├── planning.py   deterministic dependency plans and offline Mermaid source
├── cli.py        local file/input/output boundary and exit codes
└── __main__.py   python -m entry point
```

Only these root modules and a small `helix_orchestration` compatibility namespace are
included in the wheel. The compatibility modules re-export the supported implementation
and will remain throughout the 0.1 release line. Historical, unsupported subpackages were
removed from the working tree and remain available in Git history.

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
8. When a checkpoint store is explicit, successful batch results are atomically persisted
   with canonical workflow and input digests. Resume restores only matching successful
   steps and recomputes the remaining graph.
9. Explicit event handlers receive serialized lifecycle transitions in per-run sequence
   order. Delivery is backpressured; no background telemetry task survives the run.
10. In workflow schema version 2, a ready step with an approval policy creates a durable
    request before the complete ready batch yields. Resume durably records approve or
    reject before any approved handler can start.
11. `build_workflow_plan` derives dependency waves and visualization metadata solely from
    the validated definition. It never resolves actions, reads run input, or contacts a
    renderer; Mermaid output is deterministic source text with internal node identifiers.
12. Schema-v3 failures and approval rejections transition a durable checkpoint to
    `compensating` before reverse handlers start. Successful effects are reversed in
    dependency-safe waves; completed reversals persist and are skipped on resume.

The runtime stores no hidden global workflow state. A `WorkflowRunner` contains only
the host application's explicit forward-action registry, compensation registry, and
configuration.

## Trust boundaries

- Workflow definitions, inline input, and input files are untrusted data. They cannot
  select Python modules or executable code; action names resolve only against the
  registry supplied by the host application.
- Registered handlers are trusted code with the process's full filesystem, network,
  environment, and subprocess privileges. The runtime is not an isolation boundary.
- Compensation names resolve only through a separate host-supplied registry. Workflow
  data cannot turn a forward action into an implicitly trusted compensator.
- Dependency outputs remain in memory and are passed only to declared dependants. They
  must be finite JSON and are limited to 1 MiB per step by default.
- The CLI writes only explicit target paths. Existing files require explicit force
  flags. Forced writes use a same-directory temporary file, flush, `fsync`, and atomic
  replacement.
- No network, telemetry, credential, or provider boundary exists in the supported package.
  SQLite persistence is opt-in, local, and uses only Python's standard library.
- Lifecycle events omit inputs, parameters, outputs, dependency values, error messages,
  and idempotency keys. They retain run/workflow/step identifiers and exception type names,
  which applications must classify and protect as operational data.
- Approval request IDs are integrity-binding identifiers, not authentication tokens.
  The embedding application authenticates reviewers, authorizes decisions, and controls
  which prepared outputs are shown to them.

## Reliability properties and limits

- Validation occurs again when programmatically constructed definitions reach the
  runner.
- Sync actions run in worker threads so they do not directly block the event loop.
- Async actions receive cancellation; Python cannot forcibly stop a sync worker thread,
  so sync handlers must cooperate with their own external timeouts. After a sync timeout,
  the runner skips configured retries to avoid overlapping the same side effect.
- Async work reaches a terminal state before the run report is returned. A timed-out sync
  worker may still be exiting in the background, so handlers must bound their own I/O.
- Checkpoint stores are opt-in. The bundled JSON store writes one bounded file per run
  with same-directory temporary files and atomic replace and requires application-owned
  writer coordination.
- The SQLite store owns a versioned schema using SQLite `application_id` and `user_version`.
  Each operation opens its own connection, bounds lock waiting, validates the schema,
  and uses WAL plus full synchronous durability. Writes begin with `BEGIN IMMEDIATE`.
  Distinct same-host runs can progress concurrently, although SQLite permits only one
  writer at a time. Same-run identity changes, regressions, and divergent successful
  results are rejected inside the write transaction.
- SQLite WAL requires all processes to share one host and does not support a network
  filesystem deployment. Database growth and retention remain operator-managed.
- Checkpointing is at-least-once. A crash between an external effect and checkpoint commit
  can repeat the handler; the stable `run-id:step-id` idempotency key lets the destination
  deduplicate that effect.
- Compensation has the same at-least-once boundary and uses the stable
  `run-id:step-id:compensate` key. It is semantic repair supplied by the application, not
  an ACID rollback guarantee. Failed compensation halts earlier prerequisite reversal;
  cancellation or process loss leaves the durable phase resumable.
- Approval is at-most-one-decision per request. Requests bind the exact run, workflow,
  input, gated step, and dependency outputs. All bundled stores enforce monotonic approval
  records; SQLite serializes competing decisions in the same transaction as the checkpoint.
- The barrier is global for a ready batch: if any ready step awaits approval, no ready
  handler starts. A rejection invokes no gated handler, cancels sibling pending requests,
  and fail-fast blocks all remaining steps.
- Approval is static and occurs before an action attempt. It is not a stack continuation,
  dynamic tool-call interrupt, payload editor, identity provider, or policy engine.
- Timestamps and durations are observations, not a durable audit log.
- Event handlers are trusted application code. Sync handlers run in a worker thread; sync
  and async handlers are invoked one at a time and awaited before execution advances.
  Handler failure raises `EventDeliveryError`. Delivery is in-process and not durable;
  handlers can partially accept an event before a later handler fails.
- Ordering is per invocation. Concurrent runs have independent dispatchers, so shared sync
  handlers must provide their own cross-run thread safety.

## Why this scope

The original repository mixed a fake CLI, incomplete Helix-specific agent code, local
simulations, packaging metadata, and deployment documents for a service that did not
exist. The reusable core was its workflow graph intent. The 0.1 boundary preserves that
intent as a small product that can be installed, tested, understood, and adopted without
private services.

Current low-level orchestration tools emphasize durable execution, persistence,
streaming, and human approval, while general workflow tools expose explicit task states,
timeouts, retries, and resumability. Samsarix Orchestration 0.1 implements the transparent
embedded subset it can support honestly. Distributed execution and exactly-once effects
remain explicit non-goals rather than simulated features.

The approval contract was informed by current official patterns: LangGraph requires a
checkpointer and stable thread identity for interrupts, Prefect distinguishes pause from
suspend/re-entry, and Temporal separates asynchronous signals from validated updates.
Samsarix implements only the bounded embedded pre-action subset:

- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.prefect.io/v3/advanced/interactive
- https://github.com/temporalio/sdk-python

Offline planning follows the graph-inspection ergonomics documented by LangGraph and
Prefect while retaining the zero-runtime-dependency boundary:

- https://docs.langchain.com/oss/python/langgraph/use-graph-api#visualize-your-graph
- https://docs.prefect.io/v3/api-ref/python/prefect-flows#prefect.flows.Flow.visualize

Compensation follows the orchestrated Saga and transaction-rollback principles documented
by AWS and Prefect while retaining explicit handlers and local persistence:

- https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html
- https://docs.prefect.io/v3/advanced/transactions
