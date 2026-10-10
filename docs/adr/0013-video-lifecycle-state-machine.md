# ADR 0013: Enforce the video lifecycle as a domain-layer state machine, audited on every transition

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-10 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §3 ("Video state machine"), §4 features 4 and 13, §7 (`videos`, `plans`); ADR 0006 (versioned artifacts, immutable snapshots) |

## Context

Phase 1B needs an idea to become a `Video` and move through
`idea -> planned -> drafting -> qa -> in_review -> approved -> scheduled -> published -> analyzed`
(plus `rejected` and `archived`), with every transition enforced and audited
(spec §3). The planner (spec feature 4) is a separate concern - a lightweight
backlog/calendar entry that becomes a video "in one click" - and must not be
confused with the lifecycle itself.

## Decision

1. **A new `planning` bounded context owns both `plans` and `videos`.** The
   spec's module list (§3) does not name a "planner" module explicitly, but
   the video aggregate's lifecycle state machine is this module's own domain
   invariant, not a cross-cutting workflow, so it is not split out to
   `workflows`. Later phases add the versioned-artifact tables
   (`script_versions`, `metadata_versions`, ...) as their own modules'
   tables, each pointed at `videos.id`; `planning` keeps owning `videos`
   itself and its status column.
2. **The transition graph is a pure data structure in the domain layer**
   (`ALLOWED_TRANSITIONS: dict[VideoStatus, frozenset[VideoStatus]]`), checked
   by `assert_transition` before any write. The application layer never
   writes a status without calling it first, so an invalid transition is a
   domain error (409 `video-invalid-transition`), not a possible database
   state.
3. **`archived` is reachable from every working state**, expressed once as a
   union rather than repeated per edge, since "abandon this" is always a
   valid escape hatch. `rejected` returns to `drafting` (resubmission), never
   straight back to `in_review`.
4. **The `approved -> in_review` edge exists now, even though nothing
   triggers it yet.** Approval invalidation (spec §3: a post-approval edit
   returns the video to `in_review`) is Phase 1D's job once
   `publish_snapshots` exists; the edge is a domain invariant today so 1D
   only has to wire the trigger, not extend the graph.
5. **A promoted plan creates the video at `planned`, not `idea`.** The plan
   already represents the planning work; skipping it would make the very
   first status transition a no-op on data nobody asked to see.
6. **Promotion is one-way**, recorded as `plans.promoted_video_id`. There is
   no "unpromote" - the spec's acceptance criterion is "Plans persist and can
   become Video records in one click," not a two-way link to maintain.
7. **Every create and every status write records its own audit-log row and
   outbox event, in the same transaction as the `videos` write**, following
   the precedent `workspaces.infrastructure.sql_store` already set for
   workspace creation: a module's infrastructure layer writes directly to
   `audit_log` and `outbox_events` rather than through a port, because those
   are shared-kernel tables, not another bounded context's owned aggregate.
   This satisfies spec §3's "every transition writes an audit log entry and
   emits a domain event" without a new cross-module port.
8. **No OAuth-gated feature flag.** Unlike `_wire_youtube` (gated on
   `youtube_oauth_client_id`), the planner and video board need no external
   credentials, so `_wire_planning` runs unconditionally in the composition
   root, like `_wire_workspaces`. This also means the existing cross-tenant
   route harness (ADR 0012) exercises these routes automatically, with no
   change to the harness itself.

## Consequences

| Type | Consequence |
|---|---|
| Positive | An invalid transition can never reach the database; it fails in the domain layer with a stable, typed error |
| Positive | The audit trail and the outbox event for a status change cannot be forgotten by a future caller - they are written by the store, not left to the application layer to remember |
| Positive | New routes are covered by the cross-tenant harness with no additional wiring |
| Negative | `videos.plan_id -> plans.id` is a real foreign key, but `plans.promoted_video_id` is not (no FK to `videos.id`), to avoid a circular create-order dependency within one transaction. Referential integrity there is an application-layer guarantee, not a database one - recorded here rather than hidden |
| Negative | `SqlVideoStore`/`SqlPlanStore` reach into `audit.infrastructure.tables` and `jobs.infrastructure.tables` directly, the same cross-module infrastructure-to-infrastructure import `workspaces` already uses. Acceptable by precedent (ADR 0001 reads it as the shared kernel), but it means those two tables have more than one de facto writer module |
| Follow-up | Phase 1D wires the `approved -> in_review` edge to an actual post-approval edit trigger. Phase 1C adds the versioned-artifact tables that `videos` will eventually point at |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Model the lifecycle inside `workflows`/`jobs` as a `Workflow`/`WorkflowStep` | Spec §6 reserves that for orchestration above raw jobs (e.g. `create_short_from_video`); the video's own status is a simpler aggregate-level invariant, not a multi-step job with pauses |
| Let the plan's status double as the video's status (one table, not two) | Conflates "an idea on the backlog" with "a video moving through drafting/QA/approval/publish"; the spec explicitly separates planner (feature 4) from the state machine (§3) |
| Validate transitions only in the API layer | Would leave the domain invariant unenforced for any other caller (a worker task, the MCP bridge in a later phase), and spec §12 requires "no business logic in routes" |

## Enforcement

- `apps/api/tests/test_planning_transitions.py`: every allowed and a sample of
  disallowed edges, every working state can archive, every `VideoStatus` has
  an edge set, and `assert_transition` raises with both statuses attached.
- `apps/api/tests/test_planning_services.py`: `PlannerService` creates and
  promotes a plan exactly once (a second promotion raises), scopes the board
  to the workspace; `VideoLifecycleService` transitions forward, refuses a
  disallowed transition without persisting it, and scopes the board to the
  workspace.
- `apps/api/tests/test_planning_routes.py`: the full route path for create,
  list, promote and transition, a viewer refused on a mutating route, and an
  invalid transition surfacing as 409 `video-invalid-transition` over HTTP.
- `apps/api/tests/test_cross_tenant.py` (unchanged): now also covers every
  `/planner/*` and `/videos/*` route, since they carry no feature flag.
