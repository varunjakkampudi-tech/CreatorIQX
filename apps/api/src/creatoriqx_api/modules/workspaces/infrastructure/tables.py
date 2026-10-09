"""Workspace and membership ORM tables (spec §7). Owning bounded context: workspaces.

``workspaces`` is a tenant table in the sense that its own id is the tenant key:
it carries no ``workspace_id`` column, so the RLS meta-test does not select it.
Its policies are created in migration 0005 and proven by the integration tests.
``memberships`` is a tenant table keyed by ``workspace_id`` (migration 0003).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.platform.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


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
