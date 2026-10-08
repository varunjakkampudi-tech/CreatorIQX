# MASTER BUILD PROMPT: CreatorIQX

> **Status: frozen at Revision 2.5.1** (product working name set to CreatorIQX on 2026-10-08, naming only, no content or architecture change; 2.5.1 is a corrective release with no architecture changes: YouTube write scopes separated from the upload scope, manual uploads made as Private so API scheduling works, the capped API mode disabled by default in v1, and the Phase 0 time-box and security-scan timing made realistic; 2.5 consolidates the full analysis: agent-neutral wording, session continuity, indicative time-boxes, a hosted-deployment phase, a risk register, an initial ADR list and a design-first rule, with no architecture changes; 2.4 is a corrective release: YouTube publishing capability model and sync state, transcripts promoted to Core, phase order and tiers made consistent, evidence required on tickets; 2.3 adds binary ticket outcomes, a phase quality gate, stricter accessibility checks and extra release rows; 2.2 adds the Quality Scorecard, feature tiers, AI execution modes with a spend cap, and a gate decision rule; no architecture changes). Further architecture changes only through an ADR with a concrete need.
>
> **Revision 2.1:** adds OIDC login vs separate YouTube OAuth, approval invalidation rule, AI task leasing and v1 task experience, evidence strength and source immutability, table ownership, token audit events, Phase 0 depth rule and backlog structure.
>
> **Revision 2:** incorporates review feedback (separate version artifacts and publish snapshots, shared recommendations model, provenance on Channel Profile learnings, durable quota ledger, job states and workflows, task-based navigation, Phase 1 split into 1A-1D, scope guardrails).
>
> Paste this whole file into your coding agent (Claude Code, Codex or similar) at the start of the project (or save it as `CLAUDE.md` / `AGENTS.md` / `docs/SPEC.md` in the repo root so every session sees it). Then say: **"Start with Phase 0."**

---

## 0. ROLE AND WORKING AGREEMENT

You are a principal engineer, system architect, security engineer and senior product designer building a production-grade SaaS. Build it like a professional product that real paying users will trust with their YouTube channels.

Working rules, for every task:

1. **Plan before code.** For each phase, first reply with a short plan (files, decisions, risks), then implement.
2. **Small steps.** Small commits, conventional commit messages, tests with every change. Never dump the whole system in one go.
3. **Verify, don't guess.** Check the *current* official docs for YouTube Data API v3, YouTube Analytics API, Google OAuth and every library before using them. Check the latest stable version of each dependency at install time instead of relying on memory. If something is uncertain, say so and add it to `docs/OPEN_QUESTIONS.md`. Prefer official documentation over blog posts or third-party guides. If official documentation is ambiguous, implement the conservative path and record the uncertainty.
4. **Record decisions.** Every significant decision gets an ADR in `docs/adr/`.
5. **Definition of Done** for any task: code, tests passing, lint and type checks clean, docs updated, security considerations noted.
6. **Ask before** choices that are expensive to reverse (data model changes, auth model, paid services).
7. **Flag assumptions** at the end of every response.
8. **Ticket outcomes are binary.** Every ticket ends as exactly one of: **PASS** (implementation, tests, evidence, documentation and security consideration all exist), **BLOCKED** (an external dependency prevents completion, and the evidence names it), or **FAIL** (the requirement is not met). Never report "mostly complete" or "95% done" while tests fail. Never close a ticket because the code exists.
9. **Session continuity.** Usage limits and long projects mean sessions end unexpectedly. Maintain `docs/PROGRESS.md` (current phase, last PASS ticket, open BLOCKED items, decisions made, exact next step). Read it at the start of every session and update it at the end. Keep each session to one or a few small tickets.

---

## 1. PRODUCT

**Working name:** CreatorIQX (configurable; make the name a single config constant so it can change without code edits).

**Purpose:** Help YouTube creators plan, create, quality-check, publish and learn from videos and Shorts, using their own channel data and AI assistance, with a human approval step before anything is published.

**Primary user (v1):** one creator (the owner), running locally.
**Future users (v2):** many creators, each with their own workspace, no codebase redesign needed.

**V1 media assumption:** V1 Core assumes that the creator can provide a finished or near-finished source video by the time the publishing workflow is reached. Full AI video generation and advanced automatic editing are not required to complete the Core workflow. The system assists with planning, scripts, transcripts, metadata, chapters, QA, approval and YouTube synchronization. Media automation is an optional later capability.

### Non-negotiables

| Area | Requirement |
|---|---|
| UI and UX | Polished, modern, fast, accessible, guided. It must feel like a professional SaaS, not an internal tool |
| End-user friendliness | A creator with no technical background can connect a channel and get value in under 5 minutes |
| Code quality | Clean, typed, tested, documented, consistent, easy to change |
| Security | Secure by default. Least privilege, encrypted secrets, strict tenant isolation |
| Scalability | v1 single-user but v2 multi-user with no redesign |
| Honesty | The product never promises virality or guaranteed reach |

### Policy and ethics guardrails (hard rules)

- Use only official APIs. No scraping of YouTube or of any third-party tool.
- No fake engagement, botting, view manipulation, mass-produced spam content, or deceptive clickbait. Do not generate content designed to break YouTube policies.
- Every AI-generated public action (publish, reply, upload) requires explicit human approval.
- Support YouTube's disclosure for realistic altered or synthetic content if the API exposes it.
- Virality and retention features give *estimates with confidence levels*, never guarantees.

---

## 2. CONSTRAINTS AND BUDGET

| Constraint | Detail |
|---|---|
| AI budget (v1) | Claude Pro subscription only (about ₹2300/month). No Anthropic API spend in v1 by default. The capped API mode (section 9, Mode B) is built behind the interface but stays disabled until the owner enables it through an ADR |
| Server cost | Owner pays for a Hostinger VPS later |
| v1 runtime | Runs locally on the owner's machine via Docker Compose |
| v2 runtime | Hostinger VPS (Ubuntu LTS, Docker, Caddy) |
| Team | One developer plus a coding agent (Claude Code, Codex or similar) |
| vidIQ | No public developer API has been confirmed. Treat vidIQ as an **optional, unverified adapter**. Never scrape it. Check its terms first |
| YouTube publishing | A new, unaudited API project cannot be assumed to upload publicly visible videos. Direct upload is capability-gated and off by default. See the capability model in section 3 |

### Build agent vs runtime AI provider (keep these separate)

Any coding agent (Claude Code, Codex, or another) can build this project. The build agent is **not** an architectural dependency. The runtime AI provider is a different concern (MCP bridge, Anthropic API, another API, or a local model) and always sits behind the `LLMProvider` interface. Keep agent-specific wording confined to `/skills` and the MCP server docs.

### The AI strategy that fits the budget (important design point)

A Claude Pro subscription cannot be called as an API by the app. So:

- **v1:** the app exposes its capabilities through an **MCP server** and a set of **Claude Skills** (`/skills/<module>/SKILL.md`). The owner uses Claude Code or Claude desktop (included with Pro) as the "AI brain". The web UI creates `ai_tasks`; Claude picks them up via MCP tools, does the work, and writes results back for review in the UI. This is the default and only enabled mode in v1.
- **v2:** a second provider implementation calls the Anthropic API (billed per use) behind the **same interface**. Switching providers must be a config change, not a rewrite. The adapter may be built and tested earlier, but it ships disabled.

---

## 3. ARCHITECTURE

### Style
**Modular monolith**, hexagonal (ports and adapters), event-driven internally. One deployable backend, one worker, one web app, one MCP server. Do **not** use microservices. Each module is a bounded context that could be extracted later.

### Flow

```
Sources: YouTube Data/Analytics/Reporting APIs, keyword adapter (optional)
  -> Data layer (PostgreSQL + Redis) -> Channel Profile (versioned, editable)
  -> INTELLIGENCE: research, planner, virality, SEO, audit
  -> CREATION: transcript, script, SEO, chapters, thumbnail preview (edit, shorts, advanced thumbnails later)
  -> PRE-PUBLISH QA: title, SEO, chapters, hook (failures loop back to Creation)
  -> APPROVAL GATE (state machine, diff view)
  -> APPLY TO YOUTUBE (sync the approved snapshot; direct upload only if audited)
  -> POST-PUBLISH: retention, comments, experiments
  -> LEARNINGS (with confidence scores) -> Channel Profile

Cross-cutting: auth and tenancy, AI gateway, job queue, audit log,
notifications, observability, quota ledger
```

### Video state machine

`idea -> planned -> drafting -> qa -> in_review -> approved -> scheduled -> published -> analyzed` with allowed transitions enforced in the domain layer, plus `rejected` and `archived`. Every transition writes an audit log entry and emits a domain event.

**Approval invalidation (domain invariant):** approval freezes an immutable `publish_snapshot`. Any change to a publish-bound artifact after approval does NOT mutate the snapshot. The video returns to `in_review`, and a new approval creates a new snapshot. The UI must say clearly which version is approved and which is pending.

### YouTube publishing capability model

The app must not assume that a newly created, unaudited Google API project can upload publicly visible videos through `videos.insert`. Google's documentation (verify the current text before relying on it) says uploads from unverified API projects created after 28 July 2020 are restricted to private viewing until the project passes a compliance audit. Treat every YouTube write operation as a **capability** with recorded evidence.

| Capability | Meaning |
|---|---|
| `metadata_update` | Update managed video metadata (title, description, tags, category, disclosure fields) |
| `thumbnail_update` | Set a custom thumbnail |
| `scheduling` | Set a scheduled publish time (`status.publishAt`) where allowed |
| `comment_reply` | Post approved comment replies |
| `direct_video_upload` | Upload media through `videos.insert` |
| `direct_publish` | Change privacy or publication state through the API where permitted |

Each capability resolves to one of: `available`, `restricted`, `unsupported`, `requires_audit`.

Rules:

- Persist capability evidence per capability: `capability`, `status`, `verified_on`, `source_url`, `required_scopes`, `verification_notes`. **Refuse to enable any write capability without recorded verification evidence.**
- Record the exact OAuth scope each capability needs (verify against current docs). Write capabilities such as `metadata_update`, `thumbnail_update`, `scheduling` and `comment_reply` need a YouTube **write** scope, not only the upload scope. Request each scope only when the capability that needs it is enabled.
- `YOUTUBE_DIRECT_UPLOAD_ENABLED=false` by default. It is not a toggle that bypasses policy: it may be enabled only after the required Google and YouTube conditions are verified and recorded. Tests must prove an unaudited project cannot reach the disabled direct-upload path.
- Never claim direct public upload works until verified against current official documentation and the actual project status.
- After every write, read the remote resource back and verify the actual state.
- `videos.update`: read the current resource first and send back every mutable field that must be preserved, because omitted mutable fields can be deleted (verify in the official docs).
- Discover manually uploaded videos through the channel's uploads playlist (`channels.contentDetails.relatedPlaylists.uploads` plus `playlistItems.list`), not `search.list`.
- Custom-thumbnail eligibility is a capability verified at runtime and against current docs, never a hard-coded assumption.
- Scheduling through `status.publishAt` is expected to work only on a video that is **private and has never been published** (verify against current docs). The app must check the linked video's privacy and publication state before offering API scheduling, and fall back to manual-apply guidance otherwise.
- Chapters follow YouTube's rules (starts at `00:00`, at least 3 timestamps, ascending, each chapter at least 10 seconds). Verify against current YouTube Help.
- Before implementing any YouTube write operation: check current official documentation for quota rules, audit and compliance requirements, required scopes, and whether the project's verification state imposes restrictions. Record findings in `docs/YOUTUBE_CAPABILITIES.md`. Seed `docs/OPEN_QUESTIONS.md` with: (1) the `videos.insert` audit restriction and the project's actual status, (2) whether a video locked private by that restriction can later be made public (unverified, assume neither answer), (3) custom-thumbnail eligibility, (4) current quota costs, (5) refresh-token lifetime and consent-screen limits for an OAuth app in Testing versus unverified production status (as far as known, tokens in Testing mode can expire after about 7 days; verify), (6) the exact minimum scope for each write capability, (7) the exact conditions under which `status.publishAt` can be set on a manually uploaded video.

**Default V1 publishing workflow (unaudited project):**

```
Creator prepares a finished or near-finished video
  -> uploads the media manually in YouTube Studio as PRIVATE
     (not Public or Unlisted, so API scheduling stays possible)
  -> app discovers or links the YouTube video
  -> app compares current YouTube metadata with the approved publish snapshot
  -> app applies allowed approved changes through official APIs
     (title, description, tags and category where supported, chapters via the
      description, thumbnail, disclosure fields, scheduling where permitted)
  -> sync status is recorded and read back
  -> any later external change is detected as drift
```

Direct upload through `videos.insert` stays optional and capability-gated. **Manual-apply fallback** for any restricted capability: copy buttons for title, description and chapters, a downloadable thumbnail asset, and guidance for applying them in YouTube Studio (including setting the schedule manually when API scheduling is not possible). Phase 1D must PASS without direct API media upload.

### YouTube synchronization state (separate from the video state machine)

The video lifecycle state machine above is unchanged. A separate sync state tracks the link to YouTube: `not_linked`, `linked`, `pending_sync`, `synced`, `drift_detected`, `sync_failed`.

- Store the external YouTube video ID when linked. Verify the video belongs to the connected channel. Enforce uniqueness on `(workspace_id, youtube_video_id)`.
- Record every attempt as a per-operation row (`sync_operations`), not only a global status, so partial failure (title synced, thumbnail failed) is visible. Store `applied_snapshot_id`, remote `etag`, operation status, error details, quota cost and timestamps.
- Sync reads only an immutable approved `publish_snapshot`, never "latest".
- Drift detection: compare normalized managed fields (whitespace, tag casing, entities) to avoid false positives.
- Drift resolution, always explicit: **adopt remote** (creates a new local version that goes through review and approval), **overwrite remote** (requires a new approval), or **ignore** (drift stays flagged). External drift never silently redefines the approved snapshot and the app never silently overwrites external changes.
- The UI shows the approved local version, the current YouTube version, the differences, the last successful sync, and whether drift exists.

### Modules (bounded contexts)

`identity`, `workspaces`, `youtube` (connection, API adapters, capability model, sync), `intelligence` (research, planner, virality, SEO, audit), `content` (script, thumbnail, edit, shorts, chapters), `transcripts`, `qa`, `publishing`, `analytics` (retention, snapshots), `comments`, `experiments`, `recommendations`, `ai_gateway`, `jobs`, `workflows`, `notifications`, `telemetry`, `audit`.

Rules: each table has exactly one owning bounded context. Other modules may consume it only through the owner's public interface or domain events (for example, `publishing` must never write to `content.script_versions`). Modules never reach into each other's tables. Dependencies point inward (domain has no framework imports).

---

## 4. FEATURES (with acceptance criteria)

| # | Module | Must do | Acceptance |
|---|---|---|---|
| 1 | Channel connect and onboarding | Login (OIDC) first, then a separate YouTube OAuth connection with incremental scopes (read-only first; write scopes only when the user enables sync or publishing; upload scope only if direct upload is enabled), 3-step wizard, builds first Channel Profile | New user reaches first insight in under 5 minutes |
| 2 | Audit | Channel health score, best and worst videos, gaps, quick wins | Every finding shows evidence and a suggested action |
| 3 | Research | Topic and niche ideas from the user's own data and public data via official APIs | Each idea shows source, confidence and stored provenance (URL, source type, retrieved_at, excerpt or hash) |
| 4 | Planner | Calendar and backlog, series and topic clusters, drag and drop | Plans persist and can become Video records in one click |
| 5 | Script | Hook, outline, full script in the channel's voice, multiple variants, versioned | Edit and compare versions, restore any version |
| 6 | Thumbnail | Template-based preview and download (Core packaging infrastructure). Advanced concepts, generation and A/B variants are Could | Preview at real feed sizes. No claim of AI image generation unless a provider is configured |
| 7 | Edit | Silence removal, captions, jump cuts with FFmpeg (uses the shared transcripts module) | Non-destructive: originals kept, outputs versioned |
| 8 | Shorts | Clip suggestions from long videos, vertical reframe, captions, safe areas | User approves each clip before upload |
| 9 | SEO | Titles, descriptions, tags, keywords, with character limits and truncation preview | Multiple options, each with rationale |
| 10 | Chapters | Timestamped chapters generated from a transcript version (feature 22) | Editable before publish. Records the transcript version used. Validated against YouTube chapter rules |
| 11 | Virality score | Estimate from the channel's own history | Score plus confidence plus drivers. Never a guarantee |
| 12 | Pre-publish QA | Checklist: title, hook, SEO, chapters (start at 00:00, at least 3, ascending, at least 10 s each), thumbnail, disclosure flags, and a schedule check (warn if scheduling is requested but the linked video is not private and unpublished) | Failed checks return to Creation with specific fixes |
| 13 | Approval gate | Diff view of exactly what will change on YouTube | Approval freezes an immutable publish snapshot. Nothing is published without approval |
| 14 | Publish / Apply to YouTube | Link or discover the video, then apply approved metadata, chapters (via description), thumbnail, disclosure fields and schedule from the immutable snapshot, per capability. Direct `videos.insert` upload is optional and capability-gated | Idempotent, retry-safe, quota-aware. Read-back verification after every write. Drift detected, never silently overwritten. Manual-apply fallback when a capability is restricted |
| 15 | Retention | Retention curves, drop-off detection, fix suggestions | Works from the Analytics API for the user's own channel |
| 16 | Comments | Inbox, triage, drafted replies, bulk approve | Replies are never posted without approval. Spam filtering. Quota-aware |
| 17 | Experiments | Title and thumbnail tests across videos or time windows | Shows sample size and statistical caveats. Never declares winners on noise |
| 18 | Learnings | Updates Channel Profile from results | Each learned attribute stores value, source, confidence, sample size, observed period and a manual-override flag. Versioned, editable, user can undo. Weak correlations never become facts |
| 19 | Notifications | In-app (email optional) for job done, approval needed, quota low | Preferences per user |
| 20 | Settings | Connections, workspace, members and roles, security, data export and deletion | One-click disconnect that revokes tokens |
| 21 | Recommendations | One shared inbox of AI suggestions from every module | Each shows evidence, confidence and sample size. Accept and dismiss are tracked |
| 22 | Transcripts | Shared transcript module with four sources behind one abstraction: import available caption data through permitted YouTube APIs, upload a transcript file, paste text, or transcribe locally with faster-whisper. Versioned segments with timestamps, language, source and confidence where available | Chapters can be generated without Edit existing. All four sources use the same abstraction. Downstream outputs record the exact transcript version used. Local transcription is built and time-boxed but is not a PASS blocker for Phase 1C |

**Feature tiers (scope control).** Build in this order and do not start a lower tier before the higher tier passes its scorecard.

| Tier | Features |
|---|---|
| Core | 1 Connect, 2 Audit, 4 Planner, 5 Script, 22 Transcripts, 9 SEO, 10 Chapters, 12 QA, 13 Approval, 14 Publish / Apply to YouTube, 20 Settings, 21 Recommendations (template-based thumbnail preview is Core packaging infrastructure) |
| Should | 3 Research, 15 Retention, 16 Comments, 18 Learnings, 19 Notifications |
| Could | 6 Advanced thumbnail generation and testing, 7 Edit, 8 Shorts, 11 Virality, 17 Experiments |

---

## 5. TECH STACK

Use the latest stable versions at install time. Pin them with lockfiles.

| Layer | Choice |
|---|---|
| Monorepo | pnpm workspaces for JS, uv for Python |
| Frontend | Next.js (App Router) + React + TypeScript (strict) |
| Styling and UI | Tailwind CSS, shadcn/ui on Radix primitives, lucide icons, design tokens |
| Data fetching | TanStack Query, generated API client from OpenAPI |
| Forms and validation | React Hook Form + Zod |
| Charts | Recharts or visx |
| i18n | next-intl (prepared, English first) |
| Frontend testing | Vitest, Testing Library, Playwright, axe-core, Storybook |
| Backend | Python 3.12+, FastAPI, Pydantic v2 |
| ORM and migrations | SQLAlchemy 2 (async), Alembic |
| Database | PostgreSQL 16+ with row-level security |
| Cache, queue, realtime | Redis (cache, rate limits, quota counters, locks, Pub/Sub for progress) |
| Background jobs | Celery with Redis broker, behind a `TaskQueue` interface |
| Realtime to UI | Server-Sent Events for job progress |
| Storage | `StorageProvider` interface: local disk in dev, S3-compatible (MinIO or Cloudflare R2) in production |
| Media | FFmpeg, faster-whisper (serves the shared transcripts module) |
| AI | `LLMProvider` interface. v1: MCP bridge. v2: Anthropic API |
| MCP | Official Python MCP SDK, exposing app tools to Claude |
| Observability | structlog (JSON), OpenTelemetry, Prometheus metrics, Sentry (optional), product usage events (feature use, recommendation accepted or dismissed, QA failure types, job completion time, time to publish) |
| Quality tooling | Ruff, mypy (strict), pytest, ESLint, Prettier, pre-commit |
| CI/CD | GitHub Actions |
| Containers | Docker multi-stage builds, Docker Compose |
| Proxy and TLS | Caddy (automatic HTTPS) |

---

## 6. SYSTEM DESIGN CONCEPTS TO APPLY

| Concept | How |
|---|---|
| Multi-tenancy | `workspace_id` on every tenant table. PostgreSQL RLS set per request. Cross-tenant tests required |
| Stateless services | All state in Postgres, Redis, object storage |
| Idempotency | `Idempotency-Key` header on mutating endpoints. Jobs safe to retry |
| Queue and retries | Exponential backoff with jitter, dead-letter handling, visibility into failures |
| Quota management | Redis for live atomic reservation and pre-flight checks per workspace per day. Every call also writes a usage event to the durable `quota_ledger` in Postgres, so history survives a Redis flush. Graceful degradation on exhaustion |
| Workflows | Domain-level `Workflow` and `WorkflowStep` (including pauses for user selection) sit above raw jobs. Celery is only the execution engine. Keep it lightweight: no external workflow engine in v1 |
| Caching | Cache analytics and AI results by content hash with sensible TTLs. Explicit invalidation |
| Rate limiting | Redis token bucket per user and per IP |
| Event-driven | Domain events for state changes (outbox pattern for reliability) |
| Optimistic concurrency | Version column on editable aggregates |
| Pagination | Cursor-based |
| Resilience | Timeouts, circuit breakers on external APIs, bulkheads between job types |
| Feature flags | Simple config-based flags (for v2 rollout, billing, API execution mode) |
| Graceful degradation | UI stays usable if AI or YouTube is down |
| Backpressure | Queue length limits and per-workspace concurrency caps |

---

## 7. DATA MODEL (starting point, refine with ADRs)

UUIDv7 ids, `created_at`, `updated_at`, soft delete where needed, `workspace_id` on all tenant data.

**Identity:** `users`, `workspaces`, `memberships (role)`, `oauth_connections (encrypted tokens, scopes)`, `channels`.

**Video aggregate.** Artifacts are versioned independently. Never use one giant "video version" row.

| Table | Purpose |
|---|---|
| `videos` | Identity, current state-machine status, pointers to the current version of each artifact |
| `script_versions` | Script text, variant label, author (human or AI), parent version |
| `metadata_versions` | Title, description, tags, category, disclosure flags |
| `thumbnail_variants` | Template, text, rendered asset ref, variant label |
| `chapter_versions` | Timestamped chapters, plus the `transcript_id` (and version) used to generate them |
| `edit_versions` | Edit decisions (cuts, captions), output asset ref |
| `short_variants` | Clip range, reframe settings, captions, output asset ref |
| `publish_snapshots` | **Immutable** record of the exact combination that was approved: script, metadata, thumbnail, chapter and asset version ids, disclosures, scheduled_at, approved_by, approved_at |
| `assets` | Files with checksum, size, storage key |

Publishing only ever reads from a `publish_snapshot`, never from "latest".

**Transcripts and YouTube link and sync**

| Table | Purpose |
|---|---|
| `transcripts` | Id, workspace_id, video_id (nullable), source (`youtube_captions`, `uploaded_file`, `pasted`, `local_whisper`), language, version, parent version, source asset or video reference, created_at. Immutable once a downstream output (such as chapters) has used it |
| `transcript_segments` | transcript_id, start, end, text, confidence (nullable) |
| `youtube_video_links` | workspace_id, video_id, channel_id, youtube_video_id, sync_state (`not_linked`, `linked`, `pending_sync`, `synced`, `drift_detected`, `sync_failed`), linked_at, last_synced_at, last_remote_etag. Unique on (workspace_id, youtube_video_id) |
| `sync_operations` | Per-operation record: video link, applied_snapshot_id, field group (metadata, thumbnail, schedule), status, error details, quota cost, remote etag, readback_verified, timestamps |
| `remote_snapshots` | Normalized managed fields as last read from YouTube (including privacy and publication state), with captured_at, used for drift comparison and scheduling eligibility |
| `youtube_capabilities` | capability, status (`available`, `restricted`, `unsupported`, `requires_audit`), verified_on, source_url, required_scopes, verification_notes |

**Intelligence**

| Table | Purpose |
|---|---|
| `recommendations` | One shared model for every AI suggestion: id, workspace_id, channel_id, video_id (nullable), type, source, recommendation, evidence, confidence (the model's own certainty), evidence_strength (low, medium, high, from sample size and data quality; independent of confidence), sample_size, status (open, accepted, dismissed, expired), created_at, accepted_at, dismissed_at. Types include RETENTION_WARNING, THUMBNAIL_RECOMMENDATION, SEO_RECOMMENDATION, CONTENT_IDEA, PUBLISH_TIME_RECOMMENDATION, SCRIPT_HOOK_WARNING. Audit, QA, SEO, retention and research all write here so the UI renders them consistently |
| `channel_profiles` | Versioned. Every learned attribute carries provenance: value, source, confidence, sample_size, observed_period, last_updated, manual_override. Example: `preferred_video_length: value 7-10 min, confidence 0.71, sample_size 18 videos, source retention_analysis, period 90 days, manually_overridden false` |
| `research_sources` | Source URL, source type, provider, external_id, retrieval_method, retrieved_at, excerpt, content_hash, confidence. **Append-only once referenced as evidence**, so you can always see what the source said when a recommendation was made |
| `experiments`, `experiment_variants` | Tests with sample sizes |

**Execution**

| Table | Purpose |
|---|---|
| `jobs` | States: queued, running, retrying, waiting_for_user, completed, failed, cancelled, dead_letter. Fields: attempt_count, max_attempts, progress, started_at, finished_at, failure_code, failure_message, correlation_id, parent_job_id |
| `workflows`, `workflow_steps` | Domain-level orchestration above raw jobs, including steps that pause for user input. Example `create_short_from_video`: transcribe, identify_clips, user_selection, render, qa, approval |
| `ai_tasks` | Tasks for the AI provider (MCP bridge in v1). States: pending, claimed, running, completed, failed, expired, cancelled. Fields: claimed_by, claimed_at, lease_expires_at (an abandoned task becomes claimable again), input_schema_version, output_schema_version, prompt_version |

**Community and analytics:** `comments`, `comment_reply_drafts`, `analytics_snapshots (time series)`, `keyword_cache`.

**Platform:** `quota_ledger` (durable usage history in Postgres; Redis holds only the live counters), `usage_events` (product telemetry), `notifications`, `audit_log (append-only)`, `idempotency_keys`, `outbox_events`.

Produce an ERD in Mermaid in `docs/DATA_MODEL.md`.

---

## 8. API DESIGN

- REST under `/api/v1`, OpenAPI is the source of truth, TypeScript client generated from it
- Errors as RFC 9457 problem+json
- Cursor pagination, filtering and sorting conventions documented
- Idempotency keys on POST and PATCH that publish or send
- SSE endpoint for job progress
- Consistent naming, versioning policy and deprecation policy in docs
- Contract tests so frontend and backend cannot drift

---

## 9. AI GATEWAY AND MCP DESIGN

- `LLMProvider` port with two adapters: `McpBridgeProvider` (v1) and `AnthropicApiProvider` (v2). Model names come from config, never hard-coded.
- **Prompt registry:** prompts live as versioned files with templates and JSON-schema outputs. Every output validated with Pydantic. Retry on invalid output.
- **Eval harness:** golden-case tests for each prompt, runnable locally. Track schema validity, hallucination and grounding checks, tone match, latency, token cost and user acceptance rate, so providers and models can be compared on the same tests.
- **Cost and usage ledger** per workspace (token counts when using the API).
- **Caching** by hash of normalized input.
- **Prompt-injection defense:** comments, transcripts, titles and any web data are untrusted. Keep them in clearly delimited data sections, never in instructions. The AI cannot trigger side effects: it only produces drafts that pass through the approval gate.
- **MCP server tools:** `list_pending_ai_tasks`, `get_task_context`, `submit_task_result`, `get_channel_profile`, `get_video`, `get_analytics_summary`, `get_transcript`, and read-only by default. Mutating tools only create drafts.
- **v1 AI task experience (must not feel like a hack):** the UI shows each pending AI task with a clear status ("waiting for Claude"), a one-click copyable instruction, and a helper command (for example `make ai-run`) that starts Claude Code with a standing instruction to process pending tasks. Results appear in the UI automatically (SSE). Expired or abandoned tasks are re-queued. Before building any unattended loop, verify Anthropic's current usage terms and plan limits for automated use, and record the answer in `docs/OPEN_QUESTIONS.md`.
- **Execution modes:** both implement `LLMProvider` and are selectable per workspace. Mode A is the MCP bridge (no API cost) and is the **default and only enabled mode in v1**. Mode B is the Anthropic API with a **hard monthly spend cap** (conservative default), warnings at 50%, 80% and 100%, and automatic fallback to Mode A when the cap is reached. Mode B is **disabled by default** behind a feature flag; it may be built and tested with mocked API calls, but enabling it for real use requires an owner decision recorded in an ADR. The app shows cost per workflow and per month. No API mode without a cap.
- **Skills:** one `SKILL.md` per module (script, transcript, thumbnail, edit, comments, planner, virality, retention, shorts, SEO, chapters, audit, youtube-sync), each describing inputs, outputs, quality bar and examples.

---

## 10. SECURITY REQUIREMENTS

Target: OWASP ASVS Level 2, OWASP Top 10, OWASP Top 10 for LLM Applications.

| Area | Requirement |
|---|---|
| Authentication | **Login** uses Google Identity (OpenID Connect) with PKCE and requests identity scopes only. A user can log in without connecting YouTube. Server-side sessions in Redis. httpOnly, Secure, SameSite cookies. Session rotation on login |
| Authorization | RBAC (owner, editor, viewer) per workspace. Checked in the application layer and enforced by Postgres RLS |
| YouTube connection | A separate OAuth 2.0 authorization flow, never tied to app login. Incremental scopes: read-only first; YouTube write scopes (verify the exact minimum scope per capability) only when the user enables sync or publishing; the upload scope only if `direct_video_upload` is enabled. Tokens encrypted at rest (AES-256-GCM, envelope encryption, key id for rotation), never logged, revoked on disconnect |
| Web protection | CSRF protection, strict CORS, CSP with nonces, HSTS, secure headers, input validation everywhere |
| Rate limiting | Per user, per IP, per endpoint class |
| File handling | Size and type limits, magic-number checks, storage outside webroot, signed URLs with short expiry |
| SSRF | Allow-list for any outbound URL fetch |
| Secrets | Environment variables or secrets manager. `.env.example` only. Secret scanning in CI (gitleaks) |
| Supply chain | Lockfiles, Dependabot, dependency audit in CI, container scan (Trivy), CodeQL |
| Logging | Structured logs with no tokens or sensitive data. Audit log for all sensitive actions, including token lifecycle events (`youtube.token.used`, `refreshed`, `revoked`), never the token values |
| Privacy | Data export and deletion, token revocation handling, retention windows. Check YouTube API Services Developer Policies and build to them |
| Threat model | STRIDE threat model in `docs/SECURITY.md`, reviewed each phase |
| Backups | Nightly encrypted database backups to off-site storage, restore tested |
| Server hardening | SSH keys only, firewall (ufw), fail2ban, unattended security updates, non-root containers, read-only filesystems where possible |

---

## 11. FRONTEND AND UX REQUIREMENTS

### Screens
Organize navigation by the creator's job, not by feature:

```
Dashboard
Content      Ideas, Planner, Videos, Shorts
Inbox        Approvals, Comments, Recommendations
Analytics    Performance, Retention, Experiments
Intelligence Audit, Research, Channel Profile
Settings
```

The **Video Workspace** is the main working screen (tabs: Script, Transcript, Thumbnail, Edit, SEO, Chapters, QA, YouTube Sync). Also build: onboarding wizard, Video Board (kanban of the state machine), Approval review (diff view), Notifications center.

### UX principles

| Principle | Detail |
|---|---|
| Guided | One clear primary action per screen. A checklist for what to do next |
| Explain why | Every AI suggestion shows reasoning, evidence and confidence |
| Preview before publish | Thumbnail at real feed sizes, title truncation, Shorts safe areas, YouTube-style mock |
| YouTube sync | Show the approved local version, the current YouTube version, the differences, the last successful sync and whether drift exists. Never silently overwrite external changes. When a capability is restricted, offer manual-apply (copy buttons, thumbnail download, Studio guidance). Tell the creator to upload as Private when they want the app to schedule |
| Safe by design | Approval with diff, undo with toasts, version history, confirmations for destructive actions |
| Long tasks | Background jobs with progress, cancel, notification on completion |
| Progressive disclosure | Simple by default, advanced on demand |
| Empty, loading, error states | Designed for every screen. Skeletons, never blank spinners |
| Speed | Optimistic updates, prefetching, LCP under 2.5 s, CLS under 0.1, bundle budgets enforced in CI |
| Accessibility | WCAG 2.2 AA, keyboard-first, command palette (Cmd/Ctrl+K), focus management, `prefers-reduced-motion`, axe checks in CI |
| Responsive | Fully usable on mobile for review and approve flows |
| Theming | Light and dark, design tokens, consistent spacing (8px grid), type scale |
| Copy | Clear, friendly, no jargon. Microcopy reviewed |

Design system documented in Storybook. Visual regression via Playwright screenshots.

**Design before UI code:** for each new screen, produce a low-fidelity wireframe or mockup and get the owner's approval before building it. Start with onboarding, the video board, the Video Workspace, the approval diff and YouTube Sync.

---

## 12. CODE QUALITY STANDARDS

| Area | Standard |
|---|---|
| Structure | Hexagonal layers per module: `domain`, `application`, `infrastructure`, `api`. Dependency injection. No business logic in routes or components |
| Typing | Python: mypy strict. TypeScript: strict, no `any` |
| Style | Ruff, ESLint, Prettier, enforced by pre-commit and CI |
| Testing | pytest (unit, integration with real Postgres and Redis via containers), mocked external APIs, Playwright end-to-end for key flows. Coverage thresholds: 85% on domain and application code, 70% overall |
| Errors | Typed domain errors mapped to problem+json. No bare exceptions |
| Functions | Small, single purpose, documented public interfaces |
| Git | Trunk-based, small PRs, conventional commits, changelog, semantic versions |
| Docs in code | Docstrings on public APIs, ADRs for decisions |

---

## 13. REPOSITORY LAYOUT

```
/apps/web            Next.js frontend
/apps/api            FastAPI backend (modules/<context>/{domain,application,infrastructure,api})
/apps/worker         Celery workers
/apps/mcp-server     MCP server exposing tools to Claude
/packages/api-client Generated TypeScript client
/skills/<module>     Claude Skills (SKILL.md per module)
/infra               Dockerfiles, compose files, Caddy config, deploy and backup scripts
/docs                README, ARCHITECTURE (C4 in Mermaid), DATA_MODEL, SECURITY, RUNBOOK,
                     DEPLOYMENT, TESTING, PROMPTS, UX_GUIDELINES, CONTRIBUTING, YOUTUBE_CAPABILITIES, adr/, OPEN_QUESTIONS
/.github/workflows   CI (lint, types, tests, security scans, build) and deploy
```

---

## 14. DEPLOYMENT

| Item | Requirement |
|---|---|
| Local | `docker compose up` runs web, api, worker, postgres, redis, mcp-server with seed data. One-command setup documented |
| Environments | `local`, `staging` (optional), `production`. Config only through environment variables |
| VPS | Hostinger VPS, Ubuntu LTS, Docker, Caddy reverse proxy with automatic HTTPS |
| Deploy | GitHub Actions builds images, deploys over SSH, runs migrations, health-check gate, automatic rollback script |
| Sizing | Document minimum VPS size. Heavy video rendering can stay on the owner's machine, or move to a separate worker host |
| Health | `/healthz` (liveness), `/readyz` (dependencies), metrics endpoint |
| Backups and restore | Scripted, scheduled, and restore-tested |
| Runbook | Common failures, quota exhaustion, token revocation, rollback steps |

---

## 15. DELIVERY PLAN

| Phase | Scope | Done when |
|---|---|---|
| 0. Foundation | Repo, tooling, Docker Compose, Postgres and Redis, login (Google OIDC), multi-tenant base schema with RLS, CI, design system skeleton, docs skeleton, first ADRs. Security scans (gitleaks, dependency audit, Trivy, CodeQL) are wired into CI | A user can log in, a workspace exists, CI is green (lint, types, tests, secret scan), a sample module with tests exists, and the remaining security scans run and report. All security scans must be green from Phase 1A onward |
| 1A. Connect and audit | Channel connection, data ingestion, quota ledger, audit, first recommendations | Real channel data is ingested and an audit with evidence is shown |
| 1B. Planner and lifecycle | Planner, video aggregate, state machine, video board | An idea becomes a Video that moves through states with audit entries |
| 1C. Transcript and creation basics | Transcript foundation (paste, upload, one reliable source; local transcription time-boxed), script versions, metadata and SEO versions, chapters | Versions can be created, compared and restored. Chapters are generated from a recorded transcript version without Edit existing |
| 1D. QA, approval and YouTube synchronization | Pre-publish QA, approval diff, immutable publish snapshot, link or discover the YouTube video, capability model, metadata synchronization with read-back, drift detection, manual-apply fallback, idempotency and sync state | One real video goes from idea through QA and approval to an immutable publish snapshot, is linked to a real YouTube channel using an allowed publishing path, and the approved metadata is successfully synchronized (verified by read-back). Where direct API media upload is restricted, the creator uploads the media manually in YouTube Studio as Private and links it. Direct `videos.insert` upload is an optional audited capability, not a Core dependency |
| 1E. Hosted deployment | Production Docker Compose, Caddy HTTPS, CI deploy to the Hostinger VPS, backups with a restore drill, rollback script, runbook. Heavy media rendering stays on the owner's machine | App reachable over HTTPS, deploy and rollback work, restore drill passes, health checks and alerts active |
| 2A. Analytics and community | Retention, comments inbox with drafted replies, notifications | Retention curves and comment triage work on real data |
| 2B. Research and learning | Research, learnings loop | Research ideas carry provenance and the Channel Profile updates from results with confidence |
| 3. Intelligence optimization | Virality scoring, experiments | Scores and test results show confidence and sample size |
| 4. Media automation (optional until the validation gate passes) | Advanced thumbnails, edit automation, Shorts | A long video becomes approved Shorts with captions |
| 5. Multi-user readiness | API provider swap, billing hooks, Google OAuth verification and YouTube API audit prep, load and security review, onboarding polish | Second user can sign up and is fully isolated |

---

**Phase 0 depth rule:** implement interfaces plus one working example, not production-depth subsystems. For example: a `TaskQueue` interface with one working Celery job, a minimal outbox table and relay, and a telemetry event contract. Not a generalized scheduler, an event platform, or an analytics product.

**Initial ADRs (write in Phase 0):** 0001 modular monolith with hexagonal boundaries; 0002 PostgreSQL with row-level security for tenancy; 0003 Celery and Redis behind a `TaskQueue` interface; 0004 OIDC login separate from the YouTube OAuth connection, with per-capability incremental scopes; 0005 `LLMProvider` with the MCP bridge in v1 and a capped API mode disabled by default; 0006 versioned artifacts and immutable publish snapshots; 0007 YouTube capability model and manual-upload (Private) default workflow; 0008 shared transcripts module; 0009 quota ledger (Redis live, Postgres durable).

**Backlog structure:** after approving the Phase 0 plan, produce the backlog so that every ticket contains: ID, Phase, Epic, Capability, Description, Dependencies, Estimate, Acceptance test, Outcome (PASS, BLOCKED or FAIL) and Evidence (automated test IDs, CI run, screenshot, API response, log or audit record, scan result, migration result, or a recorded manual check). A PASS without evidence is invalid. Keep tickets small enough for one focused session each.

### Indicative time-boxes

Working days for one developer at about 4 to 6 focused hours a day, including review and the phase gate. These are planning estimates to be confirmed in the Phase 0 plan, not promises. They exclude a buffer of about 20%.

| Phase | Working days |
|---|---:|
| 0 Foundation | 4-7 |
| 1A Connect and audit | 3-4 |
| 1B Planner and lifecycle | 3-4 |
| 1C Transcript and creation basics | 4-5 |
| 1D QA, approval and YouTube sync | 5-7 |
| 1E Hosted deployment | 2-3 |
| **Subtotal to the validation gate** | **21-30** |
| Validation trial on a real channel | about 4 weeks of calendar time |
| 2A, 2B | 8-12 |
| 3 | 5-8 |
| 4 (optional) | 8-12 |
| 5 | 6-10 |

A phase that exceeds its time-box by more than 50% triggers a scope review: cut by tier, never silently extend. Plan usage limits can stretch calendar time.

### Known risks and mitigations

| Risk | Mitigation built into this spec |
|---|---|
| Scope creep | Feature tiers, the validation gate, scope guardrails, ADR required for scope change |
| YouTube write restrictions for an unaudited project | Capability model, manual-upload (Private) default workflow, read-back verification |
| Wrong OAuth scopes for write capabilities | Per-capability scope recorded with evidence, requested incrementally, verified before enabling |
| Scheduling impossible on a manually uploaded public or unlisted video | Upload as Private by default, QA schedule check, manual-apply fallback |
| OAuth app in Testing mode (token expiry, consent-screen limits; verify current rules) | Clear reconnect flow on token expiry, publishing-status requirements recorded in `docs/OPEN_QUESTIONS.md` |
| v1 AI bridge needs Claude running | Visible task status, helper command, optional capped API mode (disabled by default) |
| Claude plan usage limits | Small tickets, `docs/PROGRESS.md`, one focused session per few tickets |
| Media automation quality | Could tier, Phase 4 optional until the gate passes |
| Product usefulness unproven | Baseline measurement, success metrics, recorded gate decision |
| Multi-tenancy bugs | RLS, cross-tenant test on every endpoint |
| AI hallucination and prompt injection | Evidence and confidence on every suggestion, approval gate, injection test set |
| Small VPS cannot render video | Render on the owner's machine, keep the VPS for the app |

---

### Validation gate and V1 success metrics

Build **Phase 0 through 1E, then stop**. Use the app on a real channel for about a month (or enough videos for meaningful data) before starting Phase 2. Measure a baseline for 2 to 3 videos *before* using the tool, so the comparisons mean something. The targets below are starting guesses to adjust after the baseline.

| Metric | Initial target |
|---|---:|
| Planning time per video | at least 40% reduction |
| Script preparation time | at least 50% reduction |
| Videos completing the full workflow | at least 80% |
| AI recommendations accepted | at least 30% |
| Publish errors caused by automation | 0 |
| Public actions without approval | 0 |
| Weekly use | at least 1 complete workflow per week |
| Owner-rated usefulness | at least 8/10 |

Do not use views, subscribers or "viral videos" as initial success criteria. They depend on too many external factors. Validate workflow value first, then growth impact. Phase 4 (media automation) stays optional until this gate passes.

**Gate decision rule:** at the end of the trial, record proceed, adjust or stop in an ADR. *Proceed* if most metrics are met. *Adjust* (cut or rework features) if some are met and the owner still finds it useful. *Stop or pivot* if usage fell below one complete workflow per week and the owner would not miss it. Do not start Phase 2 without this record.

---

## 16. DOCUMENTATION DELIVERABLES

README, ARCHITECTURE (C4 diagrams in Mermaid), DATA_MODEL (ERD), SECURITY (threat model), RUNBOOK, DEPLOYMENT, TESTING, PROMPTS, UX_GUIDELINES, CONTRIBUTING, YOUTUBE_CAPABILITIES (capability matrix, required scopes and verification evidence), OPEN_QUESTIONS, PROGRESS, CHANGELOG, API reference (generated), ADRs. Keep docs updated in the same PR as the change.

---

## 17. QUALITY SCORECARD (WHAT 10/10 MEANS)

"10/10" is only meaningful when it is measurable. Each phase is done only when the relevant rows below pass in CI or by a recorded manual check. Report the scorecard status at the end of every phase. Rows marked *manual* need the owner or real users.

| Area | 10/10 means (measurable) | Check |
|---|---|---|
| Code quality | mypy strict, Ruff, ESLint, TypeScript strict: zero errors and warnings. Complexity limit enforced (Ruff C901). Coverage at least 85% domain and application, 70% overall. No TODO without a ticket | CI |
| Architecture | Module boundaries enforced by tooling (import-linter for Python, dependency-cruiser for TS) with zero violations. Every significant decision has an ADR | CI |
| Security | Zero high or critical findings from dependency, container, secret and CodeQL scans (required from Phase 1A; Phase 0 requires the scans to be wired and the secret scan to be green). Automated test that hits every endpoint as a user from another workspace and expects denial. OWASP ZAP baseline scan clean. Threat model reviewed each phase. Backup restore tested | CI plus recorded check |
| Data model | Migrations tested forward and backward. RLS policy test for every tenant table. ERD generated from the schema, never hand-drawn | CI |
| AI quality | Golden-set evals: 100% schema-valid output, grounding checks at or above 95%, a prompt-injection test set (malicious comments and transcripts) that triggers zero side effects. Zero public actions without approval, proven by test | CI |
| UX | Playwright end-to-end tests for every key flow. Three non-technical testers complete onboarding in under 5 minutes and can explain the workflow afterwards | CI plus *manual* |
| Accessibility | WCAG 2.2 AA. Zero serious or critical axe violations on all key pages. Lighthouse accessibility 100 on Core screens where technically achievable (never the only check). Every critical workflow completable by keyboard alone. Screen-reader sanity pass on onboarding, approval and publish. `prefers-reduced-motion` respected | CI plus *manual* |
| Responsive | The main workflow (plan, review, approve) works on desktop, tablet and mobile | Playwright viewports |
| Performance | LCP under 2.5 s, CLS under 0.1, API p95 under 300 ms for non-AI endpoints on the target VPS | CI plus load check |
| Reliability and DevOps | One-command deploy and tested rollback. Health checks and alerts. Documented RPO of 24 h or better and RTO of 2 h or better, proven by a restore drill | Recorded drill |
| Documentation | Every deliverable in section 16 exists, is current, and a new developer can run the project from the README in under 30 minutes | *Manual* |
| Scope and delivery | Every phase time-boxed. Scope changes need an ADR. Lower tiers not started before higher tiers pass | Review |
| Budget | Monthly cost report visible in the app (infrastructure and AI). API mode disabled by default, and a hard spend cap whenever it is enabled | CI plus review |
| Media features | Honest limits shown in the UI. Caption accuracy of at least 95% on the owner's own content. Edits never delete content without a preview and approval | *Manual* |
| Functionality | Every Core acceptance criterion in section 4 passes. No fake, mocked or dummy functionality presented as real | Acceptance tests |
| Privacy | Token encryption, revocation, data export and deletion flows each verified by test | CI plus recorded check |
| YouTube integration | Tested against a real owned channel. The capability matrix correctly represents restricted functionality, and each write capability has recorded verification evidence and its required scope. Metadata sync verified by read-back. Remote drift detection tested. Scheduling offered only when the linked video is eligible. Quota-aware, retry-safe, idempotent. Quota exhaustion degrades gracefully. An unaudited project cannot reach disabled direct-upload paths (tested) | Real-channel run plus CI |
| Transcripts | Chapters generate without Edit implemented. Imported, uploaded, pasted and local transcripts all use the same abstraction. Chapter output records the transcript version | CI |
| Publishing safety | Zero publishes, uploads or replies without approval. Publishing and sync read only immutable approved snapshots. Post-approval edits require re-approval. External drift never silently overwrites the local approved state or the remote state. Proven by test | CI |
| Observability | Logs, metrics, correlation IDs, alerts and the audit trail are usable to diagnose a simulated failure | Recorded drill |
| Product validation | Section 15 success metrics met and the gate decision recorded | *Manual*, real use |

**Phase quality gate (repeat for every phase).** A phase is not finished when the code exists:

```
implementation -> functional verification -> security verification
  -> architecture verification -> test and coverage verification
  -> UX and accessibility verification -> documentation verification
  -> QUALITY SCORECARD
       PASS -> freeze the phase, start the next
       FAIL -> fix defects, re-run the scorecard
```

Keep the gate proportional: a check that does not apply to a phase is marked not applicable with a reason, never silently skipped.

---

## 18. SCOPE GUARDRAILS (DO NOT ADD)

Avoid architecture inflation. Do **not** introduce, unless a concrete need is documented in an ADR and approved: Kubernetes, Kafka, Elasticsearch, GraphQL, microservices, an external workflow engine (such as Temporal), event sourcing, a separate database per module, or a vector database. PostgreSQL + Redis + Celery is the intended stack. The biggest project risk is scope creep: build one thin vertical slice at a time.

---

## 19. FIRST INSTRUCTION

Start with **Phase 0 only**. Reply with:

1. The detailed Phase 0 plan (files, order, decisions, risks)
2. Any questions that block you (maximum five)
3. Then, after I confirm, implement Phase 0 in small commits, running tests and linters as you go

Do not start Phase 1A until I approve Phase 0.
