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

## Python packages

None yet. Quality tooling (Ruff 0.16.10, mypy 2.4.0, pytest 9.1.1, pytest-cov 7.1.0, import-linter 2.15, pre-commit 4.6.2 were the latest on 2026-10-08) is added with P0-011 and P0-013, re-checked at that time.
