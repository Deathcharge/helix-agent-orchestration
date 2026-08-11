# Workflow format

Workflow files are UTF-8 JSON objects using schema version 1, 2, or 3.

```json
{
  "version": 1,
  "name": "example",
  "description": "Optional human-readable purpose.",
  "max_concurrency": 4,
  "steps": [
    {
      "id": "fetch",
      "agent": "source",
      "action": "fetch",
      "dependencies": [],
      "parameters": {},
      "timeout_seconds": 30,
      "retries": 0,
      "retry_delay_seconds": 0
    },
    {
      "id": "summarize",
      "agent": "writer",
      "action": "summarize",
      "dependencies": ["fetch"]
    }
  ]
}
```

## Workflow fields

| Field | Required | Constraints |
| --- | --- | --- |
| `version` | No | Defaults to `1`; versions `1`, `2`, and `3` are accepted. |
| `name` | Yes | Non-empty string, at most 128 characters. |
| `description` | No | String, at most 2,000 characters. |
| `max_concurrency` | No | Integer from 1 to 64; defaults to 4. |
| `steps` | Yes | Array containing 1 to 256 step objects. |

## Step fields

| Field | Required | Constraints |
| --- | --- | --- |
| `id` | Yes | Unique identifier matching `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. |
| `action` | Yes | Registered action name using the same identifier syntax. |
| `agent` | No | Logical owner label using the same syntax; defaults to `local`. |
| `dependencies` | No | Unique known step ids; the complete graph must be acyclic. |
| `parameters` | No | JSON object containing finite JSON values. |
| `timeout_seconds` | No | Greater than 0 and at most 3,600; defaults to 30. |
| `retries` | No | Integer from 0 to 10; defaults to 0. |
| `retry_delay_seconds` | No | Number from 0 to 300; defaults to 0. |
| `approval` | Version 2 or 3 | `{"prompt": "..."}`; non-empty prompt, at most 500 characters. |
| `compensation` | Version 3 only | Named reverse action with independently bounded timeout and retry policy. |

Unknown top-level or step fields are ignored in schema version 1 so metadata producers
can add annotations without changing execution. They are never passed to action
handlers.

Schema versions 2 and 3 reject every unknown workflow, step, approval, and compensation
field. This strictness
is intentional: a misspelled or future safety field cannot silently disappear. Approval
gates require version 2 or 3; compensating actions require version 3. Earlier versions
reject rather than ignore those safety policies.

An approval gate pauses the complete ready batch before any action handler starts. It
requires an explicit run ID and checkpoint store. The request binds the step to canonical
workflow, input, and dependency-output digests. A durable `approve` decision permits the
handler to start on resume. A `reject` decision creates a `rejected` step result without an
attempt and blocks remaining work. Approval is static and pre-action; handlers cannot
pause partway through their own code.

A compensation object has this shape:

```json
{
  "action": "refund-payment",
  "timeout_seconds": 30,
  "retries": 2,
  "retry_delay_seconds": 1
}
```

`action` uses the normal identifier syntax. Timeout and retry bounds are identical to a
forward step but independent from it. The host registers compensators in the runner's
separate `compensations` mapping; registering a forward action never implicitly authorizes
an undo action. After failure or rejection, successful compensable steps run in reverse
dependency order. Independent steps at one reverse depth may run concurrently. If any
compensation in a wave fails, its prerequisites remain untouched until a later resume.

## Action contract

An action is a trusted sync or async callable registered by name:

```python
def action(context: ActionContext) -> JSONValue: ...
```

`context.workflow_input` is the run input. `context.dependencies` maps each declared
dependency id to its output. `context.step.parameters` is the step's JSON parameter
object, and `context.attempt` starts at 1. `context.run_id` identifies the logical run;
`context.idempotency_key` is stable for that run and step across retries and resumes.
For a gated step, `context.approval` is the durable approved record; it is `None` for an
ungated step.

A compensator receives `CompensationContext`: the original step and successful output,
workflow input, dependency outputs, attempt number, run ID, and stable
`run-id:step-id:compensate` idempotency key. Compensation outputs follow the same finite-JSON
and size bounds as forward results.

Results must be finite JSON and fit within the runner's output bound. An exception or
timeout consumes an attempt. When all attempts fail, the step is `failed`; dependent
steps become `blocked`. A synchronous-handler timeout ends the step immediately without
using configured retries because Python cannot stop the worker thread and a retry could
overlap the same external side effect.

### Subprocess action protocol

Host code may wrap a fixed trusted command with `subprocess_action`. This does not add a
workflow field: JSON still selects only the registered action name. The executable path is
absolute, arguments are not interpolated, and no shell is involved. Each attempt writes one
newline-terminated envelope to stdin:

```json
{
  "schema_version": 1,
  "kind": "action",
  "workflow": "document-pipeline",
  "run_id": "import-42",
  "idempotency_key": "import-42:extract",
  "attempt": 1,
  "step": {
    "id": "extract",
    "agent": "local",
    "action": "external-tool",
    "parameters": {"mode": "strict"},
    "compensation_action": null
  },
  "workflow_input": {"document": "example"},
  "dependencies": {},
  "output": null
}
```

`kind` is `compensation` for a separately registered compensator; then `output` is the
original successful forward output and `step.compensation_action` names the configured
reverse action. Approval prompts and decision provenance are omitted. The child must emit
exactly one finite UTF-8 JSON value on stdout and exit zero. A nonzero exit, empty/invalid
output, stream-limit violation, or spawn error fails the attempt under the step's normal
retry policy.

By default the child receives no general parent environment. The Windows implementation
retains a bounded platform startup allowlist; caller-specified variables are added. Full
inheritance, stderr disclosure, working directory, stream ceilings, and terminate grace are
explicit Python API choices. Cancellation terminates, then kills if needed, the direct child.
This protocol provides interruptible trusted-process execution, not an untrusted-code sandbox.

The CLI exposes provider-free `collect`, `echo`, `fail`, `uppercase`, and `word_count`
forward actions plus the `compensate` handler used by `init --saga`. Applications register
real handlers through `WorkflowRunner`; workflow files cannot import them.

## Checkpoint and report contract

Checkpoint version 1 stores the run id, canonical SHA-256 digests of the complete workflow
and input, the save timestamp, and successful step results. A resume fails closed when the
workflow, input, step metadata, dependency closure, JSON bounds, or checkpoint version does
not match. Failed, blocked, cancelled, pending, and running results are never restored.

Checkpoint version 2 additionally stores ordered approval records. Each record includes
the request and context digests, step ID, bounded prompt, request time, state
(`pending`, `approved`, `rejected`, or `cancelled`), and bounded optional decision metadata.
Within each store's writer-coordination contract, saves reject removed requests, changed
request identity, decision reversal, successful-step regression, and divergence.
Checkpoints use the same version as their workflow.

Checkpoint version 3 adds a strict `phase` (`forward`, `compensating`, or `complete`) and
ordered successful compensation results. Once compensation begins, terminal forward
results are retained so resume continues rollback without replaying forward actions.
Failed compensation attempts remain retryable and are not recorded as completed. A
`complete` checkpoint is immutable.

Run reports add the following fields:

| Field | Meaning |
| --- | --- |
| `resumed` | Whether this invocation requested checkpoint restoration. |
| `restored_steps` | Forward results restored without invoking handlers; only successful results in v1/v2, terminal results during v3 compensation. |
| `schema_version` | Present for version-2 and version-3 reports. |
| `approvals` | Ordered durable approval records in version-2 and version-3 reports. |
| `compensation_status` | Version-3 reverse outcome: `not_requested`, `succeeded`, or `failed`. |
| `compensations` | Version-3 compensation results, distinct from forward step results. |

Invocation status can be `paused` while requests await decisions or `rejected` after a
negative decision, in addition to `succeeded` and `failed`. A paused result contains only
steps that have already reached a terminal state; pending steps have not run. If a result
ever contains both failed and rejected steps, `failed` takes precedence in the run status
and terminal event.

The JSON directory store bounds each file to 16 MiB by default and uses a SHA-256 hash of
the run id as its filename. The run id remains inside the auditable JSON document.

The SQLite store uses the same checkpoint document and default 16 MiB per-checkpoint bound.
Its payload-free summary contract contains `run_id`, both identity digests, `saved_at`,
`successful_steps`, and `checkpoint_bytes`. Summary queries fetch no checkpoint JSON.
CLI `runs show` loads a validated checkpoint but omits outputs by default; the explicit
`--include-outputs` option reveals the complete stored document. `runs delete` requires
an exact repeated run ID confirmation. There is no implicit retention or bulk deletion.

SQLite databases are identified with application id `0x53584f52` and schema version 1.
Existing unowned databases, changed schemas, invalid identities, corrupt JSON, inconsistent
lengths, and checkpoints above the configured bound fail closed.

## Lifecycle event contract

`WorkflowRunner(..., event_handlers=(...))` emits events matching the workflow schema
version. Each run starts
its sequence at 1, and every handler observes events in ascending sequence order. The CLI
exposes the same JSON representation as JSON Lines on stderr with `run --events`.

| Field | Meaning |
| --- | --- |
| `schema_version` | Event schema version; `1`, `2`, or `3`. |
| `sequence` | Monotonic per-invocation delivery order. |
| `kind` | Run, step-attempt, retry, restore, checkpoint, or terminal transition. |
| `run_id`, `workflow` | Logical run and workflow identifiers. |
| `occurred_at` | UTC observation timestamp. |
| `step_id`, `attempt`, `state` | Step context when applicable, otherwise `null`. |
| `duration_ms` | Observed terminal duration when applicable. |
| `error_type` | Exception or blocking-policy type without the error message. |
| `resumed` | Whether the event describes a resumed invocation or restored step. |
| `approval_id`, `decision` | Version-2 operational identifiers; otherwise absent. |

The version 1 kinds are `run_started`, `step_restored`, `step_attempt_started`,
`step_retry_scheduled`, `step_succeeded`, `step_failed`, `step_blocked`,
`step_cancelled`, `checkpoint_saved`, `run_succeeded`, `run_failed`, and
`run_cancelled`.

Version 2 adds `approval_requested`, `approval_recorded`, `step_rejected`, `run_paused`,
and `run_rejected`. Approval events expose request IDs and decision kinds but exclude
prompts, reviewer identity, reasons, input, parameters, and dependency outputs.

Version 3 adds `compensation_started`, `compensation_retry_scheduled`,
`compensation_succeeded`, `compensation_failed`, `compensation_cancelled`, and
`compensation_restored`. They expose no original or compensation outputs.

Events never contain workflow input, step parameters, output or dependency values, error
messages, or idempotency keys. Identifiers and error type names remain visible. Delivery
is in-process, ordered, and backpressured rather than a durable log. A handler exception
raises `EventDeliveryError`; already completed external effects are not rolled back.

## Static plan contract

`build_workflow_plan(workflow)` and `samsarix-orchestration plan` revalidate the definition
and derive a plan without resolving action handlers or executing code. Plan schema version
2 contains the workflow schema version and canonical digest, ordered step inventory,
dependency/dependent edges, roots, leaves, maximum concurrency, deterministic dependency
waves, approval flags, compensation actions, and one longest dependency chain. The digest uses the same
canonical JSON contract as checkpoints. A wave's `approval_barrier` is true when any step
in that wave has an approval policy.

Text is intended for terminals, JSON is the stable machine interface, and Mermaid is
offline source for an application-selected renderer. Plans do not predict handler duration,
dynamic external behavior, retry outcomes, semaphore scheduling order within a wave, or
whether a reviewer will approve a gate. Approval prompts are deliberately omitted from
Mermaid output.
