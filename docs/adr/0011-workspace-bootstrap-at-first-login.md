# ADR 0011: Bootstrap the user, personal workspace and owner membership at first login

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-09 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §7 (identity schema), §6 (idempotency, outbox), §10 (authorization, audit); ADR 0002 (RLS), ADR 0004 (login), ADR 0010 (sessions) |

## Context

Every tenant table is protected by forced row-level security (ADR 0002). A
first-time user has no workspace, no membership and no tenant context, yet the
first login must create all three. The naive approach (a superuser or
`BYPASSRLS` role that creates them) would make the bootstrap path a privileged
bypass, which the security model forbids. The session then has to carry the
tenant context, because every later request needs it to query anything.

## Decision

1. **One transaction per login, under an advisory lock per Google subject.**
   The store takes `pg_advisory_xact_lock(hashtextextended('identity.google-sub:' || subject, 0))`
   first. Two concurrent first logins for the same person serialise on that lock,
   so only one creates the workspace. The lock is released at commit.
2. **Ids are chosen by the application.** `new_id()` (UUIDv7) generates the user,
   workspace and membership ids before the store is called. The store never mints
   ids, so no privileged path is needed to create them.
3. **Every row is written under its own tenant context.** `set_tenant_context`
   binds `app.workspace_id` and `app.user_id` for the transaction (`set_config(..., true)`).
   - `users` is global and has no RLS, so it needs no context.
   - The workspace, its owner membership and the `workspace.created` outbox event
     are written under the new workspace id. `INSERT ... RETURNING` is then
     checked by the read policy, which the new row satisfies.
   - Each audit row is flushed under its own context: the workspace id, or
     `NO_WORKSPACE` when it has none (`user.created`). This is why audit rows are
     never batched across contexts.
4. **`NO_WORKSPACE` is `uuid.UUID(int=0)`.** A sentinel, not a real tenant. No
   UUIDv7 can equal it, and under it RLS sees no workspace rows, so only rows
   visible without a workspace (the caller's own memberships, and audit rows with
   no workspace) are readable.
5. **Policies on `workspaces` (migration 0005).** Read: the current workspace, or
   a workspace the current user is a member of. Insert: unrestricted, because the
   membership does not exist yet and the following `RETURNING` is checked by the
   read policy. Update: the current workspace only. No delete policy, so a
   runtime delete is denied by default.
6. **Idempotent repeat login.** The store looks up the user by Google subject, then
   the first owner membership, and creates nothing when both exist. It still writes
   `auth.login_succeeded` on every login. `workspace.created` and `user.created` are
   written once.
7. **Email is a unique identity, not a merge key.** A new subject whose normalised
   email already belongs to another subject is refused with `IdentityConflictError`
   (409). The pre-check gives the clear path. A unique-constraint race is mapped to
   the same error. Accounts are never merged silently.
8. **Audit detail carries no personal data.** Audit rows hold ids, action and
   correlation id only. The email is not written to the audit log.
9. **The session carries the tenant.** `Session` stores `user_id` and `workspace_id`
   (ADR 0010). P0-054 reads them into the request-scoped tenant context.

## Consequences

| Type | Consequence |
|---|---|
| Positive | No BYPASSRLS path exists for bootstrap; the runtime role does everything under forced RLS |
| Positive | First-login races cannot create two workspaces for one person |
| Positive | Audit and outbox evidence is written in the same transaction as the data it describes |
| Negative | The `workspaces` read policy runs a `memberships` sub-select, so workspace reads cost one extra index lookup. Acceptable at this scale; the unique `(user_id, workspace_id)` index covers it |
| Negative | Sessions created before this change (none in production yet) have no tenant ids and must sign in again |
| Negative | One workspace per user is created on first login. Multi-workspace selection arrives with P0-054 and the workspace switcher |
| Follow-up | P0-054 (`require_role`, `GET /api/v1/me`, `GET /api/v1/workspaces/current`); P0-052 (owner runs the real Google login) |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| A `SECURITY DEFINER` function that creates the workspace | A privileged path inside the database that bypasses the policies it was meant to honour; harder to test and review than an ordinary transaction |
| A separate bootstrap role with `BYPASSRLS` | Gives a credential that can read every tenant. Forbidden by the role model (ADR 0002) |
| Create the workspace lazily on first API call instead of at login | Spreads tenant creation over many routes and races with them; login is the one place the identity is verified |
| Use a database sequence or the database to generate ids | UUIDv7 is generated app-side everywhere (`platform.ids`); keeping one id source avoids a second convention |
| Merge accounts that share an email | An unverified or reassigned email would hand one person's workspace to another; refusing is safer and recoverable by the owner |

## Enforcement

- `apps/api/tests/test_workspace_bootstrap.py`: domain sentinel and naming rules; idempotent repeat login; one workspace and one outbox event for two logins; audit actions on creation and on every login; email normalisation; subject and email validation; email conflict refused; default ids are UUIDv7.
- `tests/integration/test_workspace_bootstrap_db.py` (creatoriqx_test, runtime role): the first login writes user, workspace, owner membership, audit rows and outbox event; repeat login writes no second workspace; five concurrent first logins create exactly one workspace; a non-member cannot read another workspace; a conflicting email writes nothing; `workspaces` has forced RLS and its three policies.
- `apps/api/tests/test_sessions.py`, `test_session_routes.py`: sessions carry `user_id` and `workspace_id`, and `/auth/session` returns them.
- `apps/api/migrations`: migration 0005 round-trips (`dev.py` migration test).
