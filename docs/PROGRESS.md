# CreatorIQX Progress

Read this file at the start of every session. Update it at the end of every session (spec §0 rule 9).

| Field | Value |
|---|---|
| Last updated | 2026-10-09 |
| Spec | `CLAUDE.md`, MASTER BUILD SPEC Revision 2.5.1 (frozen; product name set to CreatorIQX) |
| Current phase | **Phase 0: Foundation, implementation in progress** (plan approved by owner 2026-10-08) |
| Last PASS ticket | **P0-050** — E6 Identity and access, Google OIDC login (also PASS: P0-001 to P0-007, P0-010, P0-011, P0-013, P0-020, P0-030 to P0-033, P0-040 to P0-044, P0-100) |
| Open BLOCKED items | None |
| Build environment | **Owner's Windows 11 machine** (`C:\Users\Admin\Desktop\creatoriqx`), driven through Claude Desktop Commander. Git 2.56, Docker Desktop 29.8 (WSL2), Python 3.14.6, uv 0.12.23, Node 22.23, pnpm 12.x. Postgres and Redis run in Docker Compose on 127.0.0.1:55432 / 56379 |
| Repository | `github.com/varunjakkampudi-tech/CreatorIQX`. Appears public (OQ-09). Pushing works |

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
| P0-044 | PASS | Commit `568a764`; `scripts/generate_erd.py` produces Mermaid ERD + ownership table + global tables from metadata; `--check` drift guard wired into `dev.py lint`; 6 tests; 107 tests total, 93% coverage |
| P0-050 | PASS | Commit `99ff451`; identity module (domain/application/infrastructure/api layers); GoogleOIDCProvider with PyJWT + JWKS; PKCE S256; mocked-provider tests cover valid login, bad state, bad nonce, wrong audience, expired token, unverified email, non-allow-listed email, case-insensitive allow-list, empty allow-list, problem+json format; ruff (incl. C901) clean |

## Owner actions pending

| ID | Action | Unblocks |
|---|---|---|
| OQ-09 | Confirm the repo stays public (keeps CodeQL free) | P0-102 |

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

## Exact next step

**P0-051** (Sessions and CSRF) — server-side sessions in Redis, cookie security (`HttpOnly`, `Secure`, `SameSite=Lax`), session rotation on login, idle and absolute timeouts, logout, CSRF token on unsafe methods. Then P0-053 (workspace bootstrap reference module). **P0-090** wireframes remain open for the owner's written approval before any UI code (E10/E11). Do not start Phase 1A.

## Phase 0 scorecard

Not yet run (runs in P0-110).
