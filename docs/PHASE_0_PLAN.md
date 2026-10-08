# CreatorIQX Phase 0 Plan

Spec: `CLAUDE.md` Revision 2.5.1 (frozen). Backlog: `docs/backlog/PHASE_0.md`. Status: **awaiting owner approval**. No implementation code is written until approval.

## 1. Goal and Done-when (from spec §15)

A user can log in with Google, a workspace exists, CI is green (lint, types, tests, secret scan), a sample module with tests exists, and the remaining security scans run and report.

Out of scope for Phase 0: YouTube connection, any YouTube API call, AI gateway and `LLMProvider`, storage provider, video aggregate, onboarding wizard, Caddy and VPS deployment. All of these belong to Phase 1A or later.

## 2. Files and directories

| Path | Created or modified | Purpose |
|---|---|---|
| `CLAUDE.md` | Created (spec, renamed) | Source of truth every session reads |
| `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md` | Created | Quickstart, working rules, release notes |
| `Makefile`, `.editorconfig`, `.gitignore`, `.env.example`, `.pre-commit-config.yaml` | Created | One-command tasks, hygiene, hooks |
| `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml` | Created | JS workspace |
| `pyproject.toml` (uv workspace root), `uv.lock` | Created | Python workspace |
| `packages/config/product.json` | Created | `PRODUCT_NAME = "CreatorIQX"`, single source |
| `packages/api-client/` | Created | `openapi.json` plus generated TS client |
| `apps/api/src/creatoriqx_api/main.py`, `settings.py`, `db/`, `http/` | Created | App factory, config, DB session, middleware, error mapping |
| `apps/api/src/creatoriqx_api/modules/identity/{domain,application,infrastructure,api}` | Created | Users, OIDC login, sessions |
| `apps/api/src/creatoriqx_api/modules/workspaces/{domain,application,infrastructure,api}` | Created | Reference hexagonal module: workspaces, memberships, RBAC |
| `apps/api/src/creatoriqx_api/modules/audit/` | Created | Append-only audit log port and adapter |
| `apps/api/src/creatoriqx_api/modules/jobs/` | Created | `TaskQueue` port, Celery adapter, outbox relay |
| `apps/api/src/creatoriqx_api/modules/telemetry/` | Created | `UsageEvent` contract and sink |
| `apps/api/migrations/` | Created | Alembic environment and revisions |
| `apps/api/tests/{unit,integration,contract,security}` | Created | Test layers including cross-tenant harness and RLS meta-test |
| `apps/worker/` | Created | Celery entrypoint using the api package |
| `apps/mcp-server/` | Created | MCP scaffold with `get_app_info` |
| `apps/web/` | Created | Next.js app, tokens, shadcn, Storybook, Playwright |
| `skills/README.md` | Created | SKILL.md format |
| `infra/compose/docker-compose.yml`, `infra/compose/postgres-init/`, `infra/docker/*.Dockerfile` | Created | Local runtime and images |
| `.github/workflows/ci-python.yml`, `ci-web.yml`, `security.yml`, `e2e.yml`, `.github/dependabot.yml` | Created | CI and supply chain |
| `docs/adr/0000-template.md` and `0001` to `0009` | Created | Initial ADRs from spec §15 |
| `docs/ARCHITECTURE.md`, `DATA_MODEL.md`, `SECURITY.md`, `RUNBOOK.md`, `DEPLOYMENT.md`, `TESTING.md`, `PROMPTS.md`, `UX_GUIDELINES.md`, `YOUTUBE_CAPABILITIES.md`, `OPEN_QUESTIONS.md`, `DEPENDENCIES.md`, `PROGRESS.md` | Created | §16 deliverables (stubs where content arrives later) |
| `docs/design/phase-0/` | Created | Wireframes for owner approval |

## 3. Implementation order

| Step | Tickets | Why this order |
|---|---|---|
| 1 | P0-001 to P0-007 | Docs, ADRs and threat model first, so code follows recorded decisions |
| 2 | P0-090 | Wireframes early, so owner approval is ready before UI tickets |
| 3 | P0-010, P0-011, P0-013 | Repo and Python quality gates |
| 4 | P0-100 | Python CI early, so every later ticket runs in CI |
| 5 | P0-020, P0-030 to P0-033 | Data services and backend skeleton |
| 6 | P0-040 to P0-044 | Persistence, schema, RLS, platform tables, ERD |
| 7 | P0-060 to P0-062 | TaskQueue, outbox relay, telemetry (the latter two may defer, see time-box) |
| 8 | P0-050, P0-051, P0-053, P0-054, P0-055 | Login, sessions, bootstrap, RBAC, rate limits |
| 9 | P0-080 to P0-083, P0-012, P0-101 | Frontend foundation and JS CI |
| 10 | P0-091, P0-092 | Screens (only after wireframe approval) |
| 11 | P0-021, P0-022, P0-070 | Images, one-command setup, MCP scaffold |
| 12 | P0-102, P0-103 | Security scans and E2E in CI |
| 13 | P0-052, P0-110 | Real login evidence and the phase gate |

## 4. Decisions

### Fixed by the spec (not reopened)

| # | Decision |
|---|---|
| F1 | Modular monolith, hexagonal layers per module; dependencies point inward; module boundaries enforced by import-linter and dependency-cruiser |
| F2 | Stack as spec §5: Next.js, TS strict, Tailwind, shadcn/ui, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, PostgreSQL 16+, Redis, Celery behind `TaskQueue` |
| F3 | Multi-tenancy via `workspace_id` and PostgreSQL RLS set per request; cross-tenant test on every endpoint |
| F4 | Login is Google OIDC with PKCE and identity scopes only; YouTube OAuth is a separate later flow |
| F5 | Server-side sessions in Redis; HttpOnly, Secure, SameSite cookies; rotation on login |
| F6 | RBAC roles owner, editor, viewer |
| F7 | UUIDv7 ids, `created_at`, `updated_at`, version column, soft delete where needed |
| F8 | REST under `/api/v1`, OpenAPI as source of truth, generated TS client, RFC 9457 errors |
| F9 | Append-only audit log; outbox pattern for domain events |
| F10 | Phase 0 depth rule; design before UI code; binary ticket outcomes with evidence |
| F11 | Scope guardrails: no Kubernetes, Kafka, GraphQL, microservices, workflow engines, vector DB |
| F12 | Secret scan blocking from Phase 0; other scans wired and reporting, blocking from 1A |

### Proposed in this plan (implementation-level, within the spec; owner may veto)

| # | Decision | Reason |
|---|---|---|
| D1 | `packages/config/product.json` holds the product name for both stacks | Satisfies "single config constant" across Python and TypeScript |
| D2 | uv workspace: worker and MCP server depend on the api package rather than duplicating code | One domain codebase, one deployable backend |
| D3 | `workspaces` is the reference ("sample") module with full layers and tests | The Done-when needs a sample module; a real one avoids dummy code |
| D4 | Two DB roles: owner for migrations, runtime role `NOBYPASSRLS` that owns no tables; `FORCE ROW LEVEL SECURITY` | Table owners bypass RLS unless forced; least privilege |
| D5 | First-login bootstrap generates the workspace UUID in the app, sets it as RLS context, then inserts; no privileged bypass path | Avoids a "superuser door" in the auth flow |
| D6 | RLS meta-test fails if any table with `workspace_id` lacks a policy | Makes "RLS on every tenant table" self-enforcing |
| D7 | Dev single origin via a Next.js `/api` rewrite; Caddy arrives in 1E as planned | Same-origin cookies, no CORS, fewer moving parts locally |
| D8 | Login restricted by an email allow-list (`AUTH_ALLOWED_EMAILS`) in v1 | Single-user v1; defense in depth beyond Google Testing mode |
| D9 | Test-only OIDC stub for E2E exists only when `APP_ENV=test`; a test proves it cannot load in production config | E2E without real Google credentials, without a production backdoor |
| D10 | Navigation shows only implemented items; nothing future is presented as working | Spec scorecard: no fake functionality presented as real |
| D11 | How the MCP server reaches data (API over HTTP versus direct DB) is decided by ADR when the first real tool is built, not now | Not needed for Phase 0; avoids a premature decision |

## 5. Risks and external blockers

| Risk or blocker | Impact | Mitigation |
|---|---|---|
| Q1 unanswered (no GitHub repo) | CI tickets cannot PASS | Work proceeds locally; CI tickets marked BLOCKED with evidence |
| CodeQL on a private repo may need paid GitHub features (verify) | Spec requires CodeQL | Public repo, paid plan, or an ADR for a free alternative (owner choice) |
| Q2 unanswered (no Google OAuth client) | Real login evidence (P0-052) cannot PASS | All auth logic tested with a mocked IdP; only the real-login ticket waits |
| Q3: Docker unavailable or low RAM on the owner's machine | Compose stack cannot run | Confirm early; slim images; run web outside Docker in dev if needed |
| Secure or `__Host-` cookies on `http://localhost` behave differently per browser (verify) | Login may fail in some browsers locally | Recorded in OPEN_QUESTIONS; fallback is Caddy `tls internal` locally |
| Library drift (OIDC library, MCP SDK, API client generator) | Wrong APIs from memory | Verify current docs and versions at install; record in DEPENDENCIES and OPEN_QUESTIONS |
| Estimate exceeds spec box (about 56 h versus 4 to 7 days) | Time-box rule triggered | Owner picks Option A or B (backlog totals section) |
| Claude plan usage limits interrupt sessions | Lost context | One to three tickets per session; PROGRESS updated every session |
| Owner approval latency on wireframes | UI tickets wait | Wireframes scheduled at step 2 |

## 6. Assumptions

| # | Assumption |
|---|---|
| A1 | Owner's personal Google account is the only login in v1 |
| A2 | English only in v1, with next-intl prepared |
| A3 | No brand assets yet; neutral design tokens until the owner supplies a direction |
| A4 | Table ownership for platform tables: `audit_log` -> audit, `usage_events` -> telemetry, `outbox_events` and `idempotency_keys` -> jobs |
| A5 | Estimates are agent-assisted hours with owner review included |
