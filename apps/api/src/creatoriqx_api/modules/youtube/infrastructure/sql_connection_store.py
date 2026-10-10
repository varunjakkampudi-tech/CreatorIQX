"""SQLAlchemy adapter for ``ChannelConnectionStore`` and ``ChannelVideoStore``.

Every statement runs under the caller's tenant context (set by the API
dependency before this is ever reached, mirroring ``workspaces.sql_store``).
Tokens are encrypted with the injected ``TokenCipher`` before they ever reach
the session - this module never holds a plaintext token longer than it takes
to encrypt or decrypt it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.youtube.application.ports import (
    ActiveConnection,
    ChannelVideoRecord,
    VideoStats,
)
from creatoriqx_api.modules.youtube.domain.connection import (
    PROVIDER_GOOGLE_YOUTUBE,
    ChannelInfo,
    ConnectedChannel,
    ConnectionStatus,
    OAuthTokens,
)
from creatoriqx_api.modules.youtube.domain.errors import ChannelNotConnectedError
from creatoriqx_api.modules.youtube.infrastructure.tables import (
    Channel,
    ChannelVideo,
    OAuthConnection,
)
from creatoriqx_api.platform.crypto import EncryptedValue, TokenCipher
from creatoriqx_api.platform.database import session_scope, set_tenant_context

# channels/oauth_connections' RLS policy only checks workspace_id, never
# user_id (migration 0006); reads and connection-maintenance writes have no
# acting user to attribute, so a nil UUID stands in (same convention as
# youtube.infrastructure.quota_ledger._NO_ACTOR and planning.sql_video_store).
_NO_ACTOR = uuid.UUID(int=0)


class SqlChannelConnectionStore:
    """Persists channels and their OAuth connections (spec §7)."""

    def __init__(self, factory: async_sessionmaker[AsyncSession], cipher: TokenCipher) -> None:
        self._factory = factory
        self._cipher = cipher

    async def save_connection(
        self,
        *,
        workspace_id: uuid.UUID,
        connected_by_user_id: uuid.UUID,
        tokens: OAuthTokens,
        channel: ChannelInfo,
    ) -> ConnectedChannel:
        async with session_scope(self._factory) as session:
            await set_tenant_context(
                session, workspace_id=workspace_id, user_id=connected_by_user_id
            )
            existing = await session.execute(
                select(Channel).where(
                    Channel.workspace_id == workspace_id,
                    Channel.youtube_channel_id == channel.youtube_channel_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                row = Channel(
                    workspace_id=workspace_id, youtube_channel_id=channel.youtube_channel_id
                )
                session.add(row)
            _apply_channel_info(row, channel)
            row.last_synced_at = datetime.now(UTC)
            await session.flush()

            access_encrypted = self._cipher.encrypt(tokens.access_token).to_storable()
            refresh_encrypted = (
                self._cipher.encrypt(tokens.refresh_token).to_storable()
                if tokens.refresh_token
                else None
            )
            existing_conn = await session.execute(
                select(OAuthConnection).where(
                    OAuthConnection.workspace_id == workspace_id,
                    OAuthConnection.channel_id == row.id,
                )
            )
            conn = existing_conn.scalar_one_or_none()
            if conn is None:
                conn = OAuthConnection(
                    workspace_id=workspace_id,
                    channel_id=row.id,
                    provider=PROVIDER_GOOGLE_YOUTUBE,
                    connected_by_user_id=connected_by_user_id,
                    scopes=list(tokens.scopes),
                    access_token_encrypted=access_encrypted,
                    access_token_expires_at=tokens.expires_at,
                    refresh_token_encrypted=refresh_encrypted,
                    status=ConnectionStatus.ACTIVE.value,
                )
                session.add(conn)
            else:
                conn.connected_by_user_id = connected_by_user_id
                conn.scopes = list(tokens.scopes)
                conn.access_token_encrypted = access_encrypted
                conn.access_token_expires_at = tokens.expires_at
                conn.refresh_token_encrypted = refresh_encrypted
                conn.status = ConnectionStatus.ACTIVE.value
            await session.flush()

            return _to_connected_channel(row, ConnectionStatus(conn.status))

    async def list_channels(self, workspace_id: uuid.UUID) -> list[ConnectedChannel]:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(Channel, OAuthConnection.status)
                .join(OAuthConnection, OAuthConnection.channel_id == Channel.id)
                .where(Channel.workspace_id == workspace_id)
                .order_by(Channel.created_at.desc())
            )
            return [
                _to_connected_channel(channel, ConnectionStatus(status))
                for channel, status in result.all()
            ]

    async def get_active_connection(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> ActiveConnection:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(Channel, OAuthConnection)
                .join(OAuthConnection, OAuthConnection.channel_id == Channel.id)
                .where(
                    Channel.workspace_id == workspace_id,
                    Channel.id == channel_id,
                    OAuthConnection.status == ConnectionStatus.ACTIVE.value,
                )
            )
            row = result.one_or_none()
            if row is None:
                raise ChannelNotConnectedError()
            channel, conn = row
            access_token = self._cipher.decrypt(
                EncryptedValue.from_storable(conn.access_token_encrypted)
            )
            refresh_token = (
                self._cipher.decrypt(EncryptedValue.from_storable(conn.refresh_token_encrypted))
                if conn.refresh_token_encrypted
                else None
            )
            return ActiveConnection(
                connection_id=conn.id,
                channel_id=channel.id,
                youtube_channel_id=channel.youtube_channel_id,
                uploads_playlist_id=channel.uploads_playlist_id,
                access_token=access_token,
                access_token_expires_at=conn.access_token_expires_at,
                refresh_token=refresh_token,
            )

    async def update_access_token(
        self, *, workspace_id: uuid.UUID, connection_id: uuid.UUID, tokens: OAuthTokens
    ) -> None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(OAuthConnection).where(
                    OAuthConnection.workspace_id == workspace_id,
                    OAuthConnection.id == connection_id,
                )
            )
            conn = result.scalar_one()
            conn.access_token_encrypted = self._cipher.encrypt(tokens.access_token).to_storable()
            conn.access_token_expires_at = tokens.expires_at
            if tokens.refresh_token:
                conn.refresh_token_encrypted = self._cipher.encrypt(
                    tokens.refresh_token
                ).to_storable()
            await session.flush()

    async def disconnect(self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID) -> None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(OAuthConnection).where(
                    OAuthConnection.workspace_id == workspace_id,
                    OAuthConnection.channel_id == channel_id,
                )
            )
            conn = result.scalar_one_or_none()
            if conn is None:
                raise ChannelNotConnectedError()
            conn.status = ConnectionStatus.REVOKED.value
            await session.flush()

    async def update_channel_stats(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, channel: ChannelInfo
    ) -> None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(Channel).where(
                    Channel.workspace_id == workspace_id, Channel.id == channel_id
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise ChannelNotConnectedError()
            _apply_channel_info(row, channel)
            row.last_synced_at = datetime.now(UTC)
            await session.flush()


class SqlChannelVideoStore:
    """Persists each channel's latest known video stats (spec §7: not a time series)."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def upsert_videos(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, videos: list[VideoStats]
    ) -> None:
        if not videos:
            return
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            for video in videos:
                stmt = (
                    pg_insert(ChannelVideo)
                    .values(
                        workspace_id=workspace_id,
                        channel_id=channel_id,
                        youtube_video_id=video.youtube_video_id,
                        title=video.title,
                        description=video.description,
                        published_at=video.published_at,
                        duration_seconds=video.duration_seconds,
                        view_count=video.view_count,
                        like_count=video.like_count,
                        comment_count=video.comment_count,
                    )
                    .on_conflict_do_update(
                        index_elements=["workspace_id", "channel_id", "youtube_video_id"],
                        set_={
                            "title": video.title,
                            "description": video.description,
                            "duration_seconds": video.duration_seconds,
                            "view_count": video.view_count,
                            "like_count": video.like_count,
                            "comment_count": video.comment_count,
                        },
                    )
                )
                await session.execute(stmt)

    async def list_videos(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> list[ChannelVideoRecord]:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)
            result = await session.execute(
                select(ChannelVideo)
                .where(
                    ChannelVideo.workspace_id == workspace_id,
                    ChannelVideo.channel_id == channel_id,
                )
                .order_by(ChannelVideo.published_at.desc())
            )
            return [
                ChannelVideoRecord(
                    id=row.id,
                    youtube_video_id=row.youtube_video_id,
                    title=row.title,
                    description=row.description,
                    published_at=row.published_at,
                    duration_seconds=row.duration_seconds,
                    view_count=row.view_count,
                    like_count=row.like_count,
                    comment_count=row.comment_count,
                )
                for row in result.scalars().all()
            ]


def _apply_channel_info(row: Channel, channel: ChannelInfo) -> None:
    row.title = channel.title
    row.thumbnail_url = channel.thumbnail_url
    row.subscriber_count = channel.subscriber_count
    row.view_count = channel.view_count
    row.video_count = channel.video_count
    row.uploads_playlist_id = channel.uploads_playlist_id


def _to_connected_channel(row: Channel, status: ConnectionStatus) -> ConnectedChannel:
    return ConnectedChannel(
        id=row.id,
        youtube_channel_id=row.youtube_channel_id,
        title=row.title,
        thumbnail_url=row.thumbnail_url,
        subscriber_count=row.subscriber_count,
        video_count=row.video_count,
        last_synced_at=row.last_synced_at,
        connection_status=status,
    )
