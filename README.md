# CreatorIQX

A creator intelligence and YouTube workflow platform: plan, script, quality-check, approve, sync and learn from your videos, with a human approval step before anything public happens.

> **Status:** Phase 0 (Foundation) in progress. Nothing user-facing works yet. See [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Source of truth

| Document | Purpose |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Frozen master specification (Revision 2.5.1) |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Current phase, last PASS ticket, blockers, next step |
| [`docs/PHASE_0_PLAN.md`](docs/PHASE_0_PLAN.md) | Phase 0 plan and decisions |
| [`docs/backlog/PHASE_0.md`](docs/backlog/PHASE_0.md) | Phase 0 tickets with acceptance tests and evidence |
| [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) | Unverified facts and pending decisions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How work is done here |

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.14 (3.12 minimum) |
| uv | 0.12 or newer |
| Node.js | 22 LTS |
| pnpm | 12 (Corepack picks the exact version from `package.json`) |
| Docker Desktop | 27 or newer |

Exact versions and the reasons for them: [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

## Developer tasks

One cross-platform entry point, no `make` needed on Windows:

```
python scripts/dev.py <command>     # Windows: py scripts/dev.py <command>
```

| Command | What it does |
|---|---|
| `doctor` | Checks tool versions |
| `setup` | Runs `doctor`, creates `.env` from `.env.example` if missing, installs Python and JS dependencies from the lockfiles |
| `check-docs` | Verifies the documentation deliverables |
| `format` | Formats Python with Ruff and JSON, YAML and JS with Prettier |
| `lint` | Ruff, format check, mypy strict, import-linter architecture contracts, Prettier |
| `test` | pytest with coverage gates; integration tests need `up` first |
| `up` | Starts PostgreSQL (port 55432) and Redis (port 56379) on localhost and waits until healthy |
| `down` | Stops them; database data is kept |
| `api` | Runs the API at http://127.0.0.1:8000 with reload. Health: `/healthz`, `/readyz`; metrics: `/metrics`; docs: `/api/v1/docs` |
| `migrate` | Applies database migrations (owner role) |
| `up-full` | One-command setup (P0-022): builds and starts postgres, redis, api, worker and web as containers, then migrates and seeds |
| `down-full` | Stops the full containerized stack; database data is kept |
| `seed` | Creates the second demo workspace used for manual cross-tenant checks |

More commands (openapi, erd) are documented in `scripts/dev.py`'s own docstring.

## Quickstart

```
git clone <this repo>
cd creatoriqx
python scripts/dev.py setup      # toolchain check, .env, Python + JS dependencies, git hooks
python scripts/dev.py up-full    # builds and starts postgres, redis, api, worker, web; migrates; seeds
```

`up-full` waits until every service reports healthy, then runs database
migrations and creates a second demo workspace (for manual cross-tenant
checks) under a fixed fake Google subject - no real Google account needed
for that part. When it finishes:

| Check | URL |
|---|---|
| API liveness | <http://127.0.0.1:58000/healthz> |
| API readiness (DB + Redis) | <http://127.0.0.1:58000/readyz> |
| API docs (OpenAPI) | <http://127.0.0.1:58000/api/v1/docs> |
| Web app | <http://127.0.0.1:3000> |

**Signing in** needs a real Google OAuth client (`GOOGLE_LOGIN_CLIENT_ID` /
`GOOGLE_LOGIN_CLIENT_SECRET` in `.env`) - see
[`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) for the current status of
getting one. Without it, `/api/v1/auth/*` is not mounted at all (by design:
the app never pretends login works with no client configured), so the web
app has no screens to sign into yet either - see the status line at the top
of this file. **Phase 0 is infrastructure, not a usable product**: this
quickstart proves the stack boots, migrates and serves traffic end to end,
not that there is a dashboard to reach.

Stop everything with `python scripts/dev.py down-full` (data volumes are kept).

For day-to-day backend development (hot reload, no container rebuild per
change), use `up` + `api` instead of `up-full` - see Developer tasks above.

## License

Proprietary. All rights reserved (to be confirmed by the owner).
