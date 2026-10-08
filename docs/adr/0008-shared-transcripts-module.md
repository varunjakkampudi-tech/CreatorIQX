# ADR 0008: Serve all transcript sources through one shared transcripts module

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §4 features 10 and 22, §7 (Transcripts), §15 (Phase 1C), §17 (Transcripts) |

## Context

Chapters, SEO, scripts, edits, shorts and comments analysis all need transcripts. Transcripts can come from YouTube caption data, an uploaded file, pasted text or local transcription. If each feature fetched its own, results would disagree and nothing could say which transcript a chapter list came from. Chapters (Core) must not depend on Edit (Could tier).

## Decision

1. A dedicated **`transcripts` module** owns `transcripts` and `transcript_segments`.
2. One **`TranscriptSource` port** with four adapters: `youtube_captions` (through permitted YouTube APIs), `uploaded_file`, `pasted`, `local_whisper` (faster-whisper). All produce the same model: versioned segments with start, end, text, language, source and optional confidence.
3. **Transcripts are versioned** (parent version), and a transcript becomes **immutable once a downstream output has used it.**
4. **Downstream outputs record the exact transcript version** they used (for example `chapter_versions.transcript_id`).
5. Other modules use the transcripts module's public interface, never its tables.
6. Local transcription is built and time-boxed but is **not a PASS blocker** for Phase 1C; paste and upload are enough for Chapters.

## Consequences

| Type | Consequence |
|---|---|
| Positive | Chapters work without Edit; every output is traceable to its source text |
| Positive | Adding a source means adding an adapter |
| Negative | Immutability means corrections create new versions and new downstream outputs |
| Follow-up | Phase 1C; caption-import permissions verified before that adapter is built |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Each feature fetches its own transcript | Inconsistent results, no provenance |
| Transcripts inside the `content` module | Couples Core chapters to content internals; the spec names `transcripts` as its own context |

## Enforcement

- import-linter: no module imports `transcripts.infrastructure`.
- Contract tests: all four adapters pass the same test suite.
- Test: chapter generation stores the transcript id and version; modifying a used transcript is rejected.
