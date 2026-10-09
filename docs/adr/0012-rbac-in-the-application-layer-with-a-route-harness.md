# ADR 0012: Decide authorization in the application layer, and prove it with a route-enumerating harness

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-09 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §10 (Authorization), §17 (Security scorecard), §6 (multi-tenancy); ADR 0002 (RLS), ADR 0010 (sessions), ADR 0011 (bootstrap) |

## Context

Row-level security (ADR 0002) stops a query from reaching another tenant's rows,
but it cannot express "an editor may not do this" and it cannot refuse a request
before work begins. The spec requires RBAC (owner, editor, viewer) per workspace,
checked in the application layer *and* enforced by Postgres.

The harder problem is keeping that true as the app grows. A per-route authorization
check is only as good as the discipline of whoever adds the next route, and a
hand-written list of routes to test rots the moment someone forgets to update it.

## Decision

1. **One decision point.** `WorkspaceAccessService.authorize` is the only place that
   decides whether a caller may act in a workspace. Routes never compare roles.
2. **One gate.** Routes declare the role they need with `require_role(Role.X)`.
   The dependency resolves the workspace and the user from the server-side session,
   never from a path, query or body parameter, so there is no identifier for a
   caller to tamper with.
3. **Membership is re-checked on every request.** The session carries the workspace
   (ADR 0011), but carrying it is not proof of membership. A user removed from a
   workspace is refused on their next request rather than when their session expires.
4. **One refusal for two causes.** No membership and too low a role both raise
   `InsufficientRoleError` (403, `insufficient-role`). The caller cannot tell the
   difference, so the response cannot be used to discover which workspaces exist.
5. **Roles are ranked, not matched.** owner (3) outranks editor (2), which outranks
   viewer (1), so `require_role(Role.EDITOR)` admits owners. The rank table lives in
   the domain, and a test walks `Role` so a role added without a rank fails the build.
6. **One query answers both questions.** The `WorkspaceAccessStore` port returns a
   `WorkspaceAccess` (workspace id, name, role) or `None`. The SQL adapter joins the
   workspace to the caller's own membership under their tenant context, so a
   non-member gets no row even though RLS alone would have let them read that
   workspace's membership list. Application check and RLS stay independent.
7. **The cross-tenant harness reads the OpenAPI document, not a list.** It signs in a
   real user whose session names workspace A while holding no membership there, calls
   every documented route, and requires a denial (401, 403 or 404) from each. A route
   added later is covered the moment it appears in the document.
8. **Exempting a route is deliberate and visible.** `EXEMPT` maps a route to the
   reason it carries no workspace data, and `test_no_stale_exemptions` fails once an
   exempt route disappears, so the list cannot quietly grow stale.
9. **The harness is itself tested.** A seeded route with no role check must make the
   harness fail. Without that, a harness that silently stopped checking would look
   like a passing build.

## Consequences

| Type | Consequence |
|---|---|
| Positive | A new route is covered by the harness without anyone remembering to add it |
| Positive | Authorization is readable in one place per route, and decided in one place in the code |
| Positive | A removed member loses access immediately, without session revocation machinery |
| Negative | Every gated request costs one membership query. Acceptable: it is a single indexed lookup on `(user_id, workspace_id)`, and it is the price of not trusting the session's own claim |
| Negative | The harness cannot prove a route is *correctly* scoped, only that it refuses a non-member. Per-route tests still carry that weight |
| Negative | `identity/api/me.py` imports the gate from `workspaces/api`, because membership is owned by `workspaces`. Allowed by the import contracts, and preferable to identity reading another module's tables |
| Follow-up | P0-055 (rate limits on the auth routes). Workspace switching, invitations and role changes arrive with multi-user work in Phase 5 |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Rely on RLS alone | Cannot express role requirements, and gives a confusing empty result instead of a refusal |
| Middleware that guards by URL prefix | A path pattern is a weak statement of intent, and a new route under a guarded prefix can silently inherit the wrong role |
| Trust the role recorded in the session at login | A user removed from a workspace, or demoted, would keep their old rights until the session expired |
| A hand-written list of routes for the cross-tenant test | Rots silently; the acceptance test asks for 100% coverage of routes, which only enumeration can give |
| Separate 404 for a non-member workspace and 403 for a low role | The distinction tells an attacker which workspace ids exist |

## Enforcement

- `apps/api/tests/test_rbac.py`: the full role-ranking matrix, every role is ranked, 403 shape, authorize admits a permitted caller and refuses a low role, a non-member and an unknown workspace, both refusals carry the same code, and both routes return 401 without a session and 403 for a member-less session.
- `apps/api/tests/test_cross_tenant.py`: the document has routes to check, no stale exemptions, every non-exempt route refuses a non-member, and a seeded unprotected route makes the harness fail.
- `tests/integration/test_rbac_db.py` (creatoriqx_test, runtime role): the owner of a fresh workspace is authorized at every role level, a user from another workspace is refused while keeping access to their own, and an unknown workspace is refused.
