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
| `format` | Formats JSON, YAML and JS with Prettier |

More commands (lint, test, up, migrate) arrive with their tickets.

## Quickstart

Running the app end to end arrives with ticket P0-022 (one-command setup) and must take a new developer under 30 minutes.

## License

Proprietary. All rights reserved (to be confirmed by the owner).
