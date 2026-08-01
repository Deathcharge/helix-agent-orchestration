# Real use cases and product position

Samsarix Orchestration is an **embedded reliability kernel** for applications that need
more structure than ad hoc `asyncio` tasks but do not want to operate a workflow server.
It is deliberately provider-neutral, zero-runtime-dependency, locally auditable, and
small enough to ship inside another Python product.

## Strong fits

### Costly API or AI enrichment pipelines

A document pipeline may extract text, call a paid model, validate structured output, and
publish a result. If publishing fails, checkpoint resume reuses the paid successful steps
instead of calling the provider again. The application owns credentials and provider
adapters; Samsarix owns graph, retry, bounds, identity, and recovery semantics.

### Import, synchronization, and release jobs

An application can model fetch, normalize, validate, write, and notify as explicit steps.
Stable idempotency keys let APIs or databases deduplicate writes when a response is lost.
Machine-readable reports provide evidence for support tooling without requiring a hosted
control plane. Ordered lifecycle events can feed application-owned logs, counters, or a
desktop progress view without including record payloads.

### Local automation with expensive intermediate artifacts

Build, media, research, or compliance tooling can persist successful JSON metadata and
resume a failed dependency branch. The engine remains embeddable in a desktop app, CLI,
CI job, or trusted worker process.

The runnable [order pipeline](../examples/resumable_order_pipeline.py) demonstrates a
write that succeeds before its response is lost. Resume uses the same idempotency key,
does not repeat completed pricing, and does not create a second receipt.

## Contract boundaries

- Delivery is at-least-once around external effects. Targets must support idempotency or
  handlers must deduplicate using `ActionContext.idempotency_key`.
- JSON checkpointing restores successful step outputs, not Python stack frames.
- The bundled file store is single-writer and local. It is not a lock service, queue, or
  distributed scheduler.
- Checkpoints contain plaintext inputs only as a digest, but successful outputs are stored
  in plaintext. Applications own encryption, access control, retention, and deletion.
- Registered actions are trusted code; checkpointing does not create a sandbox.

## When to choose something else

Choose a durable execution platform when work must survive worker replacement across a
cluster, wait for months, coordinate distributed deployments, or provide a hosted control
plane. Current products make those trade-offs explicit:

- [Temporal](https://docs.temporal.io/) targets durable distributed application execution.
- [Inngest durable workflows](https://www.inngest.com/docs/patterns/durable) persist and
  independently retry hosted/background steps.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
  supports stateful agents, human intervention, and time-travel workflows.
- [Prefect tasks](https://docs.prefect.io/v3/concepts/tasks) add caching, retries,
  concurrency, transactions, and orchestration services.
- [Dagster](https://docs.dagster.io/) is asset-oriented data orchestration with a broader
  operational platform.

Samsarix should not imitate those platforms feature for feature. Its competitive advantage
is a narrow, inspectable contract for embedded workflows with no mandatory service,
provider, database, account, or runtime dependency.

## Next evidence-driven milestones

1. Validate lifecycle events in a separate package consumer and desktop progress view.
2. A versioned approval/interrupt primitive built on the checkpoint contract.
3. A SQLite store with transactional single-host concurrency and run inspection.
4. A published package, signed provenance, compatibility fixtures, and one external
   consumer that demonstrates measurable avoided work after resume.

Research reviewed 2026-08-01. Product claims in the README remain limited to behavior
verified in this repository.
