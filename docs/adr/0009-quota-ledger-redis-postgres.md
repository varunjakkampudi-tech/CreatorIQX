# ADR 0009: Track YouTube quota live in Redis and durably in Postgres

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §6 (Quota management, Graceful degradation), §7 (`quota_ledger`), §17 (YouTube integration) |

## Context

The YouTube Data API has a daily quota with per-method costs (verify current values, OQ-04). Running out mid-sync can leave partial writes; overspending can disrupt a creator's workflow for a day. Checks must be fast and atomic across concurrent workers, and the history must survive a Redis restart for reporting and debugging.

## Decision

1. **Live counters in Redis:** per workspace, per day (in the quota's reset timezone, verify), an atomic reserve-then-commit check before every call (Lua script or `INCRBY` with a guard). A call that would exceed the budget is refused before it is made.
2. **Durable ledger in Postgres:** every call, reserved or refunded, writes a `quota_ledger` row (workspace, method, units, outcome, correlation id, timestamp).
3. **Reconciliation:** if Redis loses its counters, the day's total is rebuilt from the ledger before any further call.
4. **Graceful degradation:** on exhaustion, reads fall back to cached data, writes queue for the next window or move to manual-apply, and the UI says so. Nothing fails silently.
5. Method costs live in configuration with the source and verification date, not inline.

## Consequences

| Type | Consequence |
|---|---|
| Positive | No over-spend under concurrency; history for audits and cost reports |
| Negative | Two stores to keep consistent; a small write per call |
| Follow-up | Phase 1A (ledger, reservation, first ingestion) |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Redis only | History lost on flush; no reporting |
| Postgres only | Row-lock contention on hot counters; slower pre-flight checks |
| Rely on Google's quota errors | Discovers exhaustion mid-operation, causing partial writes |

## Enforcement

- Concurrency test: N parallel reservations never exceed the budget.
- Test: after a Redis flush, the counter is rebuilt from the ledger before the next call.
- Test: exhaustion produces a degraded-but-usable response, not an unhandled error.
