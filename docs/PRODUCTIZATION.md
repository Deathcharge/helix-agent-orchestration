# Productization record

Last updated: 2026-08-31

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

1. Keep a small explicit public module set and exclude historical subpackages from the
   wheel rather than pretending they are supported.
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
9. Expose deterministic static plans as text, stable JSON, and offline Mermaid source.
   Planning validates definitions but never imports handlers, reads run input, or chooses
   a renderer.
10. Introduce compensation only in strict workflow schema version 3. Persist the reverse
    phase before effects, execute successful steps in reverse dependency waves, retain
    completed compensation across resume, and report rollback separately from business
    workflow success.
11. Offer process execution only as an application-registered direct-executable adapter.
    Use a bounded versioned JSON protocol, no shell, explicit environment policy, and
    terminate-then-kill cancellation; do not label trusted-process isolation a sandbox.
12. Publish only from an immutable version-matched GitHub release through a protected
    environment and PyPI Trusted Publishing. Attest the built distributions, attach their
    checksums, and never store a long-lived package-index token.

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
- LangGraph and Prefect expose graph visualization as a core debugging affordance.
  Samsarix implements the zero-network source/metadata subset without a rendering
  dependency: https://docs.langchain.com/oss/python/langgraph/use-graph-api#visualize-your-graph
  and https://docs.prefect.io/v3/api-ref/python/prefect-flows#prefect.flows.Flow.visualize
- AWS documents orchestrated Sagas as compensating successful transactions in reverse
  after a later failure, and Prefect distinguishes rollback hooks from ordinary failure
  hooks. Samsarix implements the bounded embedded form with explicit idempotent handlers:
  https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html
  and https://docs.prefect.io/v3/advanced/transactions
- Python documents bounded async subprocess streams and direct exec APIs, while Prefect
  explicitly distinguishes uninterruptible thread-pool timeouts from process execution.
  Samsarix implements a smaller zero-service JSON adapter for trusted local tools:
  https://docs.python.org/3/library/asyncio-subprocess.html and
  https://docs.prefect.io/v3/how-to-guides/workflows/write-and-run#task-timeout-behavior
- The Python Packaging User Guide recommends `pyproject.toml`, `[project.scripts]`,
  and a `src` layout that tests the installed package boundary:
  https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
- PyPA recommends GitHub OIDC Trusted Publishing instead of long-lived PyPI tokens, and
  GitHub artifact attestations bind release files to their source workflow and commit. The
  release path implements both controls behind a protected environment:
  https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/
  and https://docs.github.com/en/actions/concepts/security/artifact-attestations

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
- [x] Validate Python 3.12 and 3.13 in CI; the post-merge matrix at `93295ff` passed,
  including the installed-wheel/source-archive test gate.
- [x] Make the public recovery example reject conflicting receipts and publish complete
  content without overwriting an existing destination; add failure/race/CLI regressions.

### P2

- [x] Remove excluded historical source subpackages while preserving them in Git history.
- [x] Add bounded opt-in checkpoints with exact identity and stable idempotency keys.
- [x] Add transactional same-host SQLite checkpoints and privacy-safe run operations.
- [x] Add ordered structured progress callbacks and explicit cancellation events.
- [x] Add durable, state-bound pre-action approval and rejection gates.
- [x] Add offline dependency plans and Mermaid source for review and downstream UIs.
- [x] Add durable schema-v3 compensating actions with reverse dependency execution.
- [x] Add bounded direct subprocess actions with reliable timeout termination.
- [x] Add a protected, version-gated release workflow with provenance attestations and
  secretless PyPI publishing.
- [x] Select PyPI and verify that the public normalized-name endpoint returned `404` on
  2026-08-10; the first trusted upload remains the authoritative name claim.
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
- [x] Stable static plan schema with deterministic waves, graph metadata, and prompt-free
  Mermaid export.
- [x] Durable compensating phase, separate handler registry and outcome, retry/resume,
  cancellation events, privacy-safe inspection, and installed CLI Saga journey.
- [x] Shell-free absolute-command subprocess adapter with JSON protocol, stream and
  environment bounds, cancellation cleanup, forward/compensation support, and example.
- [x] Release automation with immutable action pins, exact version-tag validation,
  distribution checksums, Sigstore/GitHub provenance, and PyPI OIDC.
- [x] Standard security scan and adversarial final review.

## Release acceptance criteria

- A clean Python 3.11 environment can build and install the wheel.
- `samsarix-orchestration --version`, `init`, `validate`, `plan`, and `run` reproduce the
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
- Added deterministic Python and CLI preflight plans with text, JSON, and Mermaid formats.
- Added schema-v3 compensation policies, durable reverse execution, lifecycle events,
  planning metadata, and a provider-free `init --saga` failure/recovery demonstration.
- Added a bounded subprocess JSON adapter and provider-free isolated-worker pipeline for
  interruptible trusted command-line tools.
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

Compensation is semantic and at least once. It cannot erase observation of an original
effect or make an irreversible operation transactional. A reverse handler may complete
before its checkpoint is committed, so it must deduplicate the stable compensation key.

Approval gates are intentionally static and pre-action. Dynamic pauses from inside a
handler, editable action arguments, delegated reviewer policy, quorum decisions, expiry,
and a hosted approval inbox remain deferred until real integrations establish their
requirements. The request identifier is an operational correlation value, not a bearer
credential; callers must authenticate and authorize reviewers before constructing a
decision.

## External package consumer

The separately installable, owner-controlled private `samsarix-integration-examples`
distribution pins this package
at merged commit `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005`. Consumer merge
`41ea9221f88c66d469c022075c9c9c49400a7961` proves a bounded redaction/publish workflow,
one restored step, one redaction call across failure and resume, byte-identical idempotent
publishing, payload-free lifecycle events, and source-identity rejection. Its Python
3.11–3.13 CI and clean-wheel installation are recorded in
[the consumer evidence](CONSUMER_EVIDENCE.md).

The current consumer `0.2.12` additionally passed 38 tests against an installed candidate
wheel built from Orchestration `93295ff` on Windows Python 3.11. Its older declared pin was
deliberately overridden for this compatibility check, not upgraded. Private source/CI
links are not a public reproducibility path; the standalone order example requires no
sibling package or credentials.

This supplies internal cross-package compatibility evidence. It does not close publication,
release provenance, consumer adoption of the candidate, or third-party adoption gates.

## External and owner-controlled blockers

- Publication: register the documented pending PyPI Trusted Publisher; the public project
  endpoint returned `404` on 2026-08-10 but only the first upload reserves the name.
- Release: create and publish the first immutable version tag after the publisher identity
  and protected `pypi` environment are confirmed.

## Known risks

- Sync Python handlers run in threads. A timeout stops waiting but cannot forcibly stop
  arbitrary thread code; handlers must apply timeouts to their own blocking I/O. The
  runner does not retry a timed-out sync handler because that could overlap side effects.
  Applications can opt into the subprocess adapter for direct-child termination, but it
  is not a sandbox and does not own arbitrary descendant process trees.
- A crash after an external effect but before checkpoint commit can repeat that effect;
  handlers must apply the stable idempotency key at the destination.
- A compensation can fail or be only partially meaningful. Earlier prerequisites remain
  untouched after a reverse-wave failure, but operators still own domain reconciliation.
- Handler output is measured after it is returned, so a malicious trusted handler can
  allocate memory before the 1 MiB serialization limit is applied.
- The old distribution/import/CLI aliases intentionally remain visible during the 0.1
  compatibility window and should be removed only in a versioned breaking release.

## Final verification

### Public recovery example and current consumer (2026-08-31)

A regression against `93295ff` reproduced a real example defect: after a lost publish
response, replacing its receipt with different valid JSON made resume report success
with the wrong order. The example also wrote directly to the final path, exposing partial
content if interrupted. The destination now stages and flushes bounded content, publishes
with a no-replacement hard link, and accepts existing content only when it matches the
expected receipt (including the historical CRLF newline). There is no overwrite fallback.

Twelve targeted tests pass for complete recovery, conflict refusal, staging cleanup on
flush/link failure, competing publishers, historical receipts, bounded and nonregular
destinations, and actual CLI failure/resume commands. Strict MyPy and Ruff pass for the
changed example. Python's documented [hard-link](https://docs.python.org/3/library/os.html#os.link)
and [flush/fsync](https://docs.python.org/3/library/os.html#os.fsync) contracts inform the
implementation. Filesystem support, trusted-directory ownership, JSON-store single-writer
requirements, power-loss limits, and possible interrupted staging-file cleanup are explicit
in the use-case guide. The runtime API and dependency boundary are unchanged.

The complete local suite passed 204 tests with 88.99% branch-aware runtime coverage on
Python 3.11.9. Ruff, strict MyPy for shipped modules and the changed example, and Bandit
for both shipped modules and the example passed. Formatting checks passed for both new
or modified Python files.
The rebuilt sdist/wheel passed Twine and the distribution round-trip: all 204 shipped
tests passed outside the checkout against the installed wheel with 88.90% coverage, and
both namespace CLI version commands passed.

The separate installed-wheel consumer check passed 38 tests with 91.03% coverage; exact
versions, substituted-pin scope, and private-access limits are in
[the consumer evidence](CONSUMER_EVIDENCE.md).

### Distribution-path audit (2026-08-31)

The prior green checkout did not prove the distribution path. An exact `95f2d30` source
archive reproduced a failing `test_repository_has_structured_contribution_intake` because
the manifest omitted CODEOWNERS and issue/PR templates. The checkout-free release asset
job also lacked `GH_REPO`; GitHub CLI repository discovery failed in an empty directory.
These are release-engineering defects, not external-account blockers.

The manifest now includes the contribution files, scripts, and tests. Both CI and release
run `python scripts/verify_distributions.py dist`: exact artifact inventory, complete source
payload, strict wheel boundary, fresh venv installation, installed-import provenance, and
the shipped test suite outside the checkout. Release upload explicitly binds `GH_REPO`.
Release verification runs on a separate read-only runner after build attestation and before
asset attachment; ranged test dependencies have no signing or publication credentials.
The attachment and publication jobs download the original build artifact by immutable ID,
never by reusable name or from the test runner. This isolates the test dependency trust
boundary; it does not eliminate supply-chain risk in build tools or third-party actions.
The verifier never publishes and is for locally built artifacts only; its development-tool
installation requires package-index access. Source and runtime APIs are unchanged.

The local checkout suite passed 192 tests with 88.96% branch-aware coverage on Python 3.11.9;
the same 192 tests passed against the installed wheel with 88.93% coverage (also counting
the module entry point). Both module CLI version commands passed. Ruff, strict MyPy (22
shipped source files plus a separate strict check of the verifier), Bandit, build, Twine,
and Actionlint 1.7.12 passed. Remote CI evidence is recorded with the pull request and
Actions runs. GitHub CLI repository selection was verified read-only outside a checkout;
actual release upload, attestation, and PyPI publication remain unexecuted.

### Earlier milestone evidence

The release-candidate foundation was verified from a fresh Python 3.11 virtual
environment. The durable-checkpoint and lifecycle-event milestones were then verified
locally on Python 3.14. The SQLite, approval-gate, offline-planning, and compensation milestones were
fully verified and packaged with Python 3.11; the repository CI matrix remains
authoritative for Python 3.11 through 3.13:

- `python -m ruff check .`: pass;
- `python -m mypy`: pass, 22 source files across the primary and compatibility packages;
- `python -m pytest`: 181 passed, 88.96% branch-aware coverage;
- `python -m bandit -q -r src`: pass, no findings;
- `python -m build` and `python -m twine check dist/*`: pass for sdist and wheel;
- a second empty environment installed the wheel with `--no-deps`; both command names,
  both `python -m` entry points, SQLite `run`, `runs list`, privacy-safe `runs show`, and
  the pause/approve/resume journey passed;
- a third empty environment installed the wheel with `--no-deps` and produced verified
  JSON and Mermaid plans through the installed console script and compatibility API;
- a fourth empty Python 3.11 environment installed the exact wheel with `--no-deps`,
  imported both subprocess compatibility APIs, and ran the two-process JSON pipeline;
- eight separate PowerShell job processes committed distinct runs to one installed-wheel
  SQLite database without loss;
- wheel boundary inspection: 32 archive entries, 12 primary package entries, 12 thin
  compatibility entries, three legal files, no historical subpackages, and zero
  unconditional runtime dependencies.

The verified artifact types are `samsarix_orchestration-0.1.0-py3-none-any.whl` and
`samsarix_orchestration-0.1.0.tar.gz`. No public release attestation exists yet. Record
checksums for the exact published bytes in the release assets and verification record,
not in this source document: it is itself included in the source archive, and a rebuild
can produce different bytes. Local build/test success does not prove signed provenance
or publication.

## Release disposition

**Branded local release candidate with named owner gates.** The core product journey,
offline preflight planning, durable pre-action review gate, MPL-2.0 licensing, Samsarix
ownership, compatibility boundary, and local engineering gates are implemented. Registry
publication remains gated by the one-time PyPI publisher registration and first immutable
release. The repository-side provenance, approval, checksum, and secretless upload path is
implemented in `.github/workflows/release.yml`.
