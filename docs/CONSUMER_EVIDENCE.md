# External consumer evidence

Evidence recorded 2026-08-01 for Samsarix Orchestration commit
`0dfc050cf9a4582c9fa8d34d74b1ca97d43c9005`.

## Consumer boundary

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

## Real workflow

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

## Measured result

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

## Scope and rollback

This proves compatibility and avoided repeated work across a real package boundary; it is
not evidence of third-party production adoption or distributed execution. The consumer is
an application-owned local workflow with a single-writer checkpoint store.

Rollback requires only stopping the consumer and, after retaining any necessary evidence,
removing its explicit output and checkpoint paths. Neither product is configured globally
or creates a remote resource. Dependency upgrades require changing the consumer's exact
pin and rerunning its complete contract suite.
