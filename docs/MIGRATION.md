# Samsarix rename migration

The supported product name is **Samsarix Orchestration**. The `0.1.0` release
candidate introduces the Samsarix distribution, import package, and CLI while
retaining compatibility aliases for the earlier productization branch.

| Historical name | Supported name |
| --- | --- |
| Distribution `helix-orchestration` | `samsarix-orchestration` |
| Import `helix_orchestration` | `samsarix_orchestration` |
| CLI `helix-orchestration` | `samsarix-orchestration` |

## Compatibility window

The historical Python import, root module paths, `python -m` entry point, and
CLI command are aliases to the Samsarix implementation throughout `0.1.x`.
They do not maintain a second runtime. New code should use the supported names
so it does not depend on the compatibility window.

The workflow document and run-report schemas are unchanged. Files created by
the historical CLI remain readable.

## Application migration

Replace imports:

```python
from samsarix_orchestration import ActionContext, WorkflowDefinition, WorkflowRunner
```

Replace CLI invocations:

```console
samsarix-orchestration init workflow.json
samsarix-orchestration validate workflow.json
samsarix-orchestration run workflow.json --output run.json
```

The repository and support identities are:

- repository: <https://github.com/Deathcharge/samsarix-agent-orchestration>
- general and licensing inquiries: contact@samsarix.com
- support and private security reports: support@samsarix.com
