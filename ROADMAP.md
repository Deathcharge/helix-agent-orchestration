# Samsarix Orchestration roadmap

This roadmap separates four gates: merge, release, publication, and flagship adoption. Passing one does not imply the next.

## Product boundary

Portfolio role: **reusable library or sdk**. Keep this as a small, independently versioned package. Samsarix Unified should consume it only through a public API adapter; private monorepo imports and copied implementations are out of scope.

Current disposition: the prerelease-quality foundation is merged. Build competitive
increments behind focused, green pull requests; publication remains a separate owner gate.

## Stabilize the productized default

- Keep the default branch buildable from a clean checkout and preserve exact-head CI evidence.
- Keep Samsarix LLC branding, package identity, license metadata, and compatibility aliases internally consistent.
- Preserve the pre-productization default under a rollback ref before merging; do not delete legacy history.
- Completed: a timed-out synchronous handler is not retried concurrently.
- Completed: bounded local checkpoints restore only digest-matched successful steps and
  expose stable idempotency keys for effectful handlers.
- Completed: schema-versioned lifecycle events expose ordered, privacy-minimized
  progress to application-owned observers and the CLI.
- MPL-2.0 licensing and Samsarix LLC ownership are authorized and merged.
- Completed: an exact-pin external consumer validates checkpoints, lifecycle events,
  idempotent publishing, payload privacy, and measurable avoided redaction work.

## Release candidate

- Build and install the wheel in a clean environment.
- Prove one real consumer and a versioned compatibility fixture. Completed by
  `samsarix-integration-examples` merge `41ea9221f88c66d469c022075c9c9c49400a7961`.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

Current hardening backlog:

- Local step checkpointing and idempotency keys are implemented; process isolation,
  compensation, human pauses, distributed workers, and cross-host coordination remain.
- No release/tag/package-index verification or third-party user evidence.
- The current differentiation is bounded, auditable, zero-dependency embedded recovery;
  a separate installed consumer now validates that wedge across a package boundary.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- Add a consumer-owned contract fixture covering authentication, privacy, limits, errors, and version compatibility.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
