# YouTube Capabilities

The capability register required by spec §3. **No write capability can be enabled without recorded verification evidence.** Until a row has evidence, the app treats it as restricted.

Allowed statuses: `available`, `restricted`, `unsupported`, `requires_audit`. Verification happens before each capability is implemented (Phase 1A for reads, Phase 1D for writes), never from memory.

## Register

| Capability | Meaning | Status | Verified on | Required scopes | Source URL | Verification notes |
|---|---|---|---|---|---|---|
| `metadata_update` | Update title, description, tags, category, disclosure fields | `restricted` (not verified) | — | Not verified (OQ-06) | — | Read current resource first; send back every mutable field to preserve (verify) |
| `thumbnail_update` | Set a custom thumbnail | `restricted` (not verified) | — | Not verified (OQ-06) | — | Eligibility verified at runtime per channel (OQ-03) |
| `scheduling` | Set `status.publishAt` | `restricted` (not verified) | — | Not verified (OQ-06) | — | Expected only for private, never-published videos (OQ-07) |
| `comment_reply` | Post approved comment replies | `restricted` (not verified) | — | Not verified (OQ-06) | — | Phase 2A |
| `direct_video_upload` | Upload media via `videos.insert` | `restricted` (not verified); `YOUTUBE_DIRECT_UPLOAD_ENABLED=false` | — | Not verified (OQ-06) | — | Expected `requires_audit` for this unaudited project (OQ-01) |
| `direct_publish` | Change privacy or publication state | `restricted` (not verified) | — | Not verified (OQ-06) | — | Depends on OQ-01, OQ-02 |

## Evidence rule

A status may change only in a commit that adds the verification date, the official source URL, the exact scopes, and notes from the actual project status. The same data is persisted in the `youtube_capabilities` table once it exists (Phase 1D).
