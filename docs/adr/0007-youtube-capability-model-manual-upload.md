# ADR 0007: Gate every YouTube write behind a verified capability; default to manual Private upload

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §3 (YouTube publishing capability model, Default V1 publishing workflow, YouTube synchronization state), §4 features 12 and 14, §17 (YouTube integration) |

## Context

As far as currently known (verify, OQ-01), uploads through `videos.insert` from unaudited API projects are restricted to private viewing until a compliance audit. Other writes (metadata, thumbnails, scheduling, comment replies) have their own scope and eligibility rules. Assuming any of these works, and building the core workflow on it, risks a product that cannot deliver its main promise. Wrong writes to a creator's live channel are costly and public.

## Decision

1. Every YouTube write is a **capability**: `metadata_update`, `thumbnail_update`, `scheduling`, `comment_reply`, `direct_video_upload`, `direct_publish`. Each resolves to `available`, `restricted`, `unsupported` or `requires_audit`.
2. **Evidence before enablement:** a capability can become `available` only with recorded `verified_on`, `source_url`, `required_scopes` and `verification_notes` (in `docs/YOUTUBE_CAPABILITIES.md`, later the `youtube_capabilities` table). Unverified means restricted.
3. **Default v1 workflow:** the creator uploads the media manually in YouTube Studio **as Private**; the app links or discovers the video (via the uploads playlist, not `search.list`), compares remote metadata with the approved snapshot, applies allowed changes, and reads them back.
4. `YOUTUBE_DIRECT_UPLOAD_ENABLED=false` by default and cannot be enabled without recorded verification.
5. **Every write is read back and verified.** `videos.update` first reads the resource and resends every mutable field to preserve (verify).
6. **Scheduling** is offered only when the linked video is private and never published (verify, OQ-07); otherwise manual-apply guidance.
7. **Manual-apply fallback** for any restricted capability: copy buttons, thumbnail download, YouTube Studio guidance.
8. **Separate sync state** (`not_linked`, `linked`, `pending_sync`, `synced`, `drift_detected`, `sync_failed`) and per-operation `sync_operations` rows. Drift is resolved explicitly (adopt remote, overwrite remote with new approval, or ignore); never silently.

## Consequences

| Type | Consequence |
|---|---|
| Positive | The core workflow (Phase 1D) can PASS without any audited capability |
| Positive | The UI can be honest about what works for this channel and project |
| Negative | The creator does one manual step (upload) per video in v1 |
| Negative | Capability verification is ongoing work as Google's rules change |
| Follow-up | Phase 1A (read capabilities), 1D (writes, sync, drift); OQ-01 to OQ-07 |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Build on `videos.insert` from day one | Likely restricted for an unaudited project; Core would depend on an audit |
| Hard-code capability assumptions | Breaks silently when rules or channel eligibility differ |
| Browser automation of YouTube Studio | Violates the official-APIs-only rule |

## Enforcement

- Test: an unaudited configuration cannot reach the direct-upload code path.
- Test: enabling a write capability without evidence fields is rejected.
- Test: every write operation is followed by a read-back assertion before the sync operation is marked succeeded.
