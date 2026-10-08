"""Audit log ORM table (spec §7, §10). Owning bounded context: audit.

The audit log is append-only (STRIDE T-T2): the runtime role is denied UPDATE
and DELETE and a trigger rejects them, so tampering cannot hide an action.
``workspace_id`` is nullable because some events (user creation at first login)
happen before any workspace exists; forced RLS still scopes the tenant rows.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only record of a sensitive action (who, what, when, correlation)."""

    __tablename__ = "audit_log"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100), default=None)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    correlation_id: Mapped[str | None] = mapped_column(String(100), default=None)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
