"""Typed domain errors for the transcripts module (spec §8, §12)."""

from __future__ import annotations

from creatoriqx_api.platform.errors import DomainError


class TranscriptNotFoundError(DomainError):
    """No transcript with the given id exists in this workspace."""

    status = 404
    title = "Transcript not found"
    code = "transcript-not-found"


class EmptyTranscriptError(DomainError):
    """A transcript must have at least one segment of text."""

    status = 422
    title = "A transcript needs at least one segment of text"
    code = "transcript-empty"


class TranscriptSourceUnavailableError(DomainError):
    """A transcript source exists in the abstraction but is not wired up yet.

    Covers ``youtube_captions`` (needs a caption-download scope and format
    handling not built in Phase 1C - OQ-21) and ``local_whisper`` (needs
    ``faster-whisper`` installed, which this build environment cannot do -
    spec feature 22: "built and time-boxed but is not a PASS blocker for
    Phase 1C"). Both are real, named gaps, not silent no-ops.
    """

    status = 501
    title = "This transcript source is not available yet"
    code = "transcript-source-unavailable"

    def __init__(self, source: str) -> None:
        self.source = source
        super().__init__(f"{source!r} is not wired up in this build")
