"""SQLAlchemy adapter for workspace access checks (P0-054).

One query under the caller's own tenant context (ADR 0002): it joins the
workspace to the caller's membership, so a user who is not a member gets no
row even though row-level security would have let them read the workspace's
membership list. The application check and RLS are independent layers.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.modules.workspaces.infrastructure.tables import Membership, Workspace
from creatoriqx_api.platform.database import session_scope, set_tenant_context


class SqlWorkspaceAccessStore:
    """Reads one membership as the runtime role under forced RLS."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def access(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceAccess | None:
        async with session_scope(self._factory) as session:
            await set_tenant_context(session, workspace_id=workspace_id, user_id=user_id)
            result = await session.execute(
                select(Workspace.name, Membership.role)
                .join(Membership, Membership.workspace_id == Workspace.id)
                .where(Workspace.id == workspace_id, Membership.user_id == user_id)
            )
            row = result.first()
        if row is None:
            return None
        name, role = row
        return WorkspaceAccess(workspace_id=workspace_id, name=str(name), role=Role(role))
