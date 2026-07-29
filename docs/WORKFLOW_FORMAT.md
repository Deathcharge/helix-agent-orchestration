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
object, and `context.attempt` starts at 1.

Results must be finite JSON and fit within the runner's output bound. An exception or
timeout consumes an attempt. When all attempts fail, the step is `failed`; dependent
steps become `blocked`. A synchronous-handler timeout ends the step immediately without
using configured retries because Python cannot stop the worker thread and a retry could
overlap the same external side effect.

The CLI exposes only `collect`, `echo`, `uppercase`, and `word_count`. Applications
register real actions through `WorkflowRunner`; workflow files cannot import them.
