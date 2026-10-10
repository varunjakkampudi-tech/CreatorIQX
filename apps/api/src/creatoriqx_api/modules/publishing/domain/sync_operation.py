"""One attempted write against YouTube (spec §3: "Record every attempt as a
per-operation row ... not only a global status, so partial failure (title
synced, thumbnail failed) is visible").
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime


class SyncOperationStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_FALLBACK = "manual_fallback"


class SyncFieldGroup(enum.StrEnum):
    """Which part of the snapshot this operation applied (spec §7 ``field_group``)."""

    METADATA = "metadata"
    THUMBNAIL = "thumbnail"
    SCHEDULE = "schedule"


@dataclass(frozen=True, slots=True)
class SyncOperation:
    id: uuid.UUID
    workspace_id: uuid.UUID
    video_link_id: uuid.UUID
    applied_snapshot_id: uuid.UUID
    field_group: SyncFieldGroup
    status: SyncOperationStatus
    error_details: str | None
    quota_cost: int
    remote_etag: str | None
    readback_verified: bool
    finished_at: datetime | None
    created_at: datetime
