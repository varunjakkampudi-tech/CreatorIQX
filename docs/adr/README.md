# Architecture Decision Records

Every significant decision gets an ADR (spec §0.4). Copy [`0000-template.md`](0000-template.md), use the next number, and add a row here in the same commit. Accepted ADRs are never edited in substance; supersede them with a new ADR.

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-modular-monolith-hexagonal.md) | Build a modular monolith with hexagonal module boundaries | Accepted | 2026-10-08 |
| [0002](0002-postgresql-rls-tenancy.md) | Isolate tenants with PostgreSQL row-level security | Accepted | 2026-10-08 |
| [0003](0003-celery-redis-behind-taskqueue.md) | Run background work on Celery and Redis behind a TaskQueue port | Accepted | 2026-10-08 |
| 0004 | OIDC login separate from the YouTube OAuth connection | Planned (P0-003; waits on owner decision OQ-14) | — |
| [0005](0005-llmprovider-mcp-bridge-capped-api.md) | Put all runtime AI behind an LLMProvider port, MCP bridge in v1 | Accepted | 2026-10-08 |
| [0006](0006-versioned-artifacts-immutable-snapshots.md) | Version artifacts independently and publish only immutable snapshots | Accepted | 2026-10-08 |
| [0007](0007-youtube-capability-model-manual-upload.md) | Gate every YouTube write behind a verified capability; default to manual Private upload | Accepted | 2026-10-08 |
| [0008](0008-shared-transcripts-module.md) | Serve all transcript sources through one shared transcripts module | Accepted | 2026-10-08 |
| [0009](0009-quota-ledger-redis-postgres.md) | Track YouTube quota live in Redis and durably in Postgres | Accepted | 2026-10-08 |
