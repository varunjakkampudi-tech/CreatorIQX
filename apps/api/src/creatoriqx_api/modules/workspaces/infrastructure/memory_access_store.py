"""In-memory access store for unit tests only. Never wired into the running app."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess


@dataclass
class InMemoryWorkspaceAccessStore:
    """Test double for ``WorkspaceAccessStore``, keyed by (workspace, user)."""

    memberships: dict[tuple[uuid.UUID, uuid.UUID], WorkspaceAccess] = field(default_factory=dict)

    def grant(self, access: WorkspaceAccess, user_id: uuid.UUID) -> None:
        """Record a membership so ``access`` is returned for this pair."""
        self.memberships[(access.workspace_id, user_id)] = access

    async def access(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceAccess | None:
        return self.memberships.get((workspace_id, user_id))
