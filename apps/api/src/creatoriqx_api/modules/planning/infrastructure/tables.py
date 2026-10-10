"""ORM tables owned by the planning module (spec §7, Phase 1B).

``plans`` is the backlog/calendar entry (spec feature 4). ``videos`` is the
start of the video aggregate (spec §7): identity, current lifecycle status,
and a pointer back to the plan it was promoted from. Later phases add the
versioned-artifact tables (``script_versions``, ``metadata_versions``, ...)
alongside this one, each owned by its own module - ``videos`` itself stays
owned here, since the lifecycle state machine is this module's domain.

Both are ordinary tenant tables: forced RLS, one ``FOR ALL`` policy each,
the same pattern as every other tenant table (``0006_youtube_and_intelligence.py``).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PlanRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A backlog/calendar entry, promotable to a video exactly once."""

    __tablename__ = "plans"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    series: Mapped[str | None] = mapped_column(String(255), default=None)
    scheduled_date: Mapped[date | None] = mapped_column(Date, default=None)
    # Set once, by promotion. No FK to videos.id to avoid a circular
    # create-order dependency within one transaction; referential integrity
    # is enforced by the application layer, which always creates the video
    # before marking the plan promoted.
    promoted_video_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)


class VideoRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One video or Short moving through the lifecycle (spec §3, §7)."""

    __tablename__ = "videos"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("plans.id"), default=None)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="idea")
