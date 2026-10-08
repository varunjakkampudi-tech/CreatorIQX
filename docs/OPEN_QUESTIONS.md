# Open Questions

Unverified facts and pending decisions. Rule (spec §0.3): prefer official documentation; when ambiguous, take the conservative path and record it here. An item closes only with a source link and a verification date.

**Status values:** Open, Verified, Decided, Superseded.

## YouTube and Google (seeded from spec §3)

| ID | Question | Conservative assumption until verified | Source to check | Needed by | Status |
|---|---|---|---|---|---|
| OQ-01 | Does `videos.insert` from an unverified API project (created after 28 July 2020) still restrict uploads to private until a compliance audit? What is this project's actual status? | Restricted; `direct_video_upload` stays disabled | YouTube Data API `videos.insert` docs; API Services audit page; Google Cloud console | 1D | Open |
| OQ-02 | Can a video locked private by that restriction later be made public? | Unknown either way; never promise it | Same as OQ-01 | 1D | Open |
| OQ-03 | What makes a channel eligible for custom thumbnails (`thumbnails.set`)? | Verify at runtime per channel; never hard-code | YouTube Help; `thumbnails.set` docs | 1D | Open |
| OQ-04 | Current quota costs per method and default daily quota | Use documented costs at implementation time; ledger records actual cost | YouTube Data API quota calculator | 1A | Open |
| OQ-05 | Refresh-token lifetime and consent-screen limits for an OAuth app in Testing versus unverified production | Tokens in Testing may expire after about 7 days; build a clear reconnect flow | Google OAuth 2.0 docs ("Testing" publishing status) | 1A | Open |
| OQ-06 | Exact minimum OAuth scope for each write capability (`metadata_update`, `thumbnail_update`, `scheduling`, `comment_reply`, `direct_publish`, `direct_video_upload`) | Request nothing beyond read-only until each is verified | YouTube Data API scopes page; per-method docs | 1D | Open |
| OQ-07 | Exact conditions for setting `status.publishAt` on a manually uploaded video | Only private and never-published videos; otherwise manual-apply | `videos` resource docs, `status.publishAt` | 1D | Open |

## Platform and tooling

| ID | Question | Conservative assumption until verified | Source to check | Needed by | Status |
|---|---|---|---|---|---|
| OQ-08 | Do Anthropic's current usage terms and Pro plan limits allow an automated loop processing `ai_tasks` through Claude Code? | No unattended loop; owner starts each run | Anthropic consumer terms and usage policy; Claude Code docs | Before any `make ai-run` loop | Open |
| OQ-09 | Code scanning (CodeQL) licensing for this repo | Repo appears **public** (anonymous `git ls-remote` succeeded on 2026-10-08), so CodeQL is expected to be free. Owner to confirm the repo stays public; if it goes private, decide: paid GitHub feature or an ADR for a free alternative | GitHub code scanning docs; repo settings | P0-102 | Open (owner to confirm) |
| OQ-10 | Do target browsers accept `Secure` and `__Host-` cookies on `http://localhost`? | Use them; if a target browser rejects them, fall back to local Caddy with `tls internal` | Browser docs (Chrome, Firefox, Safari secure-context rules) | P0-051 | Open |
| OQ-11 | Which OIDC library (for example Authlib) best fits FastAPI with PKCE, nonce and JWKS validation, at its current version? | Choose only a maintained library with PKCE and ID token validation; record the version | Library docs and changelog | P0-050 | Open |

## Environment findings (2026-10-08)

| ID | Question | Conservative assumption until verified | Source to check | Needed by | Status |
|---|---|---|---|---|---|
| OQ-12 | The cloud build workspace cannot pull container images (Docker Hub, GHCR, ECR Public, GCR mirror and Quay are all denied by network policy). How do Docker-dependent tickets get evidence? | Dev and tests use the native PostgreSQL 16 and Redis 7 already installed; Compose and Dockerfiles are syntax-checked locally and actually run in GitHub Actions, which provides the evidence | Workspace proxy status, 2026-10-08 | P0-020, P0-021, P0-022, P0-103 | Decided (pending owner acknowledgement) |
| OQ-13 | Real Google login (P0-052) needs the owner's browser to reach the app. A cloud workspace's `localhost` is not reachable from the owner's browser | P0-052 stays BLOCKED until the app runs on the owner's computer or a hosted URL | — | P0-052 | Open |
| OQ-14 | The owner provided a Google OAuth client labeled for YouTube. Should login reuse that client, or use a separate login-only client? | Separate clients (spec keeps the flows separate; a login client never needs YouTube scopes). Reuse only by owner decision recorded in ADR 0004 | ADR 0004 | P0-050 | Open (owner decision) |
| OQ-15 | That client secret was shared in a chat transcript | Treat it as exposed: rotate before use; store the new value only in a gitignored `.env`; never in the repo, the Project or logs | Google Cloud console | Before P0-052 | Open (owner action) |
| OQ-16 | GitHub is not yet linked to Claude, so this workspace cannot push | Commit locally; push once linked | claude.ai GitHub connection | P0-100 | Open (owner action) |
