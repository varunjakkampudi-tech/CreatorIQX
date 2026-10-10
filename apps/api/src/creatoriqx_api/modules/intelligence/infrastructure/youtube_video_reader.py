"""Adapts the youtube module's own ``ChannelVideoStore`` into intelligence's
``ChannelVideoReader`` (spec §3 module rule: consume another module only
through its public interface - here, its application-layer port, never its
ORM tables or infrastructure directly).
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.intelligence.domain.audit import AuditVideo
from creatoriqx_api.modules.youtube.application.ports import ChannelVideoStore


class YouTubeChannelVideoReader:
    """Reads a channel's videos via the youtube module's own store."""

    def __init__(self, video_store: ChannelVideoStore) -> None:
        self._video_store = video_store

    async def list_videos(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> list[AuditVideo]:
        records = await self._video_store.list_videos(
            workspace_id=workspace_id, channel_id=channel_id
        )
        return [
            AuditVideo(
                youtube_video_id=record.youtube_video_id,
                title=record.title,
                published_at=record.published_at,
                view_count=record.view_count,
                like_count=record.like_count,
                comment_count=record.comment_count,
            )
            for record in records
        ]
