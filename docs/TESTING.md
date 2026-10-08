# CreatorIQX Testing

How quality is checked locally and in CI (spec §12, §17). Run everything from the repo root.

| Command | What it runs | Fails when |
|---|---|---|
| `py scripts/dev.py lint` | Ruff lint, Ruff format check, mypy strict, import-linter, Prettier check | Any warning, type error, boundary violation or unformatted file |
| `py scripts/dev.py test` | pytest with coverage, then the layer coverage gate | A test fails, overall coverage < 70%, or domain plus application coverage < 85% |

## Gates and where they are configured

| Gate | Rule | Config |
|---|---|---|
| Lint | Ruff rule set incl. security (S), annotations (ANN), complexity C901 max 10 | `[tool.ruff]` in `pyproject.toml` |
| Types | mypy `strict = true`, no untyped defs | `[tool.mypy]` |
| Architecture | Domain imports no frameworks; module layers api/infrastructure > application > domain; no layer imports any module's infrastructure | `[tool.importlinter]` (ADR 0001) |
| Coverage, overall | 70% | `[tool.coverage.report] fail_under` |
| Coverage, domain and application | 85% across those files | `scripts/check_coverage.py` |

## Test layout

| Path | Contents |
|---|---|
| `apps/api/tests/` | API package tests (unit and, from P0-040, integration against real PostgreSQL and Redis) |
| `tests/` | Repository tooling tests (scripts) |

## Evidence that the gates bite

Each gate was proven with a deliberately seeded violation when it was introduced (P0-011, 2026-10-08): a domain module importing SQLAlchemy, a domain module importing its own application layer, a foreign module importing another module's infrastructure, a function of complexity 11, and an unannotated function. Each failed its gate; the clean tree passed.

## Still to come

Integration tests with real PostgreSQL and Redis (P0-040), cross-tenant endpoint harness (P0-054), frontend tests with Vitest, Playwright and axe (P0-083), end-to-end in CI (P0-103).
