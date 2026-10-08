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

## JavaScript packages

| Package | Version | Checked on | Scope | Why |
|---|---|---|---|---|
| prettier | 3.9.9 (exact) | 2026-10-08 | root dev | Formatter; exact pin so formatting never shifts between machines |

## Python packages (dev group, root `pyproject.toml`)

| Package | Version | Checked on | Why |
|---|---|---|---|
| ruff | 0.16.10 | 2026-10-08 | Lint (incl. C901 complexity 10) and format |
| mypy | 2.4.0 | 2026-10-08 | Strict type checking |
| pytest | 9.1.1 | 2026-10-08 | Test runner |
| pytest-cov | 7.1.0 | 2026-10-08 | Coverage (70% overall via `fail_under`) |
| import-linter | 2.15 | 2026-10-08 | Architecture contracts (ADR 0001) |
| pre-commit | 4.6.2 | 2026-10-08 | Git hooks runner |

## pre-commit hooks (`.pre-commit-config.yaml`)

Pinned with `pre-commit autoupdate` on 2026-10-08.

| Hook repo | Version | Hooks |
|---|---|---|
| pre-commit/pre-commit-hooks | v6.0.0 | end-of-file, trailing whitespace, LF line endings, YAML/TOML/JSON syntax, merge conflicts, large files (500 KB), private keys |
| astral-sh/ruff-pre-commit | v0.16.10 | ruff check --fix, ruff format |
| gitleaks/gitleaks | v8.30.0 | secret scanning (built locally by pre-commit on first run) |
| local | (repo Prettier 3.9.9) | Prettier for JSON, YAML, JS, TS, CSS |
