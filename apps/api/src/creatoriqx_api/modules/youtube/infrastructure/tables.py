"""ORM tables owned by the youtube module (spec §7).

``channels`` holds one connected YouTube channel's own identity and latest
stats. ``oauth_connections`` holds the encrypted tokens granting access to
it - a separate row so a reconnect can replace the tokens without losing the
channel's history. ``channel_videos`` holds the *latest known* stats per
video (not a time series: retention history is Phase 2A scope, spec §4
feature #15). ``quota_ledger`` is the durable, append-only record of every
YouTube API call made, mirrored from the live Redis counter (spec §6).

All four are ordinary tenant tables: forced RLS, one ``FOR ALL`` policy each,
the same pattern as every other tenant table (``0004_platform_tables.py``,
``0005_workspaces_rls.py``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Channel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A YouTube channel connected to a workspace."""

    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("workspace_id", "youtube_channel_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    youtube_channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    subscriber_count: Mapped[int | None] = mapped_column(Integer, default=None)
    view_count: Mapped[int | None] = mapped_column(Integer, default=None)
    video_count: Mapped[int | None] = mapped_column(Integer, default=None)
    uploads_playlist_id: Mapped[str | None] = mapped_column(String(64), default=None)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class OAuthConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Encrypted OAuth tokens granting access to one connected channel."""

    __tablename__ = "oauth_connections"
    __table_args__ = (UniqueConstraint("workspace_id", "channel_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("channels.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Base64(nonce):base64(ciphertext) under crypto.EncryptedValue.to_storable();
    # never the plaintext token (spec §10: encrypted at rest, never logged).
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class ChannelVideo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A channel's video, with its latest known stats (upserted on ingestion)."""

    __tablename__ = "channel_videos"
    __table_args__ = (UniqueConstraint("workspace_id", "channel_id", "youtube_video_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("channels.id"), nullable=False)
    youtube_video_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    view_count: Mapped[int | None] = mapped_column(Integer, default=None)
    like_count: Mapped[int | None] = mapped_column(Integer, default=None)
    comment_count: Mapped[int | None] = mapped_column(Integer, default=None)


class YoutubeCapabilityRow(Base):
    """What *this app's* Google API project is verified to do (ADR 0007, Phase 1D).

    Deliberately **not** a tenant table: there is one Google Cloud project
    per deployment (not per workspace), so its audit/verification status is
    app-level config, not per-tenant data. No ``workspace_id`` column, so the
    RLS meta-test (``tests/integration/test_rls.py``, which discovers tenant
    tables purely by the presence of a ``workspace_id`` column) skips it
    automatically - no explicit allow-list edit needed. Rows are seeded by a
    script/fixture, not created through a tenant-scoped request.
    """

    __tablename__ = "youtube_capabilities"

    capability: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="restricted")
    verified_on: Mapped[date | None] = mapped_column(Date, default=None)
    source_url: Mapped[str | None] = mapped_column(String(2048), default=None)
    required_scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    verification_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()", onupdate=datetime.utcnow
    )


class QuotaLedgerEntry(UUIDPrimaryKeyMixin, Base):
    """One durable record of a YouTube API call's quota cost (spec §6, §7).

    Append-only; no ``updated_at``. The live, atomic per-day counter lives in
    Redis (``RedisPostgresQuotaLedger``) - this table is the history that
    survives a Redis flush and lets a quota report be rebuilt from scratch.
    """

    __tablename__ = "quota_ledger"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
