# CreatorIQX Dependencies

Every dependency is checked for its latest stable version **at install time** (spec §0.3, §5) and pinned through lockfiles (`uv.lock`, `pnpm-lock.yaml`). Add a row in the same commit that adds a dependency.

## Toolchain

| Tool | Pinned or minimum | Checked on | Where pinned | Notes |
|---|---|---|---|---|
| Python | 3.14 (spec minimum 3.12) | 2026-10-08 | `.python-version`, `requires-python >=3.12` | 3.14 chosen because uv's managed 3.13 download failed to link on the owner's Windows machine; the installed 3.14.6 works and meets the spec |
| uv | >= 0.12 (0.12.23 installed) | 2026-10-08 | `scripts/dev.py` doctor | Installed with `py -m pip install --user uv` |
| uv_build (build backend) | >=0.12.23,<0.13 | 2026-10-08 | `apps/api/pyproject.toml` | uv's native backend |
| Node.js | >=22.12 <23 (22 LTS) | 2026-10-08 | `package.json` engines | 22.23.2 installed |
| pnpm | 12.10.1 | 2026-10-08 | `package.json` `packageManager` | Corepack switches to this exact version |
| Docker | >= 27 (29.8 installed) | 2026-10-08 | `scripts/dev.py` doctor | Docker Desktop with WSL2 |

## Container images (`infra/compose/docker-compose.yml`)

| Image | Tag | Checked on | Notes |
|---|---|---|---|
| postgres | 18-alpine | 2026-10-08 | Spec needs 16+; 18 is the current major. Data volume mounts at `/var/lib/postgresql` (18+ layout) |
| redis | 8-alpine | 2026-10-08 | Append-only persistence on |

## JavaScript packages

| Package | Version | Checked on | Scope | Why |
|---|---|---|---|---|
| prettier | 3.9.9 (exact) | 2026-10-08 | root dev | Formatter; exact pin so formatting never shifts between machines |
| next | 16.4.0 | 2026-10-09 | apps/web | App Router framework (P0-080) |
| react, react-dom | 19.3.0 | 2026-10-09 | apps/web | Peer of Next 16.4 |
| @types/react, @types/react-dom | 19.3.0 | 2026-10-09 | apps/web dev | Types matching the installed React |
| typescript | 6.0.3 | 2026-10-09 | apps/web dev | Strict TS for the web app. npm's `latest` tag is 7.0.2, but `typescript-eslint@8.71.1`'s peer range is `>=4.8.4 <6.1.0` (confirmed by a real CI failure, not guessed), so 6.0.3 is the newest version both tools accept |
| @types/node | 26.6.4 | 2026-10-09 | apps/web dev | Types for Next's Node-side code (config, route handlers) |
| tailwindcss, @tailwindcss/postcss | 4.3.3 | 2026-10-09 | apps/web / apps/web dev | CSS-first design tokens via `@theme` (P0-080); no `tailwind.config.js` needed in v4 |
| clsx | 2.1.1 | 2026-10-09 | apps/web | Conditional class composition, used by `cn()` |
| tailwind-merge | 3.7.0 | 2026-10-09 | apps/web | Resolves conflicting Tailwind utilities in `cn()` (shadcn/ui convention) |
| lucide-react | 1.53.0 | 2026-10-09 | apps/web | Icon set named in spec section 5 |
| eslint | 10.12.0 | 2026-10-09 | apps/web dev | Flat config; carries the no-raw-hex rule for P0-080 |
| @eslint/js, typescript-eslint | 10.0.1, 8.71.1 | 2026-10-09 | apps/web dev | Recommended rule sets for the flat config |
| @next/eslint-plugin-next | 16.4.0 | 2026-10-09 | apps/web dev | Next's own lint rules, added directly to the flat config (no `eslint-config-next` compat wrapper needed) |

CI-only (not in any `package.json`, fetched by `npx` the way `docs.yml` already fetches `@mermaid-js/mermaid-cli`): `playwright@1.64.0` (light/dark screenshot evidence for P0-080; Playwright becomes a real devDependency in P0-083 when the Playwright+axe harness is built), `wait-on@9` (waits for `next start` before screenshotting).

## Python packages (dev group, root `pyproject.toml`)

| Package | Version | Checked on | Why |
|---|---|---|---|
| ruff | 0.16.10 | 2026-10-08 | Lint (incl. C901 complexity 10) and format |
| mypy | 2.4.0 | 2026-10-08 | Strict type checking |
| pytest | 9.1.1 | 2026-10-08 | Test runner |
| pytest-cov | 7.1.0 | 2026-10-08 | Coverage (70% overall via `fail_under`) |
| import-linter | 2.15 | 2026-10-08 | Architecture contracts (ADR 0001) |
| pre-commit | 4.6.2 | 2026-10-08 | Git hooks runner |

## Python packages (API runtime, `apps/api/pyproject.toml`)

| Package | Version | Checked on | Why |
|---|---|---|---|
| fastapi | 0.143.0 | 2026-10-08 | Web framework |
| uvicorn[standard] | 0.54.0 | 2026-10-08 | ASGI server |
| pydantic | 2.13.5 | 2026-10-08 | Validation |
| pydantic-settings | 2.15.0 | 2026-10-08 | Environment settings |
| prometheus-client | 0.26.0 | 2026-10-08 | `/metrics` |
| asyncpg | 0.32.0 | 2026-10-08 | PostgreSQL driver (readiness now, SQLAlchemy from P0-040) |
| redis | 8.1.0 | 2026-10-08 | Redis client |

Dev additions on 2026-10-08: httpx2 2.13.1 (Starlette's test client now recommends it over httpx, which emits a deprecation warning), asyncpg-stubs 0.32.0 (types for mypy strict).

Local URLs use `127.0.0.1`, not `localhost`: on Windows, `localhost` tries IPv6 `::1` first and a refused IPv6 connection takes about 2 seconds to fail, which exceeded the 2 second readiness timeout (found by the P0-030 integration test).

## pre-commit hooks (`.pre-commit-config.yaml`)

Pinned with `pre-commit autoupdate` on 2026-10-08.

| Hook repo | Version | Hooks |
|---|---|---|
| pre-commit/pre-commit-hooks | v6.0.0 | end-of-file, trailing whitespace, LF line endings, YAML/TOML/JSON syntax, merge conflicts, large files (500 KB), private keys |
| astral-sh/ruff-pre-commit | v0.16.10 | ruff check --fix, ruff format |
| gitleaks/gitleaks | v8.30.0 | secret scanning (built locally by pre-commit on first run) |
| local | (repo Prettier 3.9.9) | Prettier for JSON, YAML, JS, TS, CSS |
