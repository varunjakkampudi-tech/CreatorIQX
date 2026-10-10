"""Pure parsing for the two text-based transcript sources (paste, upload).

No third-party dependency: SRT's timestamp grammar is simple enough to parse
with the standard library, and WebVTT uses the same block shape with ``.``
instead of ``,`` for milliseconds and no block index line, so one parser
covers both. Anything that doesn't look like either is treated as plain
text - a single untimed segment - which is exactly what a creator pasting a
script-style transcript expects.
"""

from __future__ import annotations

import re

from creatoriqx_api.modules.transcripts.domain.transcript import TranscriptSegment

_TIMESTAMP = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)


def parse_plain_text(text: str) -> tuple[TranscriptSegment, ...]:
    """One untimed segment holding the whole text (spec feature 22: ``pasted``)."""
    cleaned = text.strip()
    return (TranscriptSegment(start_seconds=0.0, end_seconds=None, text=cleaned),)


def parse_subtitle_blocks(text: str) -> tuple[TranscriptSegment, ...]:
    """Parse SRT or WebVTT-style ``HH:MM:SS,mmm --> HH:MM:SS,mmm`` blocks.

    Returns an empty tuple if no timestamp line is found, so the caller can
    fall back to :func:`parse_plain_text` for a file that isn't actually
    timed subtitles.
    """
    segments: list[TranscriptSegment] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _TIMESTAMP.search(lines[i])
        if match is None:
            i += 1
            continue
        start = _to_seconds(*match.groups()[:4])
        end = _to_seconds(*match.groups()[4:])
        i += 1
        body_lines: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            body_lines.append(lines[i].strip())
            i += 1
        body = " ".join(body_lines).strip()
        if body:
            segments.append(TranscriptSegment(start_seconds=start, end_seconds=end, text=body))
    return tuple(segments)


def _to_seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000
