"""Ports the youtube application layer depends on.

Infrastructure implements these; the application never imports httpx,
SQLAlchemy or Redis directly. Mirrors the seam pattern already used by
``identity.application.ports`` and ``jobs.application.ports``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from creatoriqx_api.modules.youtube.domain.connection import (
    ChannelInfo,
    ConnectedChannel,
    OAuthTokens,
)


@dataclass(frozen=True, slots=True)
class ConnectFlowState:
    """The one-time state for a connect attempt in progress."""

    state: str
    redirect_uri: str


class YouTubeOAuthProvider(Protocol):
    """Google's OAuth 2.0 endpoints for the YouTube connection (not the login client)."""

    def build_authorization_url(self, redirect_uri: str, state: str) -> str:
        """The URL to send the browser to, requesting ``CONNECT_SCOPES``."""

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        """Exchange the authorization code for an access/refresh token pair."""

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        """Mint a new access token from a stored refresh token."""


@dataclass(frozen=True, slots=True)
class ActiveConnection:
    """What the ingestion service needs to call the API as one channel's owner."""

    connection_id: uuid.UUID
    channel_id: uuid.UUID
    youtube_channel_id: str
    uploads_playlist_id: str | None
    access_token: str
    access_token_expires_at: datetime
    refresh_token: str | None


class ChannelConnectionStore(Protocol):
    """Persists OAuth connections and the channels they grant access to."""

    async def save_connection(
        self,
        *,
        workspace_id: uuid.UUID,
        connected_by_user_id: uuid.UUID,
        tokens: OAuthTokens,
        channel: ChannelInfo,
    ) -> ConnectedChannel:
        """Create or replace this workspace's connection and its channel row."""

    async def list_channels(self, workspace_id: uuid.UUID) -> list[ConnectedChannel]:
        """Every channel connected in this workspace, most recently connected first."""

    async def get_active_connection(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> ActiveConnection:
        """The live connection backing ``channel_id``, or raise ``ChannelNotConnectedError``."""

    async def update_access_token(self, *, connection_id: uuid.UUID, tokens: OAuthTokens) -> None:
        """Persist a freshly refreshed access token (and expiry) for this connection."""

    async def disconnect(self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID) -> None:
        """Revoke this workspace's connection; the channel row is kept for history."""

    async def update_channel_stats(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, channel: ChannelInfo
    ) -> None:
        """Refresh a connected channel's own stats and mark it synced now."""


class YouTubeDataApiClient(Protocol):
    """The subset of the YouTube Data API v3 this module calls (spec §3)."""

    async def get_own_channel(self, access_token: str, *, workspace_id: uuid.UUID) -> ChannelInfo:
        """``channels.list(mine=true)`` for the token's own channel."""

    async def list_uploads(
        self, access_token: str, *, workspace_id: uuid.UUID, uploads_playlist_id: str, limit: int
    ) -> list[str]:
        """Video ids from the channel's uploads playlist (``playlistItems.list``, spec §3:
        discover manually uploaded videos through the uploads playlist, never ``search.list``).
        """

    async def list_video_stats(
        self, access_token: str, *, workspace_id: uuid.UUID, video_ids: list[str]
    ) -> list[VideoStats]:
        """``videos.list`` statistics and content details for up to 50 ids at a time."""


@dataclass(frozen=True, slots=True)
class VideoStats:
    """One video's metadata and stats, as read from ``videos.list``."""

    youtube_video_id: str
    title: str
    description: str
    published_at: datetime
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None


class QuotaLedger(Protocol):
    """Per-workspace-per-day quota reservation (spec §6 Quota management)."""

    async def reserve(
        self, *, workspace_id: uuid.UUID, provider: str, endpoint: str, units: int
    ) -> None:
        """Reserve ``units``, or raise ``QuotaExhaustedError``.

        Also appends to the durable ledger.
        """


@dataclass(frozen=True, slots=True)
class ChannelVideoRecord:
    """A video's latest known stats, as persisted (spec §7: not a time series -
    retention history is Phase 2A scope; this is the current-state row the
    Phase 1A audit feature reads).
    """

    id: uuid.UUID
    youtube_video_id: str
    title: str
    description: str
    published_at: datetime
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None


class ChannelVideoStore(Protocol):
    """Persists the latest known stats for a channel's videos."""

    async def upsert_videos(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID, videos: list[VideoStats]
    ) -> None:
        """Insert or refresh each video's stats row, keyed by youtube_video_id."""

    async def list_videos(
        self, *, workspace_id: uuid.UUID, channel_id: uuid.UUID
    ) -> list[ChannelVideoRecord]:
        """Every known video for this channel, most recently published first."""
