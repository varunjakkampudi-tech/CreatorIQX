"""Chapter versions (spec feature 10), validated against YouTube's own rules.

Verified against current YouTube Help (spec rule 3, recorded in
``docs/YOUTUBE_CAPABILITIES.md``): a chapter list must start at ``00:00``,
have at least 3 timestamps, be strictly ascending, and space each chapter at
least 10 seconds from the next. This module enforces exactly that, in the
domain layer, before any chapter version is ever persisted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise

MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10


@dataclass(frozen=True, slots=True)
class Chapter:
    """One timestamped chapter marker."""

    start_seconds: int
    title: str


@dataclass(frozen=True, slots=True)
class ChapterVersion:
    """One version of a video's chapter list, tied to the transcript it was built from."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    transcript_id: uuid.UUID
    chapters: tuple[Chapter, ...]
    parent_version_id: uuid.UUID | None
    is_current: bool
    created_at: datetime


def validate_chapters(chapters: tuple[Chapter, ...]) -> list[str]:
    """Return every rule a chapter list violates; an empty list means it's valid."""
    reasons: list[str] = []
    if len(chapters) < MIN_CHAPTERS:
        reasons.append(f"needs at least {MIN_CHAPTERS} chapters, got {len(chapters)}")
    if not chapters:
        return reasons
    if chapters[0].start_seconds != 0:
        reasons.append("the first chapter must start at 00:00")
    for previous, current in pairwise(chapters):
        if current.start_seconds <= previous.start_seconds:
            reasons.append(
                f"chapter start times must be strictly ascending "
                f"({previous.start_seconds}s is not before {current.start_seconds}s)"
            )
        elif current.start_seconds - previous.start_seconds < MIN_CHAPTER_SECONDS:
            reasons.append(
                f"each chapter must be at least {MIN_CHAPTER_SECONDS}s long "
                f"({previous.start_seconds}s -> {current.start_seconds}s is too short)"
            )
    return reasons
