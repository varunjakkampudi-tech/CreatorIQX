# CreatorIQX Architecture

How CreatorIQX is put together, in [C4](https://c4model.com/) terms. Decisions behind it are in [`docs/adr/`](adr/README.md). The spec (`CLAUDE.md` §3) is the source of truth; this document explains it and must change in the same pull request as any structural change.

## Level 1: System context

Who uses CreatorIQX and which outside systems it talks to.

```mermaid
flowchart LR
    creator["Creator (owner)<br/>Plans, reviews and approves videos"]
    claude["Claude (owner's Pro subscription)<br/>Claude Code or Claude desktop"]
    subgraph boundary["CreatorIQX"]
        app["CreatorIQX platform<br/>Planning, scripts, QA, approval,<br/>YouTube sync, analytics"]
    end
    google["Google Identity<br/>OIDC login"]
    yt["YouTube Data and Analytics APIs<br/>Channel data, metadata sync"]
    studio["YouTube Studio<br/>Manual Private upload (v1)"]

    creator -->|"Uses (HTTPS, browser)"| app
    creator -->|"Uploads media manually"| studio
    claude -->|"Claims AI tasks, submits drafts (MCP)"| app
    app -->|"Login (OIDC, identity scopes)"| google
    app -->|"Reads data, applies approved changes (OAuth)"| yt
    studio -.->|"Same channel"| yt
```

| Element | Notes |
|---|---|
| Creator | The only user in v1; many creators, each in a workspace, from v2 |
| Claude | Runtime AI in v1 via the MCP bridge; it drafts, never publishes (ADR 0005) |
| Google Identity | Login only, `openid email profile` (ADR 0004) |
| YouTube APIs | Separate OAuth connection; every write capability gated by verified evidence (ADR 0007) |
| YouTube Studio | v1 media upload happens here, as Private (ADR 0007) |

## Level 2: Containers

The deployable pieces inside CreatorIQX and how they connect.

```mermaid
flowchart TB
    browser["Browser"]
    claudeclient["Claude Code / desktop"]

    subgraph cx["CreatorIQX"]
        web["Web app<br/>Next.js, React, TypeScript"]
        api["API<br/>FastAPI, Python<br/>Modular monolith (ADR 0001)"]
        worker["Worker<br/>Celery, Python<br/>Same domain code as API"]
        mcp["MCP server<br/>Python MCP SDK"]
        pg[("PostgreSQL 16+<br/>Row-level security (ADR 0002)")]
        redis[("Redis<br/>Sessions, broker, quota, rate limits")]
        store[("Object storage<br/>Local disk in dev, S3-compatible later")]
    end

    google["Google Identity"]
    yt["YouTube APIs"]

    browser -->|"HTTPS"| web
    web -->|"/api/v1, same origin (REST, SSE)"| api
    claudeclient -->|"MCP"| mcp
    mcp -->|"Read-only tools, draft submission"| api
    api --> pg
    api --> redis
    api --> store
    api -->|"Enqueue via TaskQueue (ADR 0003)"| redis
    redis -->|"Deliver jobs"| worker
    worker --> pg
    worker --> store
    api -->|"OIDC"| google
    worker -->|"OAuth, quota-checked (ADR 0009)"| yt
```

| Container | Responsibility | Key rules |
|---|---|---|
| Web app | UI; server-rendered shell; CSP with nonces | No business logic; calls the API only through the generated client |
| API | All business logic, organized by bounded context | Hexagonal layers per module; RLS context set per request |
| Worker | Background jobs: ingestion, sync, outbox relay, AI task leases | Jobs idempotent; same tenant context rules as the API |
| MCP server | Exposes app capabilities to the owner's Claude | Read-only by default; mutations only create drafts |
| PostgreSQL | System of record, including workflow state and audit log | Runtime role cannot bypass RLS or alter the audit log |
| Redis | Sessions, Celery broker, live quota counters, rate limits, progress pub/sub | Nothing here is the only copy of business state |
| Object storage | Thumbnails, transcripts files, media outputs | Behind a `StorageProvider` port; signed URLs |

**Open point:** whether the MCP server calls the API over HTTP (shown) or reads the database directly is decided by ADR when its first real tool is built (plan decision D11). The diagram shows the default.

## Level 3: Inside the API (module layout)

Each bounded context is a package with four layers. Arrows show allowed imports.

```mermaid
flowchart LR
    apiLayer["api<br/>FastAPI routers, schemas"]
    appLayer["application<br/>Use cases"]
    domLayer["domain<br/>Entities, ports, errors"]
    infraLayer["infrastructure<br/>SQLAlchemy, Redis, Celery, HTTP adapters"]

    apiLayer --> appLayer
    appLayer --> domLayer
    infraLayer --> appLayer
    infraLayer --> domLayer
```

Bounded contexts (spec §3), added only when a ticket needs them: `identity`, `workspaces`, `youtube`, `intelligence`, `content`, `transcripts`, `qa`, `publishing`, `analytics`, `comments`, `experiments`, `recommendations`, `ai_gateway`, `jobs`, `workflows`, `notifications`, `telemetry`, `audit`.

## Request lifecycle (authenticated API call)

1. Browser calls `/api/v1/...` on the same origin; the session cookie identifies a server-side session in Redis.
2. Middleware assigns a correlation id, enforces CSRF on unsafe methods and rate limits.
3. The handler opens one transaction, sets `app.workspace_id` and `app.user_id` with `SET LOCAL`, and calls an application use case.
4. The use case checks the role (owner, editor, viewer), works through ports, and writes audit and outbox rows in the same transaction.
5. Errors map to RFC 9457 problem+json; logs are JSON with the correlation id and no secrets.

## Phase status

Phase 0 builds: web app shell, API skeleton, `identity` and `workspaces` modules (workspaces is the reference module, P0-053), `audit`, a minimal `jobs` port with one Celery job, PostgreSQL and Redis, CI. Everything else on this page arrives in later phases.

## Sign-in and session flows (P0-051)

How a creator signs in, and how each later request is checked. The rules are in [ADR 0010](adr/0010-server-side-sessions-and-csrf.md); the login provider is in [ADR 0004](adr/0004-oidc-login-separate-from-youtube-oauth.md).

### Sign-in sequence

```mermaid
sequenceDiagram
    autonumber
    actor U as Creator (browser)
    participant API as CreatorIQX API
    participant R as Redis
    participant G as Google OIDC

    U->>API: GET /api/v1/auth/login
    API->>R: Store login flow (state, nonce, PKCE verifier), 10 min
    API-->>U: 302 to Google, sets flow cookie (HttpOnly, SameSite=Lax)
    U->>G: Authorize with openid email profile
    G-->>U: 302 to /api/v1/auth/callback with code and state
    U->>API: GET /api/v1/auth/callback (flow cookie)
    API->>R: Take login flow (single use, atomic)
    API->>G: Exchange code with PKCE verifier
    G-->>API: ID token
    API->>API: Check issuer, audience, expiry, nonce, signature, email_verified, allow-list
    API->>R: Delete previous session, if any
    API->>R: Store new session, absolute TTL 12 h
    API-->>U: 303 to the app, sets session cookie, clears flow cookie
```

### Checking each request

```mermaid
flowchart TD
    req["Request with session cookie"] --> exists{"Session in Redis?"}
    exists -- no --> r401["401 session-required"]
    exists -- yes --> live{"Inside idle and absolute limits?"}
    live -- no --> drop["Delete session"]
    drop --> r401e["401 session-expired"]
    live -- yes --> touch["Record activity, restart idle timer"]
    touch --> unsafe{"Unsafe method?"}
    unsafe -- no --> handle["Handle request"]
    unsafe -- yes --> csrf{"X-CSRF-Token matches?"}
    csrf -- no --> r403["403 csrf-token-invalid"]
    csrf -- yes --> handle
```

## First-login bootstrap (P0-053)

The first successful Google login creates the person, their personal workspace and the owner membership, in one transaction, before the session is issued. The rules are in [ADR 0011](adr/0011-workspace-bootstrap-at-first-login.md). Repeat logins resolve the same ids and create nothing.

### Bootstrap sequence

```mermaid
sequenceDiagram
    autonumber
    participant Cb as /auth/callback
    participant BS as WorkspaceBootstrapService
    participant ST as SqlPersonalWorkspaceStore
    participant PG as PostgreSQL (runtime role, forced RLS)
    participant SS as SessionService
    Cb->>BS: ensure_personal_workspace(subject, email)
    BS->>BS: normalise email, generate UUIDv7 ids
    BS->>ST: ensure(BootstrapCommand)
    ST->>PG: BEGIN, then pg_advisory_xact_lock(subject)
    ST->>PG: find users by google_sub
    alt first login
        ST->>PG: INSERT users (context: no workspace)
        ST->>PG: INSERT audit_log user.created (context: no workspace)
    end
    ST->>PG: find owner membership (context: user)
    alt no workspace yet
        ST->>PG: INSERT workspaces and flush first (context: new workspace)
        ST->>PG: INSERT memberships and outbox_events (context: new workspace)
        ST->>PG: INSERT audit_log workspace.created (context: new workspace)
    end
    ST->>PG: INSERT audit_log auth.login_succeeded (context: workspace)
    ST->>PG: COMMIT
    ST-->>BS: BootstrapResult(user_id, workspace_id, flags)
    BS-->>Cb: result
    Cb->>SS: rotate(previous, subject, email, user_id, workspace_id)
    SS-->>Cb: session bound to the tenant
```

### Tenant context while bootstrapping

```mermaid
flowchart TD
    start["Login callback verified by Google"] --> lock["Advisory lock on the Google subject"]
    lock --> known{"User already exists for this subject?"}
    known -- no --> email{"Email bound to another subject?"}
    email -- yes --> conflict["409 identity-conflict, nothing written"]
    email -- no --> mkuser["Create user, audit user.created under NO_WORKSPACE"]
    known -- yes --> member
    mkuser --> member{"Owner membership exists?"}
    member -- no --> mkws["Insert workspace first, then owner membership and outbox workspace.created, under the NEW workspace id"]
    member -- yes --> reuse["Reuse its workspace id, create nothing"]
    mkws --> audit["Audit auth.login_succeeded under the workspace"]
    reuse --> audit
    audit --> commit["COMMIT, then issue the session with user_id and workspace_id"]
```

## Authorization on every request (P0-054)

One gate stands in front of tenant data. A route declares the role it needs; the
gate resolves the workspace and user from the session, re-checks membership, and
hands the route a verified `WorkspaceAccess`. The rules are in
[ADR 0012](adr/0012-rbac-in-the-application-layer-with-a-route-harness.md).

```mermaid
flowchart TD
    req["Request with a session cookie"] --> sess{"Live session?"}
    sess -- no --> r401["401 session-required"]
    sess -- yes --> unsafe{"Unsafe method?"}
    unsafe -- yes --> csrf{"X-CSRF-Token matches?"}
    csrf -- no --> r403c["403 csrf-token-invalid"]
    csrf -- yes --> gate
    unsafe -- no --> gate{"require_role: membership in the session's workspace?"}
    gate -- none --> r403["403 insufficient-role"]
    gate -- "role too low" --> r403
    gate -- ok --> rls["Query under app.workspace_id and app.user_id"]
    rls --> handler["Route handler, with a verified WorkspaceAccess"]
```

The two layers are independent on purpose. `require_role` refuses the request
before any work happens and can express a role requirement; row-level security
cannot express roles but stops a query that slips past the gate from reading
another tenant's rows.

### Why the harness enumerates routes

A per-route check is only as reliable as the next person adding a route, so the
cross-tenant harness reads the OpenAPI document rather than a list of routes. It
signs in a user whose session names workspace A while holding no membership there,
and requires every documented route to refuse. A route added later is covered as
soon as it appears; exempting one is an explicit entry with a reason, and a seeded
unprotected route is asserted to make the harness fail.

```mermaid
flowchart LR
    doc["app.openapi() paths"] --> split{"In EXEMPT?"}
    split -- yes --> reason["Skipped, with a recorded reason"]
    split -- no --> probe["Call as a non-member of the session's workspace"]
    probe --> judge{"401, 403 or 404?"}
    judge -- yes --> ok["Isolated"]
    judge -- no --> fail["Harness fails: tenant isolation hole"]
```

## Frontend foundation (P0-080)

`apps/web` is a Next.js App Router app, not yet any product screen. Spec
section 11's named UI screens (onboarding, the video board, the Video
Workspace, the approval diff, YouTube Sync) wait on P0-090's written
wireframe approval; this ticket is the app shell and design tokens those
screens will be built on, so it does not touch that gate.

Design tokens (color, the 8px spacing grid, type scale, radius, motion) are
CSS custom properties defined once in `src/app/globals.css`, each mapped to a
Tailwind v4 `@theme` utility (`bg-surface`, `text-ink`, ...). Light values
live on `:root`; dark values override the same properties under
`prefers-color-scheme: dark` (unless `data-theme="light"` is forced) and
under an explicit `data-theme="dark"`, so a component's class never changes
between themes — only what the token resolves to does. A component reaches
every color through a token utility; a lint rule
(`eslint.config.mjs`, `no-restricted-syntax` on hex-literal nodes) forbids a
raw hex literal anywhere in `src/**/*.ts(x)`, so the only way to add a color
is to add a token.

```mermaid
flowchart LR
    comp["Component className=\"bg-surface\""] --> theme["@theme: --color-surface: var(--surface)"]
    theme --> root[":root { --surface: #fff }"]
    theme --> dark["prefers-color-scheme: dark or data-theme=dark { --surface: #0b1220 }"]
    lint["eslint no-restricted-syntax"] -. blocks .-> hex["className=\"bg-[#4f46e5]\""]
```

`cn()` (`src/lib/utils.ts`, clsx + tailwind-merge) and `components.json` are
the shadcn/ui-style init; no component primitives exist yet (P0-083 adds
Button/Input/Card/Skeleton). `next.config.ts` rewrites `/api/*` to the local
FastAPI backend so the dev server runs on a single origin. The product name
comes from `@creatoriqx/config/product.json`, read by both this app and the
API, never hard-coded in either.
