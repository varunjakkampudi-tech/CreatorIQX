"""Typed domain errors for the content module (spec §8, §12)."""

from __future__ import annotations

from creatoriqx_api.platform.errors import DomainError


class ScriptVersionNotFoundError(DomainError):
    status = 404
    title = "Script version not found"
    code = "script-version-not-found"


class MetadataVersionNotFoundError(DomainError):
    status = 404
    title = "Metadata version not found"
    code = "metadata-version-not-found"


class ChapterVersionNotFoundError(DomainError):
    status = 404
    title = "Chapter version not found"
    code = "chapter-version-not-found"


class ChapterValidationError(DomainError):
    """``chapters`` violates one or more of YouTube's chapter rules."""

    status = 422
    title = "This chapter list does not meet YouTube's chapter rules"
    code = "chapter-validation-failed"

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class TranscriptRequiredForChaptersError(DomainError):
    """Chapter generation needs a transcript with real end-times on every segment."""

    status = 422
    title = "Chapters can only be generated from a fully timed transcript"
    code = "chapter-generation-needs-timed-transcript"


class TranscriptNotFoundForChaptersError(DomainError):
    status = 404
    title = "Transcript not found"
    code = "chapter-generation-transcript-not-found"
