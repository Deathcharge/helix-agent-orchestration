# Workflow format

Workflow files are UTF-8 JSON objects using schema version 1.

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
| `version` | No | Defaults to `1`; no other version is accepted. |
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

Unknown top-level or step fields are ignored in schema version 1 so metadata producers
can add annotations without changing execution. They are never passed to action
handlers.

## Action contract

An action is a trusted sync or async callable registered by name:

```python
def action(context: ActionContext) -> JSONValue: ...
```

`context.workflow_input` is the run input. `context.dependencies` maps each declared
dependency id to its output. `context.step.parameters` is the step's JSON parameter
object, and `context.attempt` starts at 1. `context.run_id` identifies the logical run;
`context.idempotency_key` is stable for that run and step across retries and resumes.

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

Run reports add two fields:

| Field | Meaning |
| --- | --- |
| `resumed` | Whether this invocation requested checkpoint restoration. |
| `restored_steps` | Number of successful results reused without invoking their handlers. |

The JSON directory store bounds each file to 16 MiB by default and uses a SHA-256 hash of
the run id as its filename. The run id remains inside the auditable JSON document.

## Lifecycle event contract

`WorkflowRunner(..., event_handlers=(...))` emits schema version 1 events. Each run starts
its sequence at 1, and every handler observes events in ascending sequence order. The CLI
exposes the same JSON representation as JSON Lines on stderr with `run --events`.

| Field | Meaning |
| --- | --- |
| `schema_version` | Event schema version; currently `1`. |
| `sequence` | Monotonic per-invocation delivery order. |
| `kind` | Run, step-attempt, retry, restore, checkpoint, or terminal transition. |
| `run_id`, `workflow` | Logical run and workflow identifiers. |
| `occurred_at` | UTC observation timestamp. |
| `step_id`, `attempt`, `state` | Step context when applicable, otherwise `null`. |
| `duration_ms` | Observed terminal duration when applicable. |
| `error_type` | Exception or blocking-policy type without the error message. |
| `resumed` | Whether the event describes a resumed invocation or restored step. |

The version 1 kinds are `run_started`, `step_restored`, `step_attempt_started`,
`step_retry_scheduled`, `step_succeeded`, `step_failed`, `step_blocked`,
`step_cancelled`, `checkpoint_saved`, `run_succeeded`, `run_failed`, and
`run_cancelled`.

Events never contain workflow input, step parameters, output or dependency values, error
messages, or idempotency keys. Identifiers and error type names remain visible. Delivery
is in-process, ordered, and backpressured rather than a durable log. A handler exception
raises `EventDeliveryError`; already completed external effects are not rolled back.
