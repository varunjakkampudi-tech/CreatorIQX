"""Identity ORM tables: users (global), workspaces, memberships (spec §7).

``users`` is global (no workspace_id); a ``membership`` links a user to a
workspace with one role, unique per (user, workspace).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.platform.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person who can sign in. Global; not scoped to a workspace."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, default=None)
    display_name: Mapped[str | None] = mapped_column(String(255), default=None)


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant. All tenant data references its id as ``workspace_id``."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links a user to a workspace with exactly one role."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role", values_callable=lambda enum: [m.value for m in enum]),
        nullable=False,
    )
