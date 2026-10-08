"""Usage event ORM table (spec §6, §9). Owning bounded context: telemetry.

A tenant table (``workspace_id`` is not nullable): forced RLS applies like any
other tenant table. ``properties`` holds only allow-listed keys; the port that
writes here (P0-062) enforces the allow-list, not the schema.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class UsageEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One product usage event (spec §6 observability, §9 cost and usage)."""

    __tablename__ = "usage_events"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(nullable=False, default=1)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
