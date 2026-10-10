"""Pre-publish QA checklist (spec feature 12).

Pure domain logic: every check is a function of already-gathered data, never
a database or HTTP call. The application layer (``QaService``) gathers the
video's current artifacts from the other modules' public ports and hands
them here as a single :class:`QaInput`; a failing check names exactly what
to fix, so a failure "returns to Creation with specific fixes" (the spec's
own acceptance wording) rather than a generic rejection.

Reuses ``content``'s own pure validators (chapter rules, title/description
character limits) rather than re-implementing them, since re-implementing
would let the two drift apart. This is a read of ``content``'s public
domain functions, not a write to its tables - allowed under spec §3's module
boundary rule.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field

from creatoriqx_api.modules.content.domain.chapters import Chapter, validate_chapters
from creatoriqx_api.modules.content.domain.metadata import (
    TITLE_MAX_LENGTH,
    character_limit_warnings,
)


class QaCheckId(enum.StrEnum):
    """One row of the pre-publish checklist (spec feature 12)."""

    TITLE = "title"
    HOOK = "hook"
    SEO = "seo"
    CHAPTERS = "chapters"
    THUMBNAIL = "thumbnail"
    DISCLOSURE = "disclosure"
    SCHEDULE = "schedule"


@dataclass(frozen=True, slots=True)
class QaCheck:
    """One checklist row's outcome. ``reasons`` is empty exactly when ``passed``."""

    id: QaCheckId
    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class QaResult:
    """The full checklist outcome for one video, at one point in time.

    Never persisted as a standing "QA record" the caller trusts later -
    ``ApprovalService`` re-runs the checklist against the video's *current*
    artifacts immediately before building a snapshot, so a QA pass can never
    be stale by the time it gates an approval.
    """

    video_id: uuid.UUID
    checks: tuple[QaCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failing_checks(self) -> tuple[QaCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)


@dataclass(frozen=True, slots=True)
class QaInput:
    """Everything the checklist needs, already read from the owning modules by the
    application layer. Keeping this a plain dataclass (rather than importing live
    ``ScriptVersion``/``MetadataVersion`` objects) keeps the domain layer's only
    cross-module dependency the two pure functions imported above.
    """

    title: str
    hook: str
    description: str
    tags: tuple[str, ...]
    chapters: tuple[Chapter, ...] | None
    has_thumbnail: bool
    disclosure_altered: bool
    disclosure_synthetic: bool
    wants_scheduling: bool
    # None when the video has no YouTube link yet.
    linked_video_privacy_status: str | None
    linked_video_has_been_published: bool | None


MIN_HOOK_LENGTH = 10
MIN_TAGS = 1


def _check_title(qa_input: QaInput) -> QaCheck:
    reasons: list[str] = []
    if not qa_input.title.strip():
        reasons.append("title is empty")
    elif len(qa_input.title) > TITLE_MAX_LENGTH:
        reasons.append(
            f"title is {len(qa_input.title)} characters; YouTube truncates past {TITLE_MAX_LENGTH}"
        )
    return QaCheck(id=QaCheckId.TITLE, passed=not reasons, reasons=tuple(reasons))


def _check_hook(qa_input: QaInput) -> QaCheck:
    reasons: list[str] = []
    if not qa_input.hook.strip():
        reasons.append("hook is empty")
    elif len(qa_input.hook.strip()) < MIN_HOOK_LENGTH:
        reasons.append(f"hook is shorter than {MIN_HOOK_LENGTH} characters")
    return QaCheck(id=QaCheckId.HOOK, passed=not reasons, reasons=tuple(reasons))


def _check_seo(qa_input: QaInput) -> QaCheck:
    reasons: list[str] = []
    if not qa_input.description.strip():
        reasons.append("description is empty")
    if len(qa_input.tags) < MIN_TAGS:
        reasons.append("no tags set")
    reasons.extend(character_limit_warnings(title=qa_input.title, description=qa_input.description))
    return QaCheck(id=QaCheckId.SEO, passed=not reasons, reasons=tuple(reasons))


def _check_chapters(qa_input: QaInput) -> QaCheck:
    # Chapters are optional (spec feature 10 is Core, but a video can be
    # approved without them - nothing requires every video to have chapters).
    if qa_input.chapters is None:
        return QaCheck(id=QaCheckId.CHAPTERS, passed=True)
    reasons = validate_chapters(qa_input.chapters)
    return QaCheck(id=QaCheckId.CHAPTERS, passed=not reasons, reasons=tuple(reasons))


def _check_thumbnail(qa_input: QaInput) -> QaCheck:
    # Advisory, not blocking (Known gap 3: no thumbnail producer in Core yet).
    reasons = () if qa_input.has_thumbnail else ("no thumbnail set (advisory only)",)
    return QaCheck(id=QaCheckId.THUMBNAIL, passed=True, reasons=reasons)


def _check_disclosure(qa_input: QaInput) -> QaCheck:
    # Always passes today - this row exists so the checklist surfaces the
    # disclosure flags for the creator to confirm before approval, per spec
    # feature 12; there is no rule yet under which a disclosure flag value is
    # itself wrong.
    return QaCheck(id=QaCheckId.DISCLOSURE, passed=True)


def _check_schedule(qa_input: QaInput) -> QaCheck:
    if not qa_input.wants_scheduling:
        return QaCheck(id=QaCheckId.SCHEDULE, passed=True)
    if qa_input.linked_video_privacy_status is None:
        return QaCheck(
            id=QaCheckId.SCHEDULE,
            passed=False,
            reasons=("scheduling was requested but no YouTube video is linked yet",),
        )
    reasons: list[str] = []
    if qa_input.linked_video_privacy_status != "private":
        reasons.append(
            "scheduling was requested but the linked video is "
            f"{qa_input.linked_video_privacy_status!r}, not private"
        )
    if qa_input.linked_video_has_been_published:
        reasons.append(
            "scheduling was requested but the linked video has already been published once"
        )
    return QaCheck(id=QaCheckId.SCHEDULE, passed=not reasons, reasons=tuple(reasons))


def run_qa_checklist(video_id: uuid.UUID, qa_input: QaInput) -> QaResult:
    """Run every checklist row and return the combined result (spec feature 12)."""
    checks = (
        _check_title(qa_input),
        _check_hook(qa_input),
        _check_seo(qa_input),
        _check_chapters(qa_input),
        _check_thumbnail(qa_input),
        _check_disclosure(qa_input),
        _check_schedule(qa_input),
    )
    return QaResult(video_id=video_id, checks=checks)
