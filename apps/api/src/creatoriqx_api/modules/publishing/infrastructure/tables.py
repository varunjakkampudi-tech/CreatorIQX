"""ORM tables owned by the publishing module (spec §7, Phase 1D).

``publish_snapshots`` is the immutable record of exactly what was approved
(ADR 0006): the *current* version ids of each artifact at the moment of
approval, read from ``content``'s version tables rather than from pointer
columns on ``videos`` (Known gap 3, ADR 0014; no cross-module write needed).
The app role gets INSERT and SELECT only on this table - no UPDATE, no
DELETE - enforced by migration 0009's GRANT statements, not just by
convention.

``youtube_video_links`` is the sync-state link between a local video and a
real YouTube video id (separate from the video lifecycle state machine,
spec §3). ``sync_operations`` is one row per attempted write (not just a
global status), so partial failure is visible. ``remote_snapshots`` is the
last-read normalized state of the linked YouTube video, used for drift
comparison and schedule-eligibility checks.

All four are ordinary tenant tables: forced RLS, one ``FOR ALL`` policy
each, the same pattern as every prior tenant table.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class PublishSnapshotRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Immutable. Never updated or deleted by the app role after insert."""

    __tablename__ = "publish_snapshots"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    script_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    metadata_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    chapter_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    thumbnail_variant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    disclosure_altered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disclosure_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    approved_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class YoutubeVideoLinkRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "youtube_video_links"
    __table_args__ = (UniqueConstraint("workspace_id", "youtube_video_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("channels.id"), nullable=False)
    youtube_video_id: Mapped[str] = mapped_column(String(32), nullable=False)
    sync_state: Mapped[str] = mapped_column(String(20), nullable=False, default="linked")
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_remote_etag: Mapped[str | None] = mapped_column(String(200), default=None)


class SyncOperationRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "sync_operations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_link_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("youtube_video_links.id"), nullable=False
    )
    applied_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("publish_snapshots.id"), nullable=False
    )
    field_group: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_details: Mapped[str | None] = mapped_column(Text, default=None)
    quota_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remote_etag: Mapped[str | None] = mapped_column(String(200), default=None)
    readback_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class RemoteSnapshotRow(UUIDPrimaryKeyMixin, Base):
    """Normalized managed fields as last read from YouTube. Superseded, not updated."""

    __tablename__ = "remote_snapshots"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_link_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("youtube_video_links.id"), nullable=False
    )
    fields: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    privacy_status: Mapped[str] = mapped_column(String(20), nullable=False)
    has_been_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
