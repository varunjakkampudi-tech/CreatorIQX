# CreatorIQX Progress

Read this file at the start of every session. Update it at the end of every session (spec §0 rule 9).

| Field | Value |
|---|---|
| Last updated | 2026-10-08 |
| Spec | `CLAUDE.md`, MASTER BUILD SPEC Revision 2.5.1 (frozen; product name set to CreatorIQX) |
| Current phase | **Phase 0: Foundation, implementation in progress** (plan approved by owner 2026-10-08) |
| Last PASS ticket | **P0-007** (all of E1 Governance and docs: P0-001 to P0-007 PASS) |
| Open BLOCKED items | None |
| Build environment | **Owner's Windows 11 machine** (`C:\Users\Admin\Desktop\creatoriqx`), driven through Claude Desktop Commander. Verified 2026-10-08: Git 2.56, Docker Desktop 29.8 (WSL2), Python 3.14, uv 0.12.23 (installed, on user PATH), Node 22.23, pnpm 12.5; npm, PyPI and Docker Hub reachable; 16 GB RAM. The earlier cloud workspace is retired (OQ-12, OQ-17) |
| Repository | `github.com/varunjakkampudi-tech/creatoriqx` (appears public, OQ-09). Pushing to `origin/main` works (OQ-16 resolved 2026-10-08) |

## Ticket log

| Ticket | Outcome | Evidence |
|---|---|---|
| P0-001 | PASS | Commit `083c204`; old-name grep count 0 |
| P0-005 | PASS | Commit `69fc663`; 16 questions; 0 `available` capabilities |
| P0-002 | PASS | Commit `0846bc0`; ADR template, index, 0001-0003; section check passed |
| P0-003 | PASS | Commits `060d8b5`, `5a88fc0`; ADRs 0004-0006 |
| P0-004 | PASS | Commit `060d8b5`; ADRs 0007-0009; section and capability checks passed |

## Owner actions pending

| ID | Action | Unblocks |
|---|---|---|
| OQ-15 | Reset the YouTube client secret shared in chat and paste the new one into `.env` (`YOUTUBE_CLIENT_SECRET`) | Phase 1A |
| — | Create the login-only Google OAuth client (ADR 0004); put its ID and secret in `.env` (`GOOGLE_LOGIN_CLIENT_ID`, `GOOGLE_LOGIN_CLIENT_SECRET`); redirect URI `http://localhost:3000/api/v1/auth/callback` | P0-052 |
| OQ-09 | Confirm the repo stays public (keeps CodeQL free) | P0-102 |

## Decisions made

| Date | Decision | Source |
|---|---|---|
| 2026-10-08 | Product working name is **CreatorIQX**, held as a single config constant in `packages/config/product.json` | Owner |
| 2026-10-08 | Spec 2.5.1 frozen; architecture changes only via ADR plus owner approval | Spec, owner |
| 2026-10-08 | Phase 0 plan and backlog approved (13 epics, 45 tickets) | Owner |
| 2026-10-08 | Agent kickoff prompt adopted (`docs/AGENT_KICKOFF.md`): autoshorts.ai and similar tools as UX inspiration only; no copying; guardrails win; CreatorIQX should feel like a creator operating system, not an admin dashboard | Owner |
| 2026-10-08 | Build runs in the cloud workspace for now | Owner |
| 2026-10-08 | Containers can't be pulled here: dev and tests use native Postgres and Redis; Compose and images run in GitHub Actions (OQ-12) | Environment finding |
| 2026-10-08 | Time-box Option B applied by default (defer P0-055, P0-061, P0-062, P0-070 to the start of 1A; Phase 0 about 9 to 13 days). Owner may switch to Option A | Plan recommendation, not yet explicitly confirmed |
| 2026-10-08 | Login uses a separate login-only Google client (ADR 0004, closes OQ-14) | Owner |
| 2026-10-08 | Build moved to the owner's Windows machine; `.env.example` committed, local `.env` created with generated secrets (gitignored) | Owner |
| 2026-10-08 | Windows has no native `make`: P0-010 uses a cross-platform task runner instead of a Makefile (same one-command setup) | Environment |
| 2026-10-08 | Plan decisions D1 to D11 in `docs/PHASE_0_PLAN.md` accepted with the plan | Owner |

## Exact next step

**P0-010**: monorepo skeleton (pnpm and uv workspaces, product config, task runner, `docs/DEPENDENCIES.md` with versions checked at install). Then P0-011, P0-013, P0-100. P0-090 (wireframes) can run in parallel. Do not start Phase 1A.

## Phase 0 scorecard

Not yet run (runs in P0-110).
