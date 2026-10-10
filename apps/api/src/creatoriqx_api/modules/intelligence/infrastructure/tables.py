"""The ``recommendations`` ORM table (spec §7). Owning bounded context: intelligence."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class RecommendationRow(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One AI suggestion, shared across every module that produces them."""

    __tablename__ = "recommendations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("channels.id"), default=None
    )
    video_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_strength: Mapped[str] = mapped_column(String(10), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
