"""The shared transcript model (spec §4 feature 22, ADR 0008/0014).

One abstraction serves four sources: imported YouTube captions, an uploaded
file, pasted text, and local ``faster-whisper`` transcription. All four
produce the same two things - a :class:`Transcript` header and its ordered
:class:`TranscriptSegment` rows - so every downstream consumer (chapters,
scripts, QA) reads transcripts the same way regardless of where the text
came from.

Transcripts are write-once: there is no update operation anywhere in this
module. Re-transcribing or re-uploading creates a new, independent
``Transcript`` row (optionally pointing at ``parent_transcript_id`` for
provenance); nothing ever mutates an existing one. This gives the "immutable
once a downstream output has used it" rule from spec §7 for free, with no
reference-counting needed.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime


class TranscriptSource(enum.StrEnum):
    """Where a transcript's text came from (spec feature 22: "four sources")."""

    YOUTUBE_CAPTIONS = "youtube_captions"
    UPLOADED_FILE = "uploaded_file"
    PASTED = "pasted"
    LOCAL_WHISPER = "local_whisper"


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """One timed (or, for plain paste, untimed) span of transcript text.

    ``end``/``confidence`` are optional: a pasted block of text has no
    reliable timing at all, so it is stored as a single segment with
    ``start=0`` and ``end=None`` rather than a fabricated duration. Chapter
    generation (spec feature 10) requires every segment to carry a real
    ``end``, and refuses otherwise - see ``content.domain.errors``.
    """

    start_seconds: float
    end_seconds: float | None
    text: str
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class Transcript:
    """One version of a video's transcript (spec §7 ``transcripts``)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    video_id: uuid.UUID | None
    source: TranscriptSource
    language: str
    version: int
    parent_transcript_id: uuid.UUID | None
    segments: tuple[TranscriptSegment, ...]
    created_at: datetime

    @property
    def is_fully_timed(self) -> bool:
        """Whether every segment has a real ``end_seconds`` (chapters need this)."""
        return len(self.segments) > 0 and all(s.end_seconds is not None for s in self.segments)

    @property
    def duration_seconds(self) -> float | None:
        if not self.is_fully_timed:
            return None
        return max(s.end_seconds for s in self.segments if s.end_seconds is not None)
