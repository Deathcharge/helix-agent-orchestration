# Changelog

All notable changes to the supported Samsarix Orchestration package are recorded here.

## 0.1.0 - 2026-07-28

Initial honest standalone release candidate.

### Added

- Opt-in checkpoint stores, exact workflow/input identity validation, and resumable runs.
- Stable action idempotency keys and a runnable side-effect recovery example.
- Ordered schema-versioned lifecycle events, explicit observer failure semantics, and
  privacy-minimized CLI JSON Lines progress output.
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
