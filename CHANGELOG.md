# Changelog

All notable changes to the supported Helix Orchestration package are recorded here.

## 0.1.0 - 2026-07-28

Initial honest standalone release candidate.

### Added

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
- Reduced the supported distribution to `helix_orchestration` root modules with no
  runtime dependencies or private Helix services.

### Removed from the supported product

- Fabricated agent, health, uptime, metric, and workflow CLI output.
- Nonexistent API/server deployment configuration and documentation.
- Conflicting requirements files, legacy setup metadata, stale examples, and mock-only
  core tests.

Historical agent and coordination sources remain in the repository as excluded research
evidence; they are not present in the 0.1 wheel.
