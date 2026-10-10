"""The video-lifecycle use case: state-machine transitions for the Video Board.

Every transition is validated against the domain's ``ALLOWED_TRANSITIONS``
graph before the store is asked to persist it (spec §3: "allowed transitions
enforced in the domain layer"). The store itself is responsible for writing
the audit log entry and emitting the domain event in the same transaction as
the status write (spec §3: "Every transition writes an audit log entry and
emits a domain event").
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.planning.application.ports import VideoStore
from creatoriqx_api.modules.planning.domain.errors import VideoNotFoundError
from creatoriqx_api.modules.planning.domain.transitions import assert_transition
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus


class VideoLifecycleService:
    """Move a video through ``idea -> ... -> analyzed`` (plus reject/archive)."""

    def __init__(self, video_store: VideoStore) -> None:
        self._videos = video_store

    async def list_board(self, *, workspace_id: uuid.UUID) -> list[Video]:
        return await self._videos.list_for_workspace(workspace_id=workspace_id)

    async def transition(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        to_status: VideoStatus,
        actor_user_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> Video:
        video = await self._videos.get(workspace_id=workspace_id, video_id=video_id)
        if video is None:
            raise VideoNotFoundError()

        assert_transition(video.status, to_status)

        return await self._videos.update_status(
            workspace_id=workspace_id,
            video_id=video_id,
            status=to_status,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
