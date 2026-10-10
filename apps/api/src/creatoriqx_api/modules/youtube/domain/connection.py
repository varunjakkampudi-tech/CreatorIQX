"""YouTube connection domain types (spec §3, §10).

Pure data: no SQL, no HTTP. ``CONNECT_SCOPES`` is the Phase 1A read-only
scope set - a separate OAuth flow from login (spec §10), requested
incrementally: write/upload scopes are added only when a later phase enables
the capability that needs them (spec §3 capability model), never bundled in
here "just in case".
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime

# Verified against the current YouTube Data API v3 OAuth 2.0 scopes
# documentation (spec rule 3): read-only access to a channel's own data.
# https://developers.google.com/youtube/v3/guides/auth/installed-apps
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
CONNECT_SCOPES = (YOUTUBE_READONLY_SCOPE,)

PROVIDER_GOOGLE_YOUTUBE = "google_youtube"


class ConnectionStatus(enum.StrEnum):
    """Lifecycle of one workspace's YouTube OAuth connection."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    """Tokens returned by Google's token endpoint, before encryption."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChannelInfo:
    """A channel's own data, as read from ``channels.list`` (``mine=true``)."""

    youtube_channel_id: str
    title: str
    thumbnail_url: str | None
    subscriber_count: int | None
    view_count: int | None
    video_count: int | None
    uploads_playlist_id: str | None


@dataclass(frozen=True, slots=True)
class ConnectedChannel:
    """A channel this workspace has connected, as returned to the API layer."""

    id: uuid.UUID
    youtube_channel_id: str
    title: str
    thumbnail_url: str | None
    subscriber_count: int | None
    video_count: int | None
    last_synced_at: datetime | None
    connection_status: ConnectionStatus
