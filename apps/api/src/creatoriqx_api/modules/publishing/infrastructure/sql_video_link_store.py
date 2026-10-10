"""SQLAlchemy adapter for :class:`YoutubeVideoLinkStore`.

Enforces the ``(workspace_id, youtube_video_id)`` uniqueness rule at the
database layer too (migration 0009's ``UniqueConstraint``) - a conflicting
``create`` fails loudly rather than silently overwriting a link that
belongs to a different video.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.publishing.application.ports import NewYoutubeVideoLink
from creatoriqx_api.modules.publishing.domain.sync_state import SyncState
from creatoriqx_api.modules.publishing.domain.video_link import YoutubeVideoLink
from creatoriqx_api.modules.publishing.infrastructure.tables import YoutubeVideoLinkRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

_NO_ACTOR = uuid.UUID(int=0)


class SqlYoutubeVideoLinkStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(self, link: NewYoutubeVideoLink) -> YoutubeVideoLink:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=link.workspace_id, user_id=_NO_ACTOR)
            row = YoutubeVideoLinkRow(
                workspace_id=link.workspace_id,
                video_id=link.video_id,
                channel_id=link.channel_id,
                youtube_video_id=link.youtube_video_id,
                sync_state=SyncState.LINKED.value,
            )
            session.add(row)
            await session.flush()
            return _to_domain(row)

    async def get_for_video(
        self, *, workspace_id: uuid.UUID, video_id: uuid.UUID
    ) -> YoutubeVideoLink | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(YoutubeVideoLinkRow).where(
                    YoutubeVideoLinkRow.workspace_id == workspace_id,
                    YoutubeVideoLinkRow.video_id == video_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def get_by_youtube_video_id(
        self, *, workspace_id: uuid.UUID, youtube_video_id: str
    ) -> YoutubeVideoLink | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(YoutubeVideoLinkRow).where(
                    YoutubeVideoLinkRow.workspace_id == workspace_id,
                    YoutubeVideoLinkRow.youtube_video_id == youtube_video_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def update_sync_state(
        self,
        *,
        workspace_id: uuid.UUID,
        link_id: uuid.UUID,
        sync_state: SyncState,
        last_synced_at: datetime | None = None,
        last_remote_etag: str | None = None,
    ) -> YoutubeVideoLink:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(YoutubeVideoLinkRow).where(
                    YoutubeVideoLinkRow.workspace_id == workspace_id,
                    YoutubeVideoLinkRow.id == link_id,
                )
            )
            row = result.scalar_one()
            row.sync_state = sync_state.value
            if last_synced_at is not None:
                row.last_synced_at = last_synced_at
            if last_remote_etag is not None:
                row.last_remote_etag = last_remote_etag
            await session.flush()
            return _to_domain(row)


def _to_domain(row: YoutubeVideoLinkRow) -> YoutubeVideoLink:
    return YoutubeVideoLink(
        id=row.id,
        workspace_id=row.workspace_id,
        video_id=row.video_id,
        channel_id=row.channel_id,
        youtube_video_id=row.youtube_video_id,
        sync_state=SyncState(row.sync_state),
        linked_at=row.linked_at,
        last_synced_at=row.last_synced_at,
        last_remote_etag=row.last_remote_etag,
        created_at=row.created_at,
    )
