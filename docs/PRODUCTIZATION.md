# Productization record

Last updated: 2026-07-28

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
- `LICENSE` is BSL 1.1 and names “Helix Licensing System,” while `LICENSING.md`
  describes an Apache/proprietary model.

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

**Helix Orchestration Workbench** is a local-first, provider-neutral Python library and
CLI for defining, validating, and running small dependency-aware workflows using
explicitly registered Python callables.

- Target user: a Python developer prototyping an agent/tool pipeline who wants a small
  transparent runtime without a hosted control plane or provider commitment.
- Concrete problem: catch invalid graph definitions early, execute ready work with
  bounded concurrency/retries/timeouts, propagate failure clearly, and obtain a
  machine-readable run report.
- Primary journey: install the wheel; generate a valid example; validate it; run it;
  inspect or persist the JSON result; then replace demonstration actions with trusted
  application handlers through the Python API.
- Independent reason to exist: a zero-runtime-dependency workflow primitive and format
  that does not require `helix-unified`, a model account, a database, or cloud services.
- Distribution: source distribution, universal Python wheel, and console script.
- Sustainability: keep the core free of hosted operating costs; paid integration,
  support, or dual-license offerings are plausible only after the owner resolves the
  license documents and validates demand.

The 0.1 release deliberately excludes built-in LLM/provider adapters, dynamic plugin
loading, arbitrary command/code execution, authentication, a web UI/API, cloud
deployment, durable checkpoints, distributed workers, subscriptions, and telemetry.

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
7. Keep the BSL file unchanged and point package metadata to it. Legal interpretation
   remains an owner decision.

Current ecosystem evidence informed the limits rather than expanding scope:

- LangGraph documents durable execution, persistence, streaming, and human-in-the-loop
  as runtime concerns; Helix 0.1 explicitly does not claim them:
  https://docs.langchain.com/oss/python/langgraph/overview
- Prefect treats task state, retries, timeouts, and concurrency as core workflow
  behavior; Helix implements a bounded local subset:
  https://docs.prefect.io/v3/concepts/tasks
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
- [ ] Owner: reconcile `LICENSE`, its Licensed Work name, and `LICENSING.md`.
- [ ] Validate Python 3.12 and 3.13 in CI; only 3.11 is available locally.

### P2

- Consolidate, repair, extract, or remove the excluded historical source subpackages.
- Add an opt-in durable checkpoint interface after idempotency semantics are designed.
- Add structured progress callbacks and explicit per-step cancellation reporting.
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
- [x] Standard security scan and adversarial final review.

## Release acceptance criteria

- A clean Python 3.11 environment can build and install the wheel.
- `helix-orchestration --version`, `init`, `validate`, and `run` reproduce the
  documented journey.
- Invalid documents, unknown actions, failed handlers, timeouts, retries, blocked
  dependants, existing output files, and cancellation have tested behavior.
- Ruff, strict MyPy, and the complete test suite pass.
- The wheel contains only the supported package boundary and no legacy subpackages.
- CI protects Python 3.11–3.13 and installs the built wheel.
- No locally actionable P0 remains.
- Documentation distinguishes implemented behavior, deliberate exclusions, legacy code,
  and owner-controlled gates.

## Completed work

- Rebuilt the packaging and console-script boundary around `helix_orchestration`.
- Added `spec.py`, `runtime.py`, `actions.py`, `cli.py`, and `__main__.py`.
- Replaced the stale examples and mock-centric tests with the supported vertical slice.
- Removed duplicate manifests, fake CLI code, nonexistent deployment configuration, and
  stale documentation.
- Added safe defaults, explicit overwrite controls, bounded errors, and a zero-network
  runtime.
- Added release CI, package smoke checks, and accurate user/developer documentation.

## Deferred work and rationale

The historical agent/coordination source remains in the repository but is excluded from
the wheel. Repairing or deleting roughly 80 large extraction files would create a broad
rewrite without strengthening the 0.1 journey. Their incomplete imports, syntax errors,
simulations, local path assumptions, dynamic execution helpers, and unvalidated
integrations are recorded as portfolio cleanup, not supported features.

Durable execution is also deferred. Correct persistence requires checkpoint identity,
atomic commit semantics, output compatibility, resume rules, idempotency, migration, and
retention design. A partial JSON state dump would be misleading.

## External and owner-controlled blockers

- Legal: clarify whether BSL 1.1 applies to this repository, correct the named Licensed
  Work if needed, and reconcile the Apache/proprietary claims in `LICENSING.md`.
- Publication: choose and authorize a package registry and confirm name ownership.
- CI: observe the first GitHub Actions run on Python 3.11, 3.12, and 3.13.
- Release: create owner-approved version/tag and publish artifacts; no push, tag, or
  publication is performed by this productization pass.

## Known risks

- Sync Python handlers run in threads. A timeout stops waiting but cannot forcibly stop
  arbitrary thread code; handlers must apply timeouts to their own blocking I/O.
- There is no durable checkpoint. A process crash loses in-memory run state.
- External side effects are not automatically idempotent.
- Handler output is measured after it is returned, so a malicious trusted handler can
  allocate memory before the 1 MiB serialization limit is applied.
- Historical excluded code can confuse source readers until the portfolio cleanup occurs.

## Final verification

Final verification ran from a fresh Python 3.11 virtual environment after
`python -m pip install -e ".[dev]"`:

- `python -m ruff check .`: pass;
- `python -m mypy`: pass, 6 source files;
- `python -m pytest`: 40 passed, 92.30% branch-aware coverage;
- `python -m bandit -q <all shipped modules>`: pass, no findings;
- `python -m build`: pass, both sdist and wheel built in isolation;
- a second empty virtual environment installed the wheel with `--no-deps` and completed
  `helix-orchestration init`, `validate`, and `run`: pass;
- wheel boundary inspection: 14 archive entries, the 6 supported package modules, no
  historical agent, coordination, or workflow subpackages, and zero runtime
  dependencies.

Artifact inventory for the verified build:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `helix_orchestration-0.1.0-py3-none-any.whl` | 19,408 | `6e2d923fb7e82a3ccf45a44716c68b0e961a8bf159c51b2e775bea31c9ca63fe` |
| `helix_orchestration-0.1.0.tar.gz` | 33,498 | `9e6926b06576583b64d83084c83961f41856b2ce6c41a66fe158ff16a6a3c3cb` |

## Release disposition

**Local release candidate with named owner gates.** The core product journey and local
engineering gates are implemented. Public release remains gated by license
clarification, package publication authorization/name confirmation, and observation of
the first multi-version CI run.
