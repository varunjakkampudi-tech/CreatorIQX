# ADR 0002: Isolate tenants with PostgreSQL row-level security

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §1 (Scalability), §6 (Multi-tenancy), §7, §10 (Authorization), §17 (Security, Data model) |

## Context

v1 has one user, but v2 must host many creators in one database with no redesign, and their YouTube data and tokens must never leak across workspaces. Application-level `WHERE workspace_id = ...` filters alone fail silently the first time a query forgets one. The spec requires both application checks and database enforcement.

## Decision

1. Every tenant table has a non-null `workspace_id`. Global tables (for example `users`) are the documented exception and are listed in `docs/DATA_MODEL.md`.
2. **Row-level security is enabled and forced** (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY; ALTER TABLE ... FORCE ROW LEVEL SECURITY`) on every tenant table, with policies comparing `workspace_id` to `current_setting('app.workspace_id')` for SELECT, INSERT, UPDATE and DELETE.
3. **Two database roles:**

| Role | Used by | Properties |
|---|---|---|
| `creatoriqx_owner` | Alembic migrations only | Owns tables |
| `creatoriqx_app` | API, worker, MCP server at runtime | `NOBYPASSRLS`, owns no tables, no DDL rights; no UPDATE or DELETE on `audit_log` |

4. **Tenant context per request:** each request runs in one transaction that sets `SET LOCAL app.workspace_id` and `SET LOCAL app.user_id` from the authenticated session before any query. `SET LOCAL` scopes the values to the transaction, so a pooled connection never carries a previous request's tenant. Background jobs set the same context from the job's workspace.
5. **No privileged bypass path in the app.** First-login bootstrap generates the new workspace id in the application, sets it as the context, then inserts (plan decision D5).
6. Authorization is checked **twice**: role checks in the application layer (owner, editor, viewer), and RLS in the database as the backstop.

## Consequences

| Type | Consequence |
|---|---|
| Positive | A forgotten filter returns no rows instead of another tenant's rows |
| Positive | Multi-tenancy is built in from the first table; v2 needs no data migration |
| Negative | Every query path must establish tenant context; missing context must fail closed (unset setting means no rows) |
| Negative | Policies need tests; cross-workspace admin tooling needs a deliberate, audited design later |
| Follow-up | P0-020 roles; P0-042 RLS, context and meta-test; P0-054 cross-tenant endpoint harness |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Application filters only | Fails open when a filter is forgotten; spec requires database enforcement |
| Schema per tenant | Migration fan-out, connection complexity; no benefit at this scale |
| Database per tenant | Forbidden by the spirit of §18; operational cost |

## Enforcement

- **RLS meta-test** (P0-042): queries `pg_class` and `pg_policies` and fails if any table with a `workspace_id` column lacks forced RLS and policies.
- **Cross-tenant harness** (P0-054): calls every route in the OpenAPI document as a member of another workspace and expects denial; new routes are covered automatically.
- Runtime role test: `creatoriqx_app` cannot bypass RLS, run DDL, or modify `audit_log`.
