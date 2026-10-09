# Changelog

All notable changes to CreatorIQX are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `jobs` module (P0-060): a `TaskQueue` port (`enqueue(JobRequest) -> JobHandle`,
  ADR 0003) with a `CeleryTaskQueue` adapter backed by a Redis broker on its own
  logical database, separate from sessions/quota. One working job, `ops.ping`,
  plus a test-only `ops.flaky` proving retry-then-failed over a real embedded
  worker and real Redis. New `apps/worker` package: a thin Celery CLI wrapper
  with no task code of its own. New import-linter contract `jobs-celery-boundary`:
  only `jobs.infrastructure` may import `celery`.
- `apps/web` (P0-012): TS/JS quality gates - `@typescript-eslint/no-explicit-any`
  raised to `error` (the recommended preset only warns), and dependency-cruiser
  (`.dependency-cruiser.cjs`) enforcing no import cycles and that the shared
  design-system primitives (`src/components/ui`) never import from `src/app`.
  Both proven to actually fail CI on a seeded violation, then reverted.
- `apps/web` (P0-083): a design-system skeleton - Button, Input, Card and Skeleton
  primitives under `src/components/ui`, styled only with the existing design tokens,
  each with a Vitest + Testing Library unit test; Storybook 10 with a story per
  primitive plus a design-tokens reference page; an accessibility gate
  (`tests/e2e/a11y.spec.ts`, `@axe-core/playwright`) that scans every story
  (enumerated from Storybook's own `index.json`, so a new story is covered
  automatically) and fails on any serious or critical finding.
- `apps/web` (P0-082): per-request Content Security Policy with a nonce (`src/proxy.ts`),
  blocking any inline script that doesn't carry it; next-intl wired in at one
  locale (`en`) with a lint rule forbidding hard-coded UI text; a Playwright
  end-to-end test proving the CSP nonce is present and enforced (P0-082).
- `packages/api-client`: a typed API client generated from `openapi.json` by
  openapi-typescript, with a `generate:check` drift guard. `apps/web` wires it into
  TanStack Query (`openapi-react-query`, a `QueryClientProvider`) and a typed
  `useCurrentUser()` calling `GET /api/v1/me` - the acceptance test's typed call, not
  yet rendered by any page (P0-081).
- `apps/web`: Next.js App Router frontend foundation - design tokens (color, 8px
  spacing grid, type scale, radius, motion) as CSS variables for light and dark,
  a shadcn/ui-style init (`components.json`, `cn()`), lucide icons, the `/api`
  rewrite to the local backend, and a lint rule forbidding raw hex literals in
  components. Not a product screen; those wait on P0-090's wireframe approval
  (P0-080).
- RBAC per workspace: `require_role()` gates every route that touches tenant data,
  resolving the workspace and user from the session and re-checking membership on
  every request, so a removed or demoted member loses access at once. Roles are
  ranked (owner > editor > viewer) and a non-member and an under-privileged member
  receive the same 403 (P0-054, ADR 0012).
- `GET /api/v1/me` and `GET /api/v1/workspaces/current`.
- Cross-tenant harness: enumerates every route in the OpenAPI document and requires
  a denial for a caller who is not a member of the workspace their session names, so
  routes added later are covered automatically.
- `workspaces` bounded context as the reference hexagonal module: first login creates the
  user, a personal workspace and an owner membership in one transaction under forced
  row-level security, with an advisory lock per Google subject and no privileged bypass
  path. Writes `user.created`, `workspace.created` and `auth.login_succeeded` audit rows
  and one `workspace.created` outbox event. Repeat login is idempotent (P0-053, ADR 0011).
- Sessions carry `user_id` and `workspace_id`, returned by `GET /api/v1/auth/session`.
- Frozen master specification (Revision 2.5.1, product named CreatorIQX) as `CLAUDE.md`.
- Phase 0 plan, backlog, progress log, agent kickoff prompt.
- README, CONTRIBUTING and this changelog.
