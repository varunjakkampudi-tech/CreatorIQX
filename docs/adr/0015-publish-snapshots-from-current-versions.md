# ADR 0015: Build publish snapshots from "current" version ids; treat `youtube_capabilities` as global

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-10 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §3 (publishing capability model), §7 (`publish_snapshots`, `youtube_capabilities`); ADR 0006 (versioned artifacts, immutable snapshots), ADR 0007 (capability model), ADR 0014 (deferred the `videos` pointer columns) |

## Context

ADR 0014 deferred adding "current version" pointer columns to `videos`,
noting that nothing before Phase 1D actually needed one frozen combination
of version ids - each `content` version table's own `is_current` flag was
enough. Phase 1D's `publish_snapshots` is the first thing that does need
exactly that combination, frozen at approval time. Separately, the spec
lists `youtube_capabilities` as a plain table without saying whether it is
tenant-scoped, and the app is single-Google-Cloud-project per deployment in
both v1 and the planned v2 multi-tenant shape.

## Decision

1. **`PublishSnapshotStore.create()` reads the current version directly from
   each version store** (`ScriptVersionStore.list_for_video` filtered to
   `is_current`, same for metadata and chapters) at the moment of approval,
   and copies those ids into the new immutable snapshot row. `videos` gets
   no pointer columns. This keeps the approval service's dependency on
   `content`'s stores read-only (already the pattern `ChapterService` set
   with `transcripts`, ADR 0014) and avoids a write path from `publishing`
   into `planning`'s `videos` table, which the module-boundary rule (spec
   §3: "`publishing` must never write to `content.script_versions`", and by
   the same logic, never write artifact pointers into `planning.videos`)
   would otherwise forbid.
2. **`youtube_capabilities` has no `workspace_id` column and sits outside
   row-level security**, next to `users`, `workspaces` and `outbox_events`
   in the global-tables list. It records what *this deployment's* Google
   API project is verified to do - one fact per deployment, not per tenant.
   Seeded by a script/fixture, read by every workspace, written only
   through an explicit verification step (never through a tenant-scoped
   request).
3. **`publish_snapshots` is insert-only for the app role**, enforced the
   same way `audit_log` already is (migration 0004): `REVOKE UPDATE,
   DELETE`, plus a trigger that raises on either, so the restriction holds
   even if a future query forgets to check it.

## Consequences

| Type | Consequence |
|---|---|
| Positive | No cross-module write path needed from `publishing` into `planning` or `content` |
| Positive | `youtube_capabilities` needs no per-workspace seeding or RLS policy |
| Negative | Building a snapshot requires three reads (script, metadata, chapter stores) instead of one row lookup on `videos` |
| Negative | If v2 ever runs multiple Google Cloud projects per deployment (not currently planned), `youtube_capabilities` would need a tenant or project-scoped key added later |
| Follow-up | Phase 1D's `ApprovalService` (P1D-03) implements the three-read snapshot construction; `CapabilityService` seeds and reads `youtube_capabilities` |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Add pointer columns to `videos` now | Needs a cross-module write from `content`/`transcripts` into `planning` every time a version is created, for a need only `publishing` has |
| Make `youtube_capabilities` tenant-scoped with a row per workspace | Duplicates identical rows across every workspace for data that is actually app-level; no current multi-project need to justify it |
| Store capability evidence only in `docs/YOUTUBE_CAPABILITIES.md`, no table | Spec §3 explicitly asks for the table once Phase 1D needs runtime capability checks, not just documentation |

## Enforcement

- Test: approving a video with no current metadata version is refused (snapshot construction fails loudly, never with a null/default).
- Test: `UPDATE`/`DELETE` against `publish_snapshots` fails for the app role, proven the same way as the existing `audit_log` append-only test.
- Test: the RLS meta-test's auto-discovery query (by `workspace_id` column presence) does not pick up `youtube_capabilities` - no allow-list entry required.
