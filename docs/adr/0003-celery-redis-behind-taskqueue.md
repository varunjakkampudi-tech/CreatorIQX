# ADR 0003: Run background work on Celery and Redis behind a TaskQueue port

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §5 (Background jobs), §6 (Queue and retries, Workflows, Backpressure), §7 (Execution), §15 (Phase 0 depth rule), §18 |

## Context

CreatorIQX needs background work: YouTube ingestion and sync, transcription, the outbox relay, AI task leases and later media rendering. Jobs must retry safely, never run a public action twice, and stay visible when they fail. The spec fixes Redis and Celery and forbids external workflow engines. Business code should not depend on Celery directly, so tests stay fast and the engine stays replaceable.

## Decision

1. Application code depends only on a **`TaskQueue` port** in the `jobs` module, roughly:

```python
class TaskQueue(Protocol):
    def enqueue(self, job: JobRequest) -> JobHandle: ...
```

where `JobRequest` carries the job name, a validated payload, the workspace id, a correlation id and an optional idempotency key.

2. A **Celery adapter** implements the port with Redis as broker. Defaults: `acks_late=True`, `task_reject_on_worker_lost=True`, exponential backoff with jitter, a bounded `max_retries`, per-task time limits.
3. **Jobs must be idempotent.** Every job either is naturally idempotent or checks an idempotency key before side effects. Delivery is at-least-once.
4. **Domain workflows sit above jobs** (spec §6): `Workflow` and `WorkflowStep` records in Postgres hold business state, including pauses for user input. Celery only executes steps; Postgres, not the broker, is the source of truth.
5. Jobs carry tenant context: the worker sets the same RLS context (ADR 0002) from the job's workspace before touching data, and propagates the correlation id into logs.
6. **Phase 0 depth:** the port, the adapter and one working job (`ops.ping`) only. The `jobs` table with full states, dead-letter handling, concurrency caps and SSE progress arrive when a ticket needs them (Phase 1A ingestion).

## Consequences

| Type | Consequence |
|---|---|
| Positive | Business code and tests don't import Celery; an in-memory fake adapter makes use-case tests fast |
| Positive | Spec-mandated stack with no new infrastructure |
| Negative | Celery's at-least-once delivery requires idempotent jobs everywhere |
| Negative | Redis broker durability is weaker than a log-based broker; acceptable because Postgres holds workflow state and the outbox can redeliver |
| Follow-up | P0-060 port, adapter and ping job; P0-061 outbox relay (deferred to 1A under time-box Option B) |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Temporal or another workflow engine | Forbidden by spec §18 without an ADR and concrete need; heavy for one developer |
| RQ, Dramatiq, arq | Viable, but the spec fixes Celery; no concrete need to deviate |
| FastAPI background tasks | Lost on process restart; no retries or visibility |
| Kafka | Forbidden by spec §18; no streaming need |

## Enforcement

- import-linter: only `jobs.infrastructure` may import `celery`.
- Integration test (P0-060): enqueue through the port, observe completion; a failing job retries with backoff then reaches a failed state.
- Review checklist item: every new job states how it is idempotent.
