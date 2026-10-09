"""Identity ORM tables. Owning bounded context: identity.

``users`` is global (no workspace_id, no RLS). Workspaces and memberships moved
to the ``workspaces`` module in P0-053 (ADR 0011).
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.platform.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person who can sign in. Global; not scoped to a workspace."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, default=None)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)
