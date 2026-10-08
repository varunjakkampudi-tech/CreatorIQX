# CreatorIQX Progress

Read this file at the start of every session. Update it at the end of every session (spec §0 rule 9).

| Field | Value |
|---|---|
| Last updated | 2026-10-08 |
| Spec | `CLAUDE.md`, MASTER BUILD SPEC Revision 2.5.1 (frozen; product name set to CreatorIQX) |
| Current phase | **Phase 0: Foundation, planning stage.** Plan and backlog written, awaiting owner approval. No implementation code written |
| Last PASS ticket | None |
| Open BLOCKED items | None yet. Three open owner questions (Q1 to Q3 below) will block specific tickets if unanswered when those tickets start |

## Owner questions (blocking specific tickets, not plan approval)

| ID | Question | Blocks |
|---|---|---|
| Q1 | GitHub repository: owner/name, and public or private? (On a private repo, CodeQL code scanning is, as far as known, a paid GitHub feature; verify current terms) | P0-001 (commit evidence), P0-100 to P0-103 (CI) |
| Q2 | Google Cloud project and an OAuth client for **login only** (scopes `openid email profile`): already exist, or should the agent provide step-by-step setup? Which email(s) go on the allow-list? | P0-052 (real login evidence) |
| Q3 | Where does implementation run (your computer through Claude Code, or this cloud workspace pushing to GitHub)? Your OS, Docker availability and RAM | P0-020 onward (anything run in Docker) |

## Decisions made

| Date | Decision | Source |
|---|---|---|
| 2026-10-08 | Product working name is **CreatorIQX**, held as a single config constant in `packages/config/product.json`, read by backend and frontend | Owner instruction |
| 2026-10-08 | Spec 2.5.1 is the frozen source of truth; architecture changes only via ADR plus owner approval | Spec status line, owner instruction |
| 2026-10-08 | Phase 0 backlog structured Phase -> Epic -> Capability -> Ticket, 13 epics, 45 tickets, in `docs/backlog/PHASE_0.md` | This plan |
| 2026-10-08 (proposed, pending approval) | Local dev uses a single origin via a Next.js `/api` rewrite; Caddy is introduced in Phase 1E as the spec plans. Fallback to Caddy `tls internal` locally if Secure cookies misbehave on `http://localhost` | Plan decision D7 |
| 2026-10-08 (proposed, pending approval) | Two Postgres roles: owner (migrations) and runtime app role with `NOBYPASSRLS` that does not own tables; RLS forced on every tenant table | Plan decision D4 |
| 2026-10-08 (proposed, pending approval) | First-login workspace bootstrap generates the workspace id in the app and runs under its own RLS context; no privileged bypass path | Plan decision D5 |
| 2026-10-08 (proposed, pending approval) | Time-box: Option B (defer P0-055, P0-061, P0-062, P0-070 to start of 1A), Phase 0 re-baselined to about 9 to 13 working days | Backlog totals section |

## Exact next step

Owner reviews the Phase 0 plan and backlog, answers Q1 to Q3, and approves (or amends) the plan and time-box option. After approval: start **P0-001** (repo docs bootstrap), then **P0-090** (wireframes) early, so wireframe approval is ready before UI tickets. Do not start Phase 1A.

## Phase 0 scorecard

Not yet run (runs in P0-110).
