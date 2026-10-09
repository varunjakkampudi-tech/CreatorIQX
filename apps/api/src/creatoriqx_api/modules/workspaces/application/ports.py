"""Ports for the workspaces module: first-login bootstrap and access checks.

Infrastructure implements them; the application never imports SQL.

The application generates every identifier before calling the store, so the
store never needs a privileged path to mint ids.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.modules.workspaces.domain.bootstrap import BootstrapResult


@dataclass(frozen=True, slots=True)
class BootstrapCommand:
    """Everything the store needs to bootstrap one login, with ids already chosen."""

    subject: str
    email: str
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    membership_id: uuid.UUID
    workspace_name: str
    correlation_id: str | None = None


class PersonalWorkspaceStore(Protocol):
    """Persists the first-login bootstrap atomically and idempotently per subject."""

    async def ensure(self, command: BootstrapCommand) -> BootstrapResult:
        """Create what is missing for ``command.subject`` and return the resolved ids."""


class WorkspaceAccessStore(Protocol):
    """Reads the caller's membership of one workspace (P0-054).

    One query answers both questions a request asks: does this user belong to
    this workspace, and what may they do in it.
    """

    async def access(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceAccess | None:
        """The caller's verified access, or None when they are not a member."""
