# Samsarix Orchestration roadmap

This roadmap separates four gates: merge, release, publication, and flagship adoption. Passing one does not imply the next.

## Product boundary

Portfolio role: **reusable library or sdk**. Keep this as a small, independently versioned package. Samsarix Unified should consume it only through a public API adapter; private monorepo imports and copied implementations are out of scope.

Current disposition: Merge as a prerelease-quality foundation after the focused merge gates pass; release remains blocked on the items below.

## Stabilize the productized default

- Keep the default branch buildable from a clean checkout and preserve exact-head CI evidence.
- Keep Samsarix LLC branding, package identity, license metadata, and compatibility aliases internally consistent.
- Preserve the pre-productization default under a rollback ref before merging; do not delete legacy history.
- Completed in this pass: a timed-out synchronous handler is not retried concurrently; documentation and regression coverage define the limitation.
- Next: keep external side effects idempotent and add durable checkpoints only if a real consumer requires them.
- Review priority: authorize license.
- Review priority: run CI/wheel/CLI and release only the narrow 0.1 boundary.

## Release candidate

- Build and install the wheel in a clean environment.
- Prove one real consumer and a versioned compatibility fixture.
- Publish only after package-name ownership, licensing, provenance, and rollback are recorded.

Current hardening backlog:

- Material BSL-to-MPL relicensing needs owner approval.
- No durable checkpoints, crash recovery, process isolation, idempotency keys, compensation, human pauses, or distributed workers; docs appropriately call these out, but they limit production use.
- No release/tag/package-index verification or external user evidence.
- Differentiation from small custom `asyncio` DAG runners is modest.

## Samsarix adoption

- Define a public API, event, schema, artifact, or deployment contract before connecting to Samsarix Unified.
- Add a consumer-owned contract fixture covering authentication, privacy, limits, errors, and version compatibility.
- Make one implementation canonical; remove or freeze duplicate behavior only after parity and rollback are proven.
- Record an owner, support level, compatibility window, and measurable adoption signal.

## Completion evidence

A milestone is complete only when its exact commit, commands and results, artifact digest, consumer or deployment, and rollback path are recorded in a pull request or release record. README claims must not exceed that evidence.
