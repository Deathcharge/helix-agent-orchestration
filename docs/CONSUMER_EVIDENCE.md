# Internal cross-package consumer evidence

The consumer repository is private as verified on 2026-08-31. Its source, PR, and CI links
below require owner-granted access. This is internal compatibility evidence, not public
reproducibility or independent adoption. Public users can run the standalone
[order recovery example](USE_CASES.md#local-automation-with-expensive-intermediate-artifacts)
without any sibling repository or package.

## Current candidate-wheel check (2026-08-31)

The current consumer `0.2.12` at `be56db8476454d6f241a5da7d5e846d92d1bcefb` still declares
Orchestration `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005`. To test compatibility with current
Orchestration, clean `git archive` snapshots were built into non-editable wheels:

| Component | Exact source commit |
| --- | --- |
| Candidate Orchestration | `93295fff0b9dbbac4a393ec4dc80a39a998b906d` |
| Consumer | `be56db8476454d6f241a5da7d5e846d92d1bcefb` |
| Integration Guard | `1aa711d89eaedcc396f0cd6eb416fb4253da3f5e` |
| Core | `2744d69eb58aef8412d15fbee9485b6d22eb30a5` |

Orchestration was built from the clean exact-commit checkout. The other three repositories
were read through `git archive`; their working trees, metadata pins, and remote state were
not changed. In a fresh Python 3.11.9 environment, all four local wheels were installed
with `--no-deps --no-index --find-links wheels`. This deliberately substitutes the
candidate for the declared Orchestration Git reference; it is **not** evidence that the
consumer adopted or resolves the newer commit through its ordinary install command.

`python -I -m pytest --import-mode=importlib` from the extracted consumer source passed all
38 tests with 91.03% branch-aware coverage, including the 14 redaction/recovery contract
tests. `python -m pip check` passed. All four package imports resolved inside the fresh
environment, and every installed Orchestration package file matched the candidate wheel's
bytes. The candidate wheel's local SHA-256 was
`5d60d1e8c5fde7917efbce65a394811f4f101c3289c7eff78baa0fc48aaf4b81`.
This hash identifies a local test artifact, not a published release or attestation.

The installed `samsarix-redaction-pipeline` executable was also run outside the checkout
against a synthetic local JSON fixture. `--fail-after-publish` exited `1` with `failed`;
the same paths and run ID with `--resume` exited `0` with `succeeded`, one restored step,
and `deduplicated: true`. The published file's SHA-256 was unchanged between invocations.

The suite covers lost-response recovery, source-identity rejection, conflicting outputs,
privacy assertions, and the consumer's Core/MCP contracts. It does not prove distributed
execution, third-party demand, package-index publication, or a consumer pin upgrade.
This candidate substitution was run locally on Windows Python 3.11 only; the older
consumer CI matrix below is separate historical evidence, not a run of this combination.

## Historical adopted-pin evidence

Evidence recorded 2026-08-01 for Samsarix Orchestration commit
`0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005`.

### Consumer boundary

[Samsarix Integration Examples](https://github.com/Deathcharge/samsarix-integration-examples)
is a separate repository and Python distribution. Its first consumer contract combines:

- `samsarix-orchestration` at exact merged commit
  `0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005`;
- `samsarix-integration-guard` at exact merged commit
  `1aa711d89eaedcc396f0cd6eb416fb4253da3f5e`;
- consumer merge commit `41ea9221f88c66d469c022075c9c9c49400a7961` from
  [consumer PR #1](https://github.com/Deathcharge/samsarix-integration-examples/pull/1).

The consumer installs both products through wheel metadata containing exact PEP 508 Git
references. A clean virtual environment's `direct_url.json` records matched both complete
commit IDs. The consumer does not use this repository's checkout, private modules, or a
copied runtime.

### Real workflow

The consumer reads bounded JSON, calls Integration Guard, and atomically publishes a
sanitized artifact through two Orchestration actions:

1. `redact` retains raw decoded data only in invocation memory and returns sanitized JSON;
2. `publish` uses its stable action idempotency key and refuses conflicting output.

Only sanitized data can become an action output or checkpoint. The workflow input contains
paths and a source SHA-256 digest, not source content. Lifecycle events use Orchestration's
payload-free version 1 schema.

The test deliberately creates the at-least-once crash window: publishing succeeds and the
action then reports a simulated lost response. Resume restores `redact`, invokes `publish`
with the same key, and accepts only the byte-identical existing artifact.

### Measured result

Local installed-CLI evidence:

| Observation | Result |
| --- | --- |
| First invocation | exit `1`, status `failed` after atomic publish |
| Resume | exit `0`, status `succeeded` |
| Restored steps | `1` |
| Redaction calls across both invocations | `1` |
| Resume publish result | `deduplicated: true` |
| Output bytes after resume | unchanged |
| Seeded bearer token, email, and API-key value | absent from checkpoint, events, report, and output |
| Changed source before resume | rejected by workflow-input identity |
| Different existing output | never replaced |

The consumer suite passed 14 tests with 98.68% branch-aware coverage, Ruff, strict MyPy,
Bandit, sdist/wheel builds, Twine validation, and a clean installed-wheel smoke test.
[GitHub Actions run 30694689949](https://github.com/Deathcharge/samsarix-integration-examples/actions/runs/30694689949)
passed on Python 3.11, 3.12, and 3.13.

Verified consumer artifacts:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `samsarix_integration_examples-0.1.0-py3-none-any.whl` | 13,687 | `b9a4dac3fa5570a3028a5069efdada8d639d0b177a2a1d8acced5c5db2771987` |
| `samsarix_integration_examples-0.1.0.tar.gz` | 18,844 | `80bed6342ffd19750c36a42043b388c18e9c3e33e1fcb988955e3bef3d5feb85` |

### Scope and rollback

This proves compatibility and avoided repeated work across a real package boundary; it is
not evidence of third-party production adoption or distributed execution. The consumer is
an application-owned local workflow with a single-writer checkpoint store.

Rollback requires only stopping the consumer and, after retaining any necessary evidence,
removing its explicit output and checkpoint paths. Neither product is configured globally
or creates a remote resource. Dependency upgrades require changing the consumer's exact
pin and rerunning its complete contract suite.
