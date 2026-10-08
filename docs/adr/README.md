# Architecture Decision Records

Every significant decision gets an ADR (spec §0.4). Copy [`0000-template.md`](0000-template.md), use the next number, and add a row here in the same commit. Accepted ADRs are never edited in substance; supersede them with a new ADR.

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-modular-monolith-hexagonal.md) | Build a modular monolith with hexagonal module boundaries | Accepted | 2026-10-08 |
| [0002](0002-postgresql-rls-tenancy.md) | Isolate tenants with PostgreSQL row-level security | Accepted | 2026-10-08 |
| [0003](0003-celery-redis-behind-taskqueue.md) | Run background work on Celery and Redis behind a TaskQueue port | Accepted | 2026-10-08 |
| 0004 | OIDC login separate from the YouTube OAuth connection | Planned (P0-003) | — |
| 0005 | `LLMProvider`, MCP bridge in v1, capped API mode disabled by default | Planned (P0-003) | — |
| 0006 | Versioned artifacts and immutable publish snapshots | Planned (P0-003) | — |
| 0007 | YouTube capability model and manual-upload (Private) default workflow | Planned (P0-004) | — |
| 0008 | Shared transcripts module | Planned (P0-004) | — |
| 0009 | Quota ledger: Redis live, Postgres durable | Planned (P0-004) | — |
