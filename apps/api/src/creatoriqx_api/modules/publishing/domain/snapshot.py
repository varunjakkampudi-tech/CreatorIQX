"""The immutable publish snapshot (spec §3 "Approval invalidation", ADR 0006).

A :class:`PublishSnapshot` is built from the *current* version ids of each
snapshot-bound artifact at the moment of approval - never from "latest" at
sync time (spec §3: "Publishing only ever reads from a publish_snapshot,
never from 'latest'."). Once created it is never mutated; a later edit to
any of the artifacts it points to does not change the snapshot - it moves
the video back to ``in_review`` instead (approval invalidation), and a new
approval creates a brand-new snapshot row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from creatoriqx_api.modules.planning.domain.video import VideoStatus

# A video must be in one of these statuses for a new snapshot to be built
# (spec §3's approval gate: the happy path is in_review -> approved, and a
# re-approval after an edit is also in_review -> approved).
SNAPSHOT_ELIGIBLE_STATUSES = frozenset({VideoStatus.IN_REVIEW})


@dataclass(frozen=True, slots=True)
class PublishSnapshot:
    """Immutable. See module docstring - this dataclass is never constructed with
    an id that already exists in the store; ``SqlPublishSnapshotStore`` is
    insert-only at the privilege layer too (ADR 0006).
    """

    id: uuid.UUID
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    script_version_id: uuid.UUID
    metadata_version_id: uuid.UUID
    chapter_version_id: uuid.UUID | None
    thumbnail_variant_id: uuid.UUID | None
    disclosure_altered: bool
    disclosure_synthetic: bool
    scheduled_at: datetime | None
    approved_by: uuid.UUID
    approved_at: datetime
    created_at: datetime


def assert_video_eligible_for_snapshot(status: VideoStatus) -> None:
    """Refuse to build a snapshot from a video that is not in_review (spec §3,
    §13: "Nothing is published without approval.").
    """
    from creatoriqx_api.modules.publishing.domain.errors import (
        VideoNotReadyForSnapshotError,
    )

    if status not in SNAPSHOT_ELIGIBLE_STATUSES:
        raise VideoNotReadyForSnapshotError(
            f"video is {status.value!r}; must be 'in_review' to approve"
        )
