# Productization record

Last updated: 2026-08-01

## Repository assessment

The repository's apparent original purpose was a Python framework and CLI for a named
network of Helix agents. The baseline instead contained three overlapping product
shapes: a large Helix-specific research extraction, generic in-process workflow and
monitoring simulations, and packaging/deployment claims for a service that did not
exist. The clean baseline at commit `57751075f90d94d8d1be0c351a6a962f599c3312`
contained 126 non-Git files and no GitHub Actions workflow.

What worked at baseline:

- a source-tree-only Click CLI displayed help;
- several generic workflow, messaging, monitoring, and resilience modules imported when
  the root package import was bypassed;
- 55 tests could be collected before package import errors, but the orchestration and
  integration suites primarily tested mocks defined inside the tests;
- extensive historical agent and coordination code recorded the project's intent.

What was incomplete or misleading:

- `pyproject.toml` was invalid TOML, blocking installation, tests, lint, typing, and
  builds;
- the package manifest included `helix_orchestration` but the console script targeted
  an excluded top-level `helix_agent_orchestration` package;
- six source files had syntax errors and several core modules referenced commented-out
  imports or private Helix paths;
- the CLI returned fabricated agents, health, uptime, metrics, and workflow success;
- the README claimed production readiness, MIT licensing, CI, and documents that were
  absent or contradicted the repository;
- Docker, Compose, Railway, and deployment documentation targeted nonexistent API/server
  entry points;
- runtime dependency lists disagreed and pulled in databases, web servers, and networking
  that the supported journey did not need;
- `LICENSE` was BSL 1.1 and named “Helix Licensing System,” while `LICENSING.md`
  described an Apache/proprietary model.

## Baseline command results

All commands below were run on Python 3.11.9 before implementation.

| Command | Exit | Actual result |
| --- | ---: | --- |
| `python -c "... tomllib ..."` | 1 | `TOMLDecodeError` at line 13, column 5. |
| `python -m pytest` | 1 | Coverage could not parse `pyproject.toml`. |
| `python -m ruff check .` | 1 | Ruff could not parse `pyproject.toml`. |
| `python -m black --check .` | 1 | Black could not parse `pyproject.toml`. |
| `python -m mypy src` | 1 | Invalid TOML plus a syntax error in `agents/__init__.py`. |
| `python -m build` | 1 | Build backend rejected invalid TOML. |
| `python -m compileall -q src helix_agent_orchestration` | 1 | Six syntax errors. |
| `python -m pytest -p no:cov -o addopts=` | 1 | 55 items plus 3 collection errors. |
| `python -m helix_agent_orchestration --help` | 0 | Help worked only from the repository checkout. |
| `python -m bandit -r src -q` | 1 | Bandit crashed rendering Unicode to the Windows console. |
| `python -m pip_audit` | 1 | Audited the unrelated global environment, so its 103 advisories were not attributed to this project. |

## Chosen product

**Samsarix Orchestration** is a local-first, provider-neutral Python library and
CLI for defining, validating, and running small dependency-aware workflows using
explicitly registered Python callables.

- Target user: a Python developer prototyping an agent/tool pipeline who wants a small
  transparent runtime without a hosted control plane or provider commitment.
- Concrete problem: catch invalid graph definitions early, execute ready work with
  bounded concurrency/retries/timeouts, stop sensitive actions behind durable review
  gates, propagate failure clearly, and obtain a machine-readable run report.
- Primary journey: install the wheel; generate a valid example; validate it; run it;
  inspect or persist the JSON result; then replace demonstration actions with trusted
  application handlers through the Python API.
- Independent reason to exist: a zero-runtime-dependency workflow primitive and format
  that does not require `helix-unified`, a model account, a database, or cloud services.
- Distribution: source distribution, universal Python wheel, and console script.
- Sustainability: keep the core free of hosted operating costs; paid integration and
  support remain possible without limiting community use under MPL-2.0. Any future
  dual-license model needs contributor-rights planning before accepting outside work.

The 0.1 release deliberately excludes built-in LLM/provider adapters, dynamic plugin
loading, arbitrary command/code execution, reviewer authentication or authorization, a
web UI/API, cloud deployment, distributed workers, subscriptions, and telemetry. Bounded
local checkpoints and static pre-action approvals are opt-in; they do not provide
distributed durable execution or continuation from inside a running handler.

## Product and architecture decisions

1. Reduce the public package to six root modules and exclude historical subpackages
   from the wheel rather than pretending they are supported.
2. Use a versioned JSON DAG with a 1 MiB document bound, 256-step limit, strict ids,
   complete validation issues, and explicit numeric bounds.
3. Require host applications to register trusted callables. Workflow JSON cannot import
   modules, choose executable paths, or contain code.
4. Run sync handlers in worker threads and async handlers on the caller's event loop;
   bound concurrency with a semaphore and each attempt with `asyncio.wait_for`.
5. Return ordered JSON terminal states and propagate cancellation. Do not fabricate live
   agent, health, consensus, cost, or uptime data.
6. Use only the standard library at runtime. Python library consumers own their lock;
   bounded development ranges live in one `pyproject.toml`.
7. License the supported project under MPL-2.0, retain copyright and trademark notices,
   and keep the Samsarix brand policy separate from source-code permissions.
8. Introduce approval gates only in strict workflow schema version 2. Bind each request to
   the run, workflow, input, gated step, and dependency outputs; persist a decision before
   starting its handler; and leave reviewer identity enforcement to the embedding system.

Current ecosystem evidence informed the limits rather than expanding scope:

- LangGraph documents persistence and a stable thread identity as requirements for
  resumable interrupts. Samsarix adopts the durable-state principle for a narrower static
  pre-action gate, without claiming stack continuation or dynamic in-handler interrupts:
  https://docs.langchain.com/oss/python/langgraph/interrupts
- Prefect treats task state, retries, timeouts, and concurrency as core workflow
  behavior; Samsarix Orchestration implements a bounded local subset:
  https://docs.prefect.io/v3/concepts/tasks
- Prefect's interactive workflows distinguish pausing from suspending and accept typed
  operator input; this informed Samsarix's explicit paused result and bounded decision
  contract: https://docs.prefect.io/v3/advanced/interactive
- Temporal's Python SDK exposes asynchronous signals and validated request/response
  updates; this informed the decision to keep approval requests addressable and to reject
  stale or divergent decisions: https://github.com/temporalio/sdk-python
- The Python Packaging User Guide recommends `pyproject.toml`, `[project.scripts]`,
  and a `src` layout that tests the installed package boundary:
  https://packaging.python.org/en/latest/guides/writing-pyproject-toml/

## Prioritized findings

### P0

- [x] Repair invalid build metadata and align the console entry point with the wheel.
- [x] Replace fabricated CLI output with a complete real workflow journey.
- [x] Make validation, execution, tests, lint, strict typing, and builds runnable.
- [x] Remove deployment claims and configs for the nonexistent server.
- [x] Ensure the supported distribution has no private Helix runtime dependency.

### P1

- [x] Replace mock-only core tests with source-backed unit and CLI integration tests.
- [x] Bound untrusted JSON, step count, concurrency, timeouts, retries, and outputs.
- [x] Make file replacement explicit and forced writes atomic.
- [x] Add CI across supported Python versions with an installed-wheel smoke test.
- [x] Rewrite user, architecture, format, security, and contribution documentation.
- [x] Adopt MPL-2.0 and reconcile `LICENSE`, package metadata, and legal notices.
- [ ] Validate Python 3.12 and 3.13 in CI; only 3.11 is available locally.

### P2

- [x] Remove excluded historical source subpackages while preserving them in Git history.
- [x] Add bounded opt-in checkpoints with exact identity and stable idempotency keys.
- [x] Add transactional same-host SQLite checkpoints and privacy-safe run operations.
- [x] Add ordered structured progress callbacks and explicit cancellation events.
- [x] Add durable, state-bound pre-action approval and rejection gates.
- Decide whether the package name is available and intended for PyPI.
- Add performance targets only after real usage workloads exist.

## Implementation checklist

- [x] Versioned workflow definition and full validation issue collection.
- [x] Dependency-aware async runner with bounded concurrency.
- [x] Timeout, retry, failure, blocked, cancellation, and output-bound behavior.
- [x] Safe provider-free CLI onboarding, validation, execution, and report persistence.
- [x] Application-defined Python handler example.
- [x] Modern package metadata with no runtime dependencies.
- [x] Source-backed tests and branch-aware coverage threshold.
- [x] Ruff and strict MyPy quality gates.
- [x] CI and wheel-install smoke verification.
- [x] Accurate README, architecture, workflow format, and this living record.
- [x] Concurrent multi-run checkpoint persistence with corruption and lock-contention tests.
- [x] Strict schema-v2 approval gates with durable decisions, a global ready-batch barrier,
  rejection propagation, event privacy, and concurrent-decision tests.
- [x] Standard security scan and adversarial final review.

## Release acceptance criteria

- A clean Python 3.11 environment can build and install the wheel.
- `samsarix-orchestration --version`, `init`, `validate`, and `run` reproduce the
  documented journey.
- Invalid documents, unknown actions, failed handlers, timeouts, retries, blocked
  dependants, approval/rejection decisions, existing output files, and cancellation have
  tested behavior.
- Ruff, strict MyPy, and the complete test suite pass.
- The wheel contains the supported package and thin compatibility namespace, with no
  historical subpackages.
- CI protects Python 3.11–3.13 and installs the built wheel.
- No locally actionable P0 remains.
- Documentation distinguishes implemented behavior, deliberate exclusions, legacy code,
  and owner-controlled gates.

## Completed work

- Rebuilt the packaging and console-script boundary around `samsarix_orchestration`.
- Added `spec.py`, `runtime.py`, `actions.py`, `cli.py`, and `__main__.py`.
- Added temporary `helix_orchestration` import and CLI compatibility for the 0.1 line.
- Replaced the stale examples and mock-centric tests with the supported vertical slice.
- Removed duplicate manifests, fake CLI code, nonexistent deployment configuration, and
  stale documentation.
- Added safe defaults, explicit overwrite controls, bounded errors, and a zero-network
  runtime.
- Added release CI, package smoke checks, and accurate user/developer documentation.
- Added a generated approval workflow, CLI and Python decision APIs, durable SQLite/JSON
  approval state, privacy-safe inspection, and installed-wheel smoke coverage.
- Adopted MPL-2.0 under Samsarix LLC ownership and added notice, migration, and trademark
  documentation.

## Deferred work and rationale

The historical agent/coordination extraction was removed from the working tree after the
supported product boundary was established. It remains recoverable from commit
`6e10c5bd515e61245b289c18c321e0b24664403b`; none of it was advertised or shipped as a
supported Samsarix feature.

Distributed durable execution remains deferred. The local checkpoint contract now covers
identity, atomic file replacement, transactional same-host SQLite writes, output
compatibility, resume rules, safe inspection, explicit deletion, and idempotency keys.
Cross-host coordination, retention automation, and exactly-once effects are not claimed.

Approval gates are intentionally static and pre-action. Dynamic pauses from inside a
handler, editable action arguments, delegated reviewer policy, quorum decisions, expiry,
and a hosted approval inbox remain deferred until real integrations establish their
requirements. The request identifier is an operational correlation value, not a bearer
credential; callers must authenticate and authorize reviewers before constructing a
decision.

## External package consumer

The separately installable `samsarix-integration-examples` distribution pins this package
at merged commit `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005`. Consumer merge
`41ea9221f88c66d469c022075c9c9c49400a7961` proves a bounded redaction/publish workflow,
one restored step, one redaction call across failure and resume, byte-identical idempotent
publishing, payload-free lifecycle events, and source-identity rejection. Its Python
3.11–3.13 CI and clean-wheel installation are recorded in
[the consumer evidence](CONSUMER_EVIDENCE.md).

This closes the internal cross-package compatibility gate. It does not close publication,
release provenance, or third-party adoption gates.

## External and owner-controlled blockers

- Publication: choose and authorize a package registry and confirm name ownership.
- Release: create an owner-approved version/tag and publish artifacts after CI passes.

## Known risks

- Sync Python handlers run in threads. A timeout stops waiting but cannot forcibly stop
  arbitrary thread code; handlers must apply timeouts to their own blocking I/O. The
  runner does not retry a timed-out sync handler because that could overlap side effects.
- A crash after an external effect but before checkpoint commit can repeat that effect;
  handlers must apply the stable idempotency key at the destination.
- Handler output is measured after it is returned, so a malicious trusted handler can
  allocate memory before the 1 MiB serialization limit is applied.
- The old distribution/import/CLI aliases intentionally remain visible during the 0.1
  compatibility window and should be removed only in a versioned breaking release.

## Final verification

The release-candidate foundation was verified from a fresh Python 3.11 virtual
environment. The durable-checkpoint and lifecycle-event milestones were then verified
locally on Python 3.14. The SQLite and approval-gate milestones were fully verified and
packaged with Python 3.11; the repository CI matrix remains authoritative for Python 3.11
through 3.13:

- `python -m ruff check .`: pass;
- `python -m mypy`: pass, 18 source files across the primary and compatibility packages;
- `python -m pytest`: 118 passed, 88.28% branch-aware coverage;
- `python -m bandit -q -r src`: pass, no findings;
- `python -m build` and `python -m twine check dist/*`: pass for sdist and wheel;
- a second empty environment installed the wheel with `--no-deps`; both command names,
  both `python -m` entry points, SQLite `run`, `runs list`, privacy-safe `runs show`, and
  the pause/approve/resume journey passed;
- eight separate PowerShell job processes committed distinct runs to one installed-wheel
  SQLite database without loss;
- wheel boundary inspection: 28 archive entries, 10 primary package entries, 10 thin
  compatibility entries, three legal files, no historical subpackages, and zero
  unconditional runtime dependencies.

Artifact inventory for the verified build:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_orchestration-0.1.0-py3-none-any.whl` | built | recorded in the external release attestation¹ |
| `samsarix_orchestration-0.1.0.tar.gz` | built | record in the external release attestation¹ |

¹ Reproducible verification records the final wheel and source-archive checksums outside
the source tree. Embedding either checksum here would make this document stale whenever
the artifact is rebuilt, and the document itself is included in the source archive.

## Release disposition

**Branded local release candidate with named owner gates.** The core product journey,
durable pre-action review gate, MPL-2.0 licensing, Samsarix ownership, compatibility
boundary, and local engineering gates are implemented. Registry publication remains
gated by package-name confirmation, release provenance, and an explicit owner publication
decision.
