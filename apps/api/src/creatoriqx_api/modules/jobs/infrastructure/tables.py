"""Outbox and idempotency ORM tables (spec §6). Owning bounded context: jobs.

``outbox_events`` carries no ``workspace_id``: the relay worker (P0-061) reads
unpublished rows across every tenant with ``FOR UPDATE SKIP LOCKED``, so it is
a platform table outside RLS, same as ``jobs`` and ``ai_tasks`` will be.

``idempotency_keys`` *is* tenant-scoped and forced-RLS. A dedupe key from one
workspace must never match or reveal a cached response belonging to another;
the ``(workspace_id, key)`` pair is the real uniqueness boundary, not the key
alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class OutboxEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A domain event awaiting relay (spec §6 event-driven, outbox pattern)."""

    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class IdempotencyKey(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A cached response for one ``Idempotency-Key`` header, scoped to a workspace."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(default=None)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
