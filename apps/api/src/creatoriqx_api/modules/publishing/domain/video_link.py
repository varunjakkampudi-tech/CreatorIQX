"""The link between a local video and a real YouTube video (spec §7
``youtube_video_links``). Separate from ``publish_snapshots`` and from the
video lifecycle status - this dataclass carries only the sync-state side.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from creatoriqx_api.modules.publishing.domain.sync_state import SyncState


@dataclass(frozen=True, slots=True)
class YoutubeVideoLink:
    id: uuid.UUID
    workspace_id: uuid.UUID
    video_id: uuid.UUID
    channel_id: uuid.UUID
    youtube_video_id: str
    sync_state: SyncState
    linked_at: datetime
    last_synced_at: datetime | None
    last_remote_etag: str | None
    created_at: datetime
