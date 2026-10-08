# ADR 0006: Version artifacts independently and publish only immutable snapshots

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §3 (Video state machine, Approval invalidation), §7 (Video aggregate), §17 (Publishing safety) |

## Context

A video is assembled from several artifacts (script, metadata, thumbnail, chapters, edits, shorts), each edited at its own pace by people and AI. The owner approves a specific combination, and exactly that combination must reach YouTube, even if someone keeps editing afterwards. One "video version" row holding everything would make every small edit a copy of the whole video and blur what was approved.

## Decision

1. **Each artifact is versioned in its own table** (`script_versions`, `metadata_versions`, `thumbnail_variants`, `chapter_versions`, `edit_versions`, `short_variants`). Versions are append-only; a version records its parent and its author (human or AI). `videos` holds pointers to the current version of each artifact.
2. **Approval freezes a `publish_snapshot`:** an immutable row holding the exact version ids of every artifact, disclosures, `scheduled_at`, `approved_by` and `approved_at`.
3. **Approval invalidation:** after approval, any change to a publish-bound artifact creates a new version, never mutates the snapshot, and returns the video to `in_review`. A new approval creates a new snapshot. The UI states which version is approved and which is pending.
4. **Publishing and sync read only from a snapshot,** never from "current" pointers.
5. Editable aggregates carry a `version` column for optimistic concurrency.

## Consequences

| Type | Consequence |
|---|---|
| Positive | What was approved is provable and reproducible; restore and compare are natural |
| Positive | No race between an editor and the sync job |
| Negative | More tables and joins; storage grows with versions (text versions are small) |
| Negative | Domain logic must manage "current" pointers carefully |
| Follow-up | Phase 1B (video aggregate), 1C (versions), 1D (snapshots, approval, sync) |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| One `video_versions` row with all fields | Every edit copies everything; approval scope unclear; forbidden by spec §7 |
| Mutable rows plus an audit log | Reconstructing "what was approved" from logs is fragile |
| Event sourcing | Forbidden by spec §18 without a concrete need; heavy for one developer |

## Enforcement

- Database: snapshot rows are insert-only for the runtime role (no UPDATE or DELETE grant, plus a trigger).
- Tests: editing an artifact after approval leaves the snapshot unchanged and moves the video to `in_review`; publishing code paths accept only a snapshot id (type-level, no "latest" accessor in the publishing module).
