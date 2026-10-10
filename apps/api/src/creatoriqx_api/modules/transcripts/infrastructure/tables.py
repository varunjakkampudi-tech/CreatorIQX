"""ORM tables owned by the transcripts module (spec §7, Phase 1C).

``transcripts`` is the version header; ``transcript_segments`` are its
ordered lines. Both carry ``workspace_id`` directly (denormalized onto the
child row) rather than relying on a join through ``transcript_id`` for RLS,
the same pattern ``channel_videos``/``recommendations`` already use for
their own child/owned rows - a flat ``WHERE workspace_id = ...`` policy is
simpler and faster than a subquery-based one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class TranscriptRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One version of a video's transcript. Write-once: no update method exists."""

    __tablename__ = "transcripts"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    video_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_transcript_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transcripts.id"), default=None
    )


class TranscriptSegmentRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One ordered line of a transcript."""

    __tablename__ = "transcript_segments"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transcripts.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
