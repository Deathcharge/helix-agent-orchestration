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
validates workflow/input identities, and replaces files atomically. Applications remain
responsible for directory access controls, encryption, retention, deletion, backups, and
ensuring only one writer owns a run. Checkpoints are integrity-checked for compatibility,
not cryptographically authenticated against a malicious local writer.

## Reporting

Report suspected vulnerabilities through a private GitHub security advisory for
`Deathcharge/samsarix-agent-orchestration` when that option is available. Otherwise
email support@samsarix.com with the subject `Private security report: Samsarix
Orchestration`. Do not post exploit details or secrets in a public issue.

Include the affected version or commit, operating system and Python version, the
smallest reproduction, impact, and any relevant deployment assumptions. Do not include
real credentials, personal data, or third-party private content.

No response-time or bounty commitment is implied.
