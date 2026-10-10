"""Pure heuristic: draft chapters from a fully timed transcript (spec feature 10).

This is a v1 heuristic, not an understanding of topic boundaries: it slices
the transcript into evenly spaced segments and titles each one from the
transcript text nearest its start time, producing a draft the creator edits
before publishing (spec feature 10 acceptance: "Editable before publish").
"Generated from a transcript version" is satisfied literally - the titles
and the very existence of a draft both come from the transcript's own text
and duration - without claiming any topic-detection intelligence this
version doesn't have.
"""

from __future__ import annotations

from creatoriqx_api.modules.content.domain.chapters import (
    MIN_CHAPTER_SECONDS,
    MIN_CHAPTERS,
    Chapter,
)
from creatoriqx_api.modules.transcripts.domain.transcript import Transcript

MAX_CHAPTERS = 10
_TITLE_WORDS = 6


def generate_draft_chapters(transcript: Transcript) -> tuple[Chapter, ...]:
    """Raise :class:`ValueError` if the transcript is too short to chapter."""
    duration = transcript.duration_seconds
    if duration is None:
        raise ValueError("transcript has no reliable end-times")
    if duration < MIN_CHAPTERS * MIN_CHAPTER_SECONDS:
        raise ValueError("transcript is too short for the minimum chapter count/length")

    count = max(MIN_CHAPTERS, min(MAX_CHAPTERS, round(duration / 180)))
    starts = sorted({int(index * duration / count) for index in range(count)})
    starts[0] = 0
    # Deduplicating rounded starts can leave fewer than MIN_CHAPTERS; that only
    # happens for a very short, already-rejected duration, so it's unreachable
    # in practice, but guarded rather than silently returning too few.
    while len(starts) < MIN_CHAPTERS:
        starts.append(starts[-1] + MIN_CHAPTER_SECONDS)

    chapters = []
    for start in starts:
        chapters.append(Chapter(start_seconds=start, title=_title_near(transcript, start)))
    return tuple(chapters)


def _title_near(transcript: Transcript, start_seconds: int) -> str:
    for segment in transcript.segments:
        end = segment.end_seconds if segment.end_seconds is not None else segment.start_seconds
        if segment.start_seconds <= start_seconds <= end:
            words = segment.text.split()[:_TITLE_WORDS]
            if words:
                return " ".join(words)
    return f"Chapter at {start_seconds}s"
