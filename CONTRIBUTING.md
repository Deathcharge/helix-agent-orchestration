# Contributing

Samsarix Orchestration 0.1 accepts focused changes to the supported local
workflow library, compatibility namespace, CLI, tests, and documentation.

## Setup

```bash
git clone https://github.com/Deathcharge/samsarix-agent-orchestration.git
cd samsarix-agent-orchestration
python -m venv .venv
python -m pip install -e ".[dev]"
```

Activate the virtual environment using the command appropriate for your shell, then run:

```bash
python -m ruff check .
python -m mypy
python -m pytest
python -m bandit -q -r src
python -m build
python -m twine check dist/*
```

All six commands must pass. Tests enforce at least 85% branch-aware coverage. Add
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

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Unless stated
otherwise before acceptance, contributions are submitted under
[MPL-2.0](LICENSE), the same terms as the project. See
[LICENSING.md](LICENSING.md) for ownership and future dual-licensing implications.

Questions: contact@samsarix.com. Product support: support@samsarix.com.
