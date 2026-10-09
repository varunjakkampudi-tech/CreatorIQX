# CreatorIQX Progress

Read this file at the start of every session. Update it at the end of every session (spec §0 rule 9).

| Field | Value |
|---|---|
| Last updated | 2026-10-09 (session 2, Linux sandbox) |
| Spec | `CLAUDE.md`, MASTER BUILD SPEC Revision 2.5.1 (frozen; product name set to CreatorIQX) |
| Current phase | **Phase 0: Foundation, implementation in progress** (plan approved by owner 2026-10-08) |
| Last PASS ticket | **P0-053** — E6 Identity and access, workspace bootstrap (the reference hexagonal module) (also PASS: P0-001 to P0-007, P0-010, P0-011, P0-013, P0-020, P0-030 to P0-033, P0-040 to P0-044, P0-050, P0-051, P0-100) |
| Open BLOCKED items | P0-052 (real Google login, owner action). P0-090 (wireframe approval, owner action) |
| Build environment | Session 1: owner's Windows 11 machine (Claude Desktop Commander), no longer reachable. Session 2: Linux sandbox, clone at `/home/claude/creatoriqx`. PyPI and files.pythonhosted.org return proxy 403 there (egress policy), so no Python tool can run locally. **GitHub Actions is the verification environment**: gates are run by pushing and reading the result. Actions log blobs are also unreachable from the sandbox, so a temporary workflow posted gate output as a pull request comment; it was deleted once P0-053 was green |
| Repository | `github.com/varunjakkampudi-tech/CreatorIQX`. Appears public (OQ-09). Pushing works. **P0-053 is green in pull request #1 on `wip/p0-053-workspace-bootstrap` and waits for the owner to review and merge it.** `main` is at `87441a8` (P0-051) until then |

## Ticket log

| Ticket | Outcome | Evidence |
|---|---|---|
| P0-001 | PASS | Commit `083c204`; old-name grep count 0 |
| P0-005 | PASS | Commit `69fc663`; 16 questions; 0 `available` capabilities |
| P0-002 | PASS | Commit `0846bc0`; ADR template, index, 0001-0003; section check passed |
| P0-003 | PASS | Commits `060d8b5`, `5a88fc0`; ADRs 0004-0006 |
| P0-004 | PASS | Commit `060d8b5`; ADRs 0007-0009; section and capability checks passed |
| P0-006 | PASS | Commit `fe1cb79`; CI run 37774467054: 16/16 deliverables, 4 Mermaid diagrams rendered |
| P0-007 | PASS | Commit `7ea0c1d`; STRIDE v0, 20 threats, all 6 categories; 0 High threats without a ticket |
| P0-010 | PASS | Commit `f8b91fc`; clean-clone `dev.py setup` exit 0; lockfiles committed; no secrets in `.env.example` |
| P0-011 | PASS | Commit `2157f1d`; every gate proven with a seeded violation; clean tree lint exit 0, tests pass, 100% coverage |
| P0-013 | PASS | Commit `76320d0`; 13 hooks pass; fake token blocked by gitleaks |
| P0-100 | PASS | CI green on main (run 37782628775); seeded failing test turned run 37782770458 red at the test step |
| P0-020 | PASS | Postgres 18 and Redis 8 healthy; 7 role and RLS integration tests pass; seeded BYPASSRLS made 5 fail |
| P0-030 | PASS | Commit `299fb39`; app factory with /healthz, /readyz, /metrics, versioned OpenAPI |
| P0-031 | PASS | Commit `d8140ba`; structlog JSON logging with redaction; DomainError to RFC 9457 problem+json |
| P0-032 | PASS | Commit `4bf71d9`; security headers, CORS limited to configured origin, 413 body-size limit |
| P0-033 | PASS | Commit `6f0930d`; deterministic OpenAPI export with `--check` drift guard in CI |
| P0-040 | PASS | Commit `9a76336`; SQLAlchemy 2 async base, UUIDv7 ids, mixins, Alembic (owner role); migration round-trip passes; 85 tests, 88.6% coverage |
| P0-041 | PASS | Commit `612264b`; users/workspaces/memberships schema + migration 0002; round-trip and drift checks pass; 93 tests, 89% coverage |
| P0-042 | PASS | Commit `4914284`; forced RLS + `set_tenant_context`; meta-test verifies every `workspace_id` table; cross-context isolation proven; 96 tests, 92% coverage |
| P0-043 | PASS | Commit `615eedd`; migration 0004 (`audit_log`, `usage_events`, `outbox_events`, `idempotency_keys`); append-only proven at the privilege layer and the trigger layer; RLS isolation proven; 101 tests, 93% coverage |
| P0-044 | PASS | Commit `568a764`; `scripts/generate_erd.py` produces Mermaid ERD + ownership table + global tables from metadata; `--check` drift guard wired into `dev.py lint`; LF line endings fixed in `ea77c05`. Seeded red CI run still to do (P0-110) |
| P0-050 | PASS | Commit `99ff451`; identity module (domain/application/infrastructure/api layers); GoogleOIDCProvider with PyJWT + JWKS; PKCE S256; mocked-provider tests. Gate repair in `88c6286`. Callback now uses the P0-051 session model |
| P0-053 | PASS | CI runs 37900856733 (ci-python) and 37900856717 (docs) green. 196 tests, 92.36% total coverage, domain and application at or above 85%. `workspaces` built as the reference hexagonal module; migration 0005 (forced RLS on `workspaces`); first login creates user, personal workspace and owner membership in one transaction with an advisory lock per Google subject and no BYPASSRLS path; audit `user.created`, `workspace.created`, `auth.login_succeeded`; one `workspace.created` outbox event; repeat login idempotent. 6 Postgres integration tests incl. five concurrent first logins creating exactly one workspace. ADR 0011 |
| P0-051 | PASS | Redis server-side sessions (opaque 256-bit id); `__Host-` Secure HttpOnly SameSite=Lax cookies; rotation on login; idle (60 min) and absolute (12 h) timeouts; CSRF on unsafe methods; single-use login flow via atomic GETDEL. 170 tests incl. Redis integration; ADR 0010; SECURITY.md session controls; ARCHITECTURE.md sign-in and request flow diagrams |

## Owner actions pending

| ID | Action | Unblocks |
|---|---|---|
| OQ-09 | Confirm the repo stays public (keeps CodeQL free) | P0-102 |
| OQ-15 | Disable the old YouTube client secret in Google Cloud (it was shared in chat) | Security hygiene |
| P0-052 | Run the real Google login once on the local stack, in Chrome and Edge at minimum | Closes P0-052 (BLOCKED until then) |
| P0-090 | Written approval of the wireframes before any UI code | E10, E11 |

## Decisions made

| Date | Decision | Source |
|---|---|---|
| 2026-10-08 | Product working name is **CreatorIQX**, held as a single config constant in `packages/config/product.json` | Owner |
| 2026-10-08 | Spec 2.5.1 frozen; architecture changes only via ADR plus owner approval | Spec, owner |
| 2026-10-08 | Phase 0 plan and backlog approved (13 epics, 45 tickets) | Owner |
| 2026-10-08 | Time-box Option B applied by default (defer P0-055, P0-061, P0-062, P0-070 to the start of 1A). Owner may switch to Option A | Plan recommendation |
| 2026-10-08 | Login uses a separate login-only Google client (ADR 0004, closes OQ-14) | Owner |
| 2026-10-08 | Build runs on the owner's Windows machine; Python pinned to 3.14 (uv's managed 3.13 failed to link on this machine) | Environment |
| 2026-10-08 | YouTube client secret rotated by owner (OQ-15 closed) | Owner |
| 2026-10-09 | `idempotency_keys` is tenant-scoped with forced RLS (unique on workspace_id+key); `outbox_events` has no `workspace_id` and stays outside RLS, since the relay worker must read unpublished rows across every tenant | Plan detail decided while building P0-043 |
| 2026-10-09 | `audit_log` append-only is enforced in two independent layers: RLS itself (no UPDATE/DELETE policy = default deny) and a trigger that blocks UPDATE/DELETE for every role including the owner, as a backstop if a policy is ever added | Plan detail decided while building P0-043 |
| 2026-10-09 | main went red after `99ff451` (P0-050): `uv.lock` not updated, `itsdangerous` undeclared, test `Settings` missing `session_secret`, one file not ruff-formatted, a mypy `httpx`/`httpx2` mismatch in the tests. Repaired in `88c6286` | Repair, found while verifying P0-044 |
| 2026-10-09 | P0-044 was also built locally in parallel and pushed as `568a764` first; the local duplicate was backed up and dropped. Remote version kept | Reconciliation |
| 2026-10-09 | First login bootstraps user, personal workspace and owner membership in one transaction under forced RLS, with an advisory lock per subject and no BYPASSRLS path (ADR 0011). Sessions carry `user_id` and `workspace_id` | Decision, P0-053 (ADR 0011) |
| 2026-10-09 | Session 2 could not install Python packages (PyPI egress 403). The egress policy was not routed around; GitHub Actions became the verification environment instead, driven through a pull request | Environment |
| 2026-10-09 | A SQLAlchemy flush orders inserts by mapper sort key (module path and class name), not by foreign key, because no ORM class here declares a `relationship()`. `workspaces.Membership` sorted ahead of `workspaces.Workspace`, so the first-login flush inserted the membership before its workspace and hit `fk_memberships_workspace_id_workspaces`. Multi-table writes now set the order explicitly (ADR 0011 decision 9) | Defect found by the P0-053 integration test |
| 2026-10-09 | Sessions are server-side in Redis with `__Host-` Secure cookies, always (ADR 0010). Starlette signed-cookie sessions removed: they cannot be revoked before expiry and need a shared secret | Decision, P0-051 (ADR 0010) |

## Exact next step

**First: the owner merges pull request #1** (P0-053). Both workflows are green on it
and the ticket is recorded PASS with evidence. A squash merge keeps one commit per
ticket, matching the existing history on `main`.

Then **P0-054** (RBAC and tenant isolation): `require_role()` dependency, `GET /api/v1/me`,
`GET /api/v1/workspaces/current`, and the cross-tenant harness that enumerates every
route in the OpenAPI document and calls it as a member of another workspace expecting
denial, plus a seeded unprotected route that makes the harness fail. The session already
carries `user_id` and `workspace_id` (P0-053), so the request-scoped tenant context is
the first piece to build.

Then P0-022, P0-021, P0-012, P0-080 to P0-083, P0-101 to P0-103, P0-110.

**P0-090** wireframes wait for the owner's written approval before any UI code (E10, E11).
Do not start Phase 1A.

### How to run the gates from a sandbox without package access

Push the branch and open a pull request; `ci-python` and `docs` run the same gates as
`dev.py lint` and `dev.py test`. Actions log blobs are unreachable from the sandbox, so
read results with `gh api repos/<owner>/<repo>/actions/runs/<id>/jobs`, or re-add a
temporary workflow that posts the output as a pull request comment.

## Phase 0 scorecard

Not yet run (runs in P0-110).
