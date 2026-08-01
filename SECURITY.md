# Security policy

## Supported scope

Security support for 0.1 covers the `samsarix_orchestration` implementation,
the `helix_orchestration` compatibility namespace, both console-script names,
package metadata, CI, and the documented workflow journey.

The runtime treats workflow JSON and run inputs as untrusted data. Registered Python
actions are trusted application code with full process privileges; Samsarix
Orchestration is not a sandbox. Applications that expose workflows remotely or add
filesystem, subprocess, network, model, database, or credential access own
authentication, authorization, destination controls, cancellation, idempotency,
privacy, and cost limits at that boundary.

Checkpointing is opt-in and persists successful step outputs as plaintext JSON. The
bundled directory store hashes run identifiers for filenames, bounds reads and writes,
validates workflow/input identities, and replaces files atomically. The SQLite store
rejects symbolic-link database paths and unowned or modified schemas, bounds reads and lock
waits, and transactionally rejects same-run regression or divergent successful results.
It supports concurrent processes only on one host and must not use a network filesystem.

Applications remain responsible for filesystem access controls, at-rest encryption,
retention, deletion, backups, free-space monitoring, and coordinating one active executor
per logical run. SQLite creates `-wal` and `-shm` sidecars during use; protect and retain
them consistently with the database. Neither store cryptographically authenticates data
against a malicious local writer.

Lifecycle observation is opt-in. Version 1 events exclude workflow inputs, parameters,
outputs, dependency values, error messages, and idempotency keys. They do include run,
workflow, and step identifiers plus exception type names. Treat those fields as
operational data, register only trusted event handlers, and apply authentication,
redaction, transport security, retention, and access controls in any external telemetry
adapter. Event handlers execute with application privileges and are not a sandbox.

## Reporting

Report suspected vulnerabilities through a private GitHub security advisory for
`Deathcharge/samsarix-agent-orchestration` when that option is available. Otherwise
email support@samsarix.com with the subject `Private security report: Samsarix
Orchestration`. Do not post exploit details or secrets in a public issue.

Include the affected version or commit, operating system and Python version, the
smallest reproduction, impact, and any relevant deployment assumptions. Do not include
real credentials, personal data, or third-party private content.

No response-time or bounty commitment is implied.
