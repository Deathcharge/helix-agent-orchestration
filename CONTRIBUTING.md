# Contributing

Helix Orchestration 0.1 accepts focused changes to the supported local workflow
library, CLI, tests, and documentation. Historical subpackages excluded from the wheel
need a separate extraction or portfolio-cleanup proposal; do not couple broad repairs
there to a core runtime change.

## Setup

```bash
git clone https://github.com/Deathcharge/helix-agent-orchestration.git
cd helix-agent-orchestration
python -m venv .venv
python -m pip install -e ".[dev]"
```

Activate the virtual environment using the command appropriate for your shell, then run:

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m bandit -q src/helix_orchestration/__init__.py src/helix_orchestration/actions.py src/helix_orchestration/cli.py src/helix_orchestration/runtime.py src/helix_orchestration/spec.py
python -m build
```

All five commands must pass. Tests enforce at least 85% branch-aware coverage. Add
source-backed tests for success, validation, failure, timeout, retry, blocked, or
cancellation behavior that changes.

## Design expectations

- Keep runtime dependencies at zero unless a user-visible capability cannot reasonably
  be implemented with the standard library.
- Treat workflow files and run inputs as untrusted data.
- Never load Python modules, execute strings, or select subprocess commands from
  workflow JSON.
- Bound concurrency, retries, timeouts, queues, persistence, and output growth.
- Preserve stable JSON fields and CLI exit codes, or document a versioned migration.
- Do not add provider, cloud, database, authentication, billing, or telemetry features
  without an implemented end-to-end need.
- Documentation must describe commands and behavior verified in the same change.

## Pull requests

Keep commits focused and explain:

1. the user problem and primary path changed;
2. compatibility, security, privacy, and cost effects;
3. commands run and exact outcomes;
4. deferred work or external requirements.

Do not commit credentials, generated build artifacts, coverage output, virtual
environments, or private data. See [SECURITY.md](SECURITY.md) for the supported security
boundary and reporting guidance.

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Licensing terms
are controlled by the repository owner; contributors should review [LICENSE](LICENSE)
and the unresolved status in [docs/PRODUCTIZATION.md](docs/PRODUCTIZATION.md).
