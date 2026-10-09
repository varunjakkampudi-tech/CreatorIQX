"""Workspace authorization use case (P0-054, spec §10).

Every request that touches tenant data passes through here. The check is made
in the application layer, and PostgreSQL row-level security enforces the same
boundary underneath (ADR 0002), so a mistake in one layer is caught by the other.
"""

from __future__ import annotations

import uuid

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.application.ports import WorkspaceAccessStore
from creatoriqx_api.modules.workspaces.domain.access import (
    InsufficientRoleError,
    WorkspaceAccess,
)


class WorkspaceAccessService:
    """Answers "may this user act in this workspace, at this level?"."""

    def __init__(self, store: WorkspaceAccessStore) -> None:
        self._store = store

    async def authorize(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        required: Role,
    ) -> WorkspaceAccess:
        """Return the caller's access, or raise ``InsufficientRoleError``.

        Raised both when there is no membership and when the role is too low:
        the caller learns only that they may not act here.
        """
        access = await self._store.access(workspace_id=workspace_id, user_id=user_id)
        if access is None or not access.satisfies(required):
            raise InsufficientRoleError(f"This action needs the {required.value} role")
        return access
