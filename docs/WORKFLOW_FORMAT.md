# Workflow format

Workflow files are UTF-8 JSON objects using schema version 1 or 2.

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
| `version` | No | Defaults to `1`; versions `1` and `2` are accepted. |
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
| `approval` | Version 2 only | `{"prompt": "..."}`; non-empty prompt, at most 500 characters. |

Unknown top-level or step fields are ignored in schema version 1 so metadata producers
can add annotations without changing execution. They are never passed to action
handlers.

Schema version 2 rejects every unknown workflow, step, and approval field. This strictness
is intentional: a misspelled or future safety field cannot silently disappear. Approval
gates require an explicit `"version": 2`; version 1 rejects the `approval` field.

An approval gate pauses the complete ready batch before any action handler starts. It
requires an explicit run ID and checkpoint store. The request binds the step to canonical
workflow, input, and dependency-output digests. A durable `approve` decision permits the
handler to start on resume. A `reject` decision creates a `rejected` step result without an
attempt and blocks remaining work. Approval is static and pre-action; handlers cannot
pause partway through their own code.

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

Results must be finite JSON and fit within the runner's output bound. An exception or
timeout consumes an attempt. When all attempts fail, the step is `failed`; dependent
steps become `blocked`. A synchronous-handler timeout ends the step immediately without
using configured retries because Python cannot stop the worker thread and a retry could
overlap the same external side effect.

The CLI exposes only `collect`, `echo`, `uppercase`, and `word_count`. Applications
register real actions through `WorkflowRunner`; workflow files cannot import them.

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

Run reports add the following fields:

| Field | Meaning |
| --- | --- |
| `resumed` | Whether this invocation requested checkpoint restoration. |
| `restored_steps` | Number of successful results reused without invoking their handlers. |
| `schema_version` | Present for version-2 reports. |
| `approvals` | Ordered durable approval records in version-2 reports. |

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
| `schema_version` | Event schema version; `1` or `2`. |
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

Events never contain workflow input, step parameters, output or dependency values, error
messages, or idempotency keys. Identifiers and error type names remain visible. Delivery
is in-process, ordered, and backpressured rather than a durable log. A handler exception
raises `EventDeliveryError`; already completed external effects are not rolled back.
