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

`subprocess_action` is a lifecycle and memory boundary for trusted local executables, not
a sandbox. Only host Python code can register it. The executable must be an absolute path,
arguments are fixed at registration, and the adapter calls the OS directly without a shell;
workflow input and parameters cannot rewrite the command. The child still runs as the same
OS user and can access that user's files, network, devices, and other permitted resources.
Use an actual container, restricted account, sandbox, or policy engine for untrusted code.

The subprocess protocol intentionally transmits workflow input, step parameters, dependency
outputs, run/step identity, and the idempotency key. Compensation requests also transmit the
original forward output. Treat stdin and the worker as part of the same data-classification
boundary. The default child environment contains only explicit entries and a small Windows
startup allowlist (`SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, `TEMP`, and `TMP` when
present). `inherit_environment=True` may expose credentials and must be an explicit trust
decision. Explicit variables replace platform-equivalent names case-insensitively on Windows.

Protocol stdin, stdout, and stderr have independent configurable limits, each capped at
16 MiB. Output must be exactly one finite UTF-8 JSON value. Stderr is hidden from persisted
step errors unless `expose_stderr=True`; enable that only when its possible secret/PII content
is acceptable in reports, checkpoints, and logs. Output bounds limit data retained by the
adapter but cannot prevent a malicious child from consuming CPU, memory, disk, or network.

On cancellation or runner timeout, the adapter terminates the direct child, waits for a
bounded grace period, then kills and reaps it. Operating-system process creation can itself
be temporarily uninterruptible, and descendants that detach or outlive their parent are not
covered. Workers must not leave descendants holding the protocol streams after the direct
child exits because those inherited handles can prevent protocol completion. The adapter
provides neither an effect-delivery guarantee nor exactly-once execution. Termination can
happen before the child makes an effect, or after it makes an effect but before it emits or
checkpoints success. Workers must apply the supplied idempotency key at the destination.

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

Approval gates are available in strict workflow schema versions 2 and 3. Older runtimes
reject those versions, preventing them from silently ignoring a gate. A pending gate persists
before returning `paused`; the full ready batch remains behind the barrier. An approve or
reject decision persists before the runtime invokes or rejects the gated step. Store
monotonicity prevents normal callers from removing a request or reversing a decided one.
SQLite enforces that check transactionally and permits only one winner among concurrent
divergent decisions. The in-memory guard applies within one store instance, while the JSON
store requires application-owned single-writer coordination for each run.

This is an execution barrier, not an identity or authorization system. Request IDs are
not bearer secrets. Applications must authenticate the reviewer, authorize the requested
operation, prevent confused-deputy use, and pass decisions only after displaying the
correct bound run and prepared outputs. A malicious process with checkpoint write access
can forge data because checkpoints are not cryptographically authenticated.

Approval prompts, reviewer labels, reasons, timestamps, request IDs, context digests, and
successful preparation outputs are plaintext checkpoint or report data. Default lifecycle
events omit prompts, labels, reasons, and outputs but retain request/run/step identifiers
and decision kinds. Protect all of these according to their classification and avoid
placing credentials in prompts or reasons.

Compensating actions require strict schema version 3, an explicit run ID, durable
checkpoint storage, and a separately registered handler. The checkpoint enters the
`compensating` phase before a reverse handler starts. Successful compensation outputs are
plaintext checkpoint data subject to the same access, retention, size, and integrity risks
as forward outputs. Default events omit both kinds of outputs.

Compensation is at least once. A crash, cancellation, synchronous timeout, or event-delivery
failure can occur after the external reverse effect but before its success checkpoint.
Handlers must use `CompensationContext.idempotency_key` at the destination or otherwise
deduplicate. Python cannot terminate timed-out synchronous compensators; Samsarix therefore
does not retry them in the same invocation and will not compensate their prerequisites.
Applications must design and test the semantic limits of every undo operation—some effects
are irreversible, externally observed, or only partially repairable.

Static planning revalidates workflow data but does not import handlers or execute actions.
Text, JSON, and Mermaid plans expose workflow, step, action, agent, and dependency
identifiers as operational metadata; text and JSON also expose the canonical workflow
digest. Compensation action identifiers are also exposed. Parameters and approval prompts
are omitted. Mermaid uses generated node IDs and
emits source only; the caller chooses and trusts any renderer.

Lifecycle observation is opt-in. Events exclude workflow inputs, parameters,
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

## Release integrity

The release workflow runs only when a GitHub release is published, checks out that immutable
tag, and requires it to equal `v<project.version>`. Its third-party actions are pinned to full
commit hashes. Build provenance uses GitHub/Sigstore artifact attestations, and PyPI upload
uses a short-lived OIDC credential scoped to the protected `pypi` environment; no persistent
package-index token is required.

Treat changes to `.github/workflows/release.yml`, the GitHub environment policy, and the PyPI
Trusted Publisher identity as release-credential changes. Require deliberate review and keep
the environment limited to version tags. Provenance proves the build origin and instructions,
not that the released code is vulnerability-free. See [release operations](docs/RELEASING.md)
for publication, verification, failure, and yank procedures.
