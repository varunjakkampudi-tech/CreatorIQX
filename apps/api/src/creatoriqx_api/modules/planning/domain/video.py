"""The video lifecycle state machine (spec §3 "Video state machine", feature 4/13).

Pure data and pure rules: no SQL, no HTTP. Every transition in
``ALLOWED_TRANSITIONS`` is a domain invariant, not an application-layer
convenience - the application layer calls :func:`assert_transition` before
persisting a status change, and never writes a status directly.

Terminal/park states ``rejected`` and ``archived`` are reachable from the
working states (spec §3), and ``rejected`` work can resume by returning to
``drafting``. The approval-invalidation rule (spec §3: an edit after
``approved`` returns the video to ``in_review`` and a new approval creates a
new snapshot) belongs to Phase 1D once ``publish_snapshots`` exists; this
phase only needs the state machine itself to exist and be enforced.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime


class VideoStatus(enum.StrEnum):
    """One node of the lifecycle graph (spec §3)."""

    IDEA = "idea"
    PLANNED = "planned"
    DRAFTING = "drafting"
    QA = "qa"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ANALYZED = "analyzed"
    REJECTED = "rejected"
    ARCHIVED = "archived"


# Every working state may also be archived directly (a creator abandoning an
# idea or a draft), so ARCHIVED is unioned onto each edge set below rather
# than repeated on every line.
_ARCHIVABLE = frozenset({VideoStatus.ARCHIVED})

ALLOWED_TRANSITIONS: dict[VideoStatus, frozenset[VideoStatus]] = {
    VideoStatus.IDEA: frozenset({VideoStatus.PLANNED}) | _ARCHIVABLE,
    VideoStatus.PLANNED: frozenset({VideoStatus.DRAFTING}) | _ARCHIVABLE,
    VideoStatus.DRAFTING: frozenset({VideoStatus.QA}) | _ARCHIVABLE,
    # QA failures loop back to Creation (spec feature 12); QA->IN_REVIEW is
    # the happy path once the pre-publish checklist passes.
    VideoStatus.QA: frozenset({VideoStatus.DRAFTING, VideoStatus.IN_REVIEW}) | _ARCHIVABLE,
    VideoStatus.IN_REVIEW: frozenset(
        {VideoStatus.APPROVED, VideoStatus.REJECTED, VideoStatus.DRAFTING}
    )
    | _ARCHIVABLE,
    # Approval invalidation (spec §3): a post-approval edit returns here, not
    # forward. Phase 1D wires the trigger; the edge is a domain invariant now.
    VideoStatus.APPROVED: frozenset({VideoStatus.SCHEDULED, VideoStatus.IN_REVIEW}) | _ARCHIVABLE,
    VideoStatus.SCHEDULED: frozenset({VideoStatus.PUBLISHED, VideoStatus.IN_REVIEW}) | _ARCHIVABLE,
    VideoStatus.PUBLISHED: frozenset({VideoStatus.ANALYZED}) | _ARCHIVABLE,
    VideoStatus.ANALYZED: _ARCHIVABLE,
    # Rejected work resumes from Creation; it is a park state, not a dead end.
    VideoStatus.REJECTED: frozenset({VideoStatus.DRAFTING}) | _ARCHIVABLE,
    VideoStatus.ARCHIVED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Video:
    """One video or Short moving through the lifecycle (spec §7 ``videos``)."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    channel_id: uuid.UUID | None
    plan_id: uuid.UUID | None
    title: str
    status: VideoStatus
    created_at: datetime
    updated_at: datetime
