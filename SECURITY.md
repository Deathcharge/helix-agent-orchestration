# Security policy

## Supported scope

Security support for 0.1 covers the modules included in the built
`helix_orchestration` wheel, its console script, package metadata, CI, and the documented
workflow journey. Historical source subpackages explicitly excluded by
`pyproject.toml` and `MANIFEST.in` are not supported runtime code.

The runtime treats workflow JSON and run inputs as untrusted data. Registered Python
actions are trusted application code with full process privileges; Helix is not a
sandbox. Applications that expose workflows remotely or add filesystem, subprocess,
network, model, database, or credential access own authentication, authorization,
destination controls, cancellation, idempotency, privacy, and cost limits at that
boundary.

## Reporting

Report suspected vulnerabilities through a private GitHub security advisory for
`Deathcharge/helix-agent-orchestration` when that option is available. If private
reporting is unavailable, open a minimal issue asking the maintainer for a private
channel without posting exploit details or secrets.

Include the affected version or commit, operating system and Python version, the
smallest reproduction, impact, and any relevant deployment assumptions. Do not include
real credentials, personal data, or third-party private content.

No response-time or bounty commitment is implied. The owner must establish those terms
before public release.
