# ADR 0014: Shared transcripts module and versioned script/metadata/chapter artifacts

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-10 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §4 features 5, 9, 10, 22; §7 (`transcripts`, `transcript_segments`, `script_versions`, `metadata_versions`, `chapter_versions`); ADR 0006 (versioned artifacts), ADR 0008 (shared transcripts module) |

## Context

Phase 1C needs: a transcript foundation serving four sources behind one
abstraction (feature 22); script versions a creator can compare and restore
(feature 5); metadata/SEO versions with character-limit warnings (feature
9); and chapters generated from a transcript version, validated against
YouTube's own rules (feature 10). None of this needs YouTube credentials or
Claude Pro's MCP bridge, so - like the planner in Phase 1B - it can be built
and verified without any owner action.

## Decision

1. **Two new bounded contexts.** `transcripts` owns `transcripts`/
   `transcript_segments`. `content` owns `script_versions`/
   `metadata_versions`/`chapter_versions`. This matches the spec's module
   list (§3) directly rather than folding transcripts into `content`,
   because feature 22 calls transcripts out as its own shared module that
   chapters (and, later, Edit) both depend on.
2. **Transcripts are write-once.** No table or store method updates an
   existing transcript row; re-importing or re-transcribing always creates
   a new `Transcript` with an optional `parent_transcript_id` for
   provenance. This gives spec §7's "immutable once a downstream output has
   used it" rule for free, with no reference-counting needed.
3. **One abstraction, four sources, two wired end to end.** `paste` and
   `uploaded_file` (with a dependency-free SRT/WebVTT line parser, falling
   back to one untimed segment for anything else) go through
   `TranscriptService` to a real `SqlTranscriptStore` today.
   `youtube_captions` and `local_whisper` are real methods on the same
   service - not missing - but both raise
   `TranscriptSourceUnavailableError` rather than quietly no-oping:
   `youtube_captions` needs a caption-download scope and format handling
   not built this phase (OQ-21, new); `local_whisper` needs
   `faster-whisper` installed, which this sandbox cannot do, and spec
   feature 22 explicitly allows this to be "built and time-boxed but is not
   a PASS blocker for Phase 1C." Neither gets a route, since a route that
   always answers 501 is noise, not a capability.
4. **"Current version" lives on each version table, not on `videos`.**
   Spec §7 describes `videos` carrying "pointers to the current version of
   each artifact," but the only thing that actually needs one frozen,
   atomic combination of version ids is Phase 1D's `publish_snapshots` -
   nothing in Phase 1C reads "the current script version for publishing,"
   only "the current script version to show in the UI." Each of
   `script_versions`/`metadata_versions`/`chapter_versions` therefore
   carries its own `is_current` boolean per `video_id`, flipped atomically
   by its own store's `create()` (clear the old row's flag, insert the new
   one as current, in one transaction) - "versions can be created, compared
   and restored" (the Phase 1C acceptance line) needs nothing more than
   that. This avoids giving `content`/`transcripts` write access to
   `planning`'s `videos` table, which would need a new cross-module port
   for no Phase-1C benefit. Phase 1D adds the real pointer-free mechanism
   it actually needs: `publish_snapshots` record the specific version ids
   it was approved with, not "whatever is current."
5. **"Restore" creates a new version, copying the old one's content.**
   There is no separate restore/rollback table operation. The service reads
   the target version's fields and calls `create()` again with them
   (`parent_version_id` set to the restored version), so restoring is just
   another version - history is never deleted, and "restore any version"
   (feature 5) falls out of the same `create()` path every other write
   uses.
6. **Chapter generation depends on `transcripts`' public port, not its
   infrastructure.** `ChapterService` takes a `TranscriptStore` (the
   protocol `transcripts.application.ports` defines) as a constructor
   argument, and `main.py`'s composition root passes the same
   `SqlTranscriptStore` instance that satisfies it - "other modules consume
   it only through the owner's public interface" (spec §3) applied at the
   application-layer boundary, not only at infrastructure. This is the
   first module-to-module dependency in the codebase that isn't audit/
   outbox (ADR 0013's shared-kernel exception); it is a real one bounded
   context depending on another's stated port, not a shortcut around it.
7. **Chapter generation is an honest v1 heuristic, not topic detection.**
   `generate_draft_chapters` slices a fully timed transcript into 3-10
   evenly spaced chapters and titles each from the nearby transcript text.
   It satisfies "chapters generated from a recorded transcript version"
   literally - the chapter count, boundaries and titles all come from the
   transcript's real duration and text - without claiming semantic topic
   boundaries this version does not compute. Generation refuses (422) on a
   transcript that is not fully timed (e.g. a plain paste), since there is
   no reliable duration to slice.
8. **Chapter validation is a pure domain function**, checked before any
   chapter version - manual or generated - is persisted: starts at
   `00:00`, at least 3 chapters, strictly ascending, each at least 10s from
   the next (verified against current YouTube Help, spec rule 3, recorded
   in `docs/YOUTUBE_CAPABILITIES.md`). A violation is a typed 422
   (`chapter-validation-failed`), never a silently-accepted bad chapter
   list.
9. **No audit-log/outbox write on version creation.** Spec §3's "every
   transition writes an audit log entry" is specifically about the video
   lifecycle state machine (ADR 0013); creating a script/metadata/chapter/
   transcript version is not a lifecycle transition, so none of this
   phase's five new stores write to `audit_log`/`outbox_events`. Recorded
   here as a deliberate scope line, not an oversight.
10. **No feature flag.** Like the planner, none of this needs external
    credentials, so `_wire_transcripts`/`_wire_content` run unconditionally
    in `main.py`'s composition root - the existing cross-tenant route
    harness (ADR 0012) covers every new route automatically.

## Consequences

| Type | Consequence |
|---|---|
| Positive | Chapters, scripts and metadata all share one "exactly one current version per video, restore via new version" contract, implemented once per store rather than reinvented per feature |
| Positive | The `youtube_captions`/`local_whisper` gaps are visible and typed (`TranscriptSourceUnavailableError`), not a silent success that would mislead a later phase into assuming caption import already works |
| Negative | `videos` carries no literal "current version" pointer columns yet, unlike the spec §7 table description; Phase 1D must introduce `publish_snapshots` as the real mechanism rather than reusing an existing pointer column, which is extra work this ADR defers rather than avoids |
| Negative | `content.application` now imports `transcripts.application`/`transcripts.domain` directly - the first non-shared-kernel cross-module dependency in this codebase; acceptable by the same "public interface" reading ADR 0013 already established, but worth watching if more modules start reaching across this way |
| Follow-up | Phase 1D: wire `publish_snapshots` to the actual current-version ids at approval time; wire the `approved -> in_review` transition on a post-approval edit to any of these five tables |
| Follow-up | `OQ-21` (new, `docs/OPEN_QUESTIONS.md`): the exact YouTube Data API caption-download scope/format needed to make `youtube_captions` real |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Fold `transcripts` into `content` as one module | Spec feature 22 and §3's module list both name transcripts as its own shared module; chapters (this phase) and Edit (a later Could-tier feature) both consume it, so keeping it separate avoids content owning a dependency two other features need independently |
| Add `current_script_version_id`/etc. columns to `videos` now | Needs a new cross-module write port from `content`/`transcripts` into `planning`'s table for a benefit ("what's current") that each version table's own `is_current` flag already provides this phase; deferred until Phase 1D's `publish_snapshots` gives a real reason |
| Build a working `faster-whisper` adapter now | This sandbox cannot install it (no PyPI access); spec feature 22 explicitly allows deferring it past Phase 1C's PASS bar |
| Have `ChapterService` call a YouTube captions-style route for `youtube_captions` just to "complete" the four sources | Would need the caption-download scope spec §3 says to request only once the capability is enabled - building a route that cannot actually work yet is worse than a named, typed gap |

## Enforcement

- `apps/api/tests/test_chapter_validation.py`: every YouTube chapter rule,
  both satisfied and violated.
- `apps/api/tests/test_transcript_service.py`: SRT/plain-text parsing, all
  four source methods (two real, two typed-unavailable), workspace
  scoping.
- `apps/api/tests/test_content_services.py`: script/metadata/chapter
  create-compare-restore, the "exactly one current" invariant, chapter
  generation success and its two refusal paths.
- `apps/api/tests/test_phase1c_routes.py`: the full route path for
  transcripts/scripts/metadata/chapters, a viewer refused on a mutating
  route, and both chapter-validation and chapter-generation failures
  surfacing as typed problem+json responses over HTTP.
- `apps/api/tests/test_cross_tenant.py` (unchanged): now also covers every
  new route, since none carry a feature-flag exemption.
