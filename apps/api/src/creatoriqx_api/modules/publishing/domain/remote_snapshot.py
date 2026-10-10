"""The last-read, normalized state of a linked YouTube video (spec §7
``remote_snapshots``), used for drift comparison and schedule-eligibility
checks. Each read supersedes the previous row rather than updating it in
place, so history of what was seen is never lost.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RemoteSnapshot:
    id: uuid.UUID
    workspace_id: uuid.UUID
    video_link_id: uuid.UUID
    fields: dict[str, object]
    privacy_status: str
    has_been_published: bool
    captured_at: datetime
