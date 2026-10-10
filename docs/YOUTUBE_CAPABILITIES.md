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

## Phase 1A: the read-only connection (not a write capability)

Phase 1A's connection (`youtube` module, `GoogleYouTubeOAuthProvider`) requests only
`https://www.googleapis.com/auth/youtube.readonly`, verified 2026-10-10 against
the current YouTube Data API v3 OAuth 2.0 scopes documentation
(https://developers.google.com/youtube/v3/guides/auth/installed-apps). This is
not one of the write capabilities in the register above - it grants no write
access at all, so it needs no audit and no `requires_audit` status. It reads,
through `HttpYouTubeDataApiClient`:

- `channels.list(mine=true, part=snippet,statistics,contentDetails)` - the connected channel's own identity, stats and uploads playlist id;
- `playlistItems.list(playlistId=<uploads>, part=contentDetails)` - discovers videos via the uploads playlist, never `search.list` (spec §3 explicit requirement);
- `videos.list(id=<...>, part=snippet,contentDetails,statistics)` - up to 50 ids per call, for per-video metadata and stats.

Quota costs for these three methods were assumed at 1 unit per call each
(not independently re-verified against Google's current quota calculator
this session - see OQ-18) and are reserved per call actually made, not per
estimated page, by `ChannelIngestionService`.
