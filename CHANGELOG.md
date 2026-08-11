# Changelog

All notable changes to the supported Samsarix Orchestration package are recorded here.

## 0.1.0 - 2026-07-28

Initial honest standalone release candidate.

### Added

- Opt-in checkpoint stores, exact workflow/input identity validation, and resumable runs.
- Transactional same-host SQLite checkpoints with bounded WAL concurrency, monotonic
  same-run updates, privacy-safe run inspection, and confirmation-gated deletion.
- Strict schema-v2 pre-action approvals with durable state-bound decisions, paused and
  rejected results, distinct pause/rejection exit codes, CLI approve/reject controls, and
  privacy-minimized lifecycle events.
- Stable action idempotency keys and a runnable side-effect recovery example.
- Ordered schema-versioned lifecycle events, explicit observer failure semantics, and
  privacy-minimized CLI JSON Lines progress output.
- Side-effect-free workflow plans with dependency waves, approval-barrier markers, stable
  JSON metadata, and offline Mermaid source export.
- Strict schema-v3 compensating actions with reverse dependency waves, independent retry
  policy, durable phase recovery, separate outcomes, lifecycle events, and a runnable
  provider-free Saga rollback example.
- Bounded subprocess actions with an absolute direct-exec command contract, versioned JSON
  protocol, explicit environment inheritance, stream ceilings, cancellation termination,
  Saga compatibility, and a runnable isolated-worker example.
- A protected GitHub release workflow with exact version-tag validation, immutable action
  pins, wheel-boundary checks, SHA-256 release assets, provenance attestations, and secretless
  PyPI Trusted Publishing.
- Exact-pin external consumer evidence for resumable, idempotent redaction and publishing.
- Samsarix distribution, import namespace, CLI, company contacts, and `0.1.x`
  compatibility aliases for the historical Helix names.
- MPL-2.0 licensing, ownership notice, trademark guidance, and rename migration guide.
- Versioned JSON workflow definitions and complete graph validation.
- Bounded async DAG runner for registered sync or async Python actions.
- Concurrency, timeout, retry, fail-fast, cancellation, and JSON output controls.
- Provider-free `init`, `validate`, `run`, and `actions` CLI commands.
- Structured terminal run reports and explicit atomic output replacement.
- Source-backed tests, strict typing, linting, CI, and installed-wheel verification.
- Accurate workflow format, architecture, security, and productization documentation.

### Changed

- Made first-use SQLite WAL initialization retry transient lock contention so concurrent
  store instances can safely create and use the same new checkpoint database.
- Hardened Saga restoration by reapplying output-size bounds to compensations and by
  making terminal forward failures durable only with the compensation phase transition.
- Updated immutable GitHub Actions pins to Node-24-native checkout and Python setup releases.
- Reset the package maturity from an unsupported “production stable” 1.0 claim to an
  explicit 0.1 alpha release candidate.
- Reduced the supported distribution to the typed `samsarix_orchestration` runtime
  plus small compatibility aliases, with no runtime dependencies or private services.
- Removed the unsupported historical research forest from the active tree; revision
  `6e10c5b` preserves it in Git history.

### Removed from the supported product

- Fabricated agent, health, uptime, metric, and workflow CLI output.
- Nonexistent API/server deployment configuration and documentation.
- Conflicting requirements files, legacy setup metadata, stale examples, and mock-only
  core tests.

Historical agent and coordination sources remain available in Git revision `6e10c5b`;
they are not present in the active tree or the 0.1 wheel.
