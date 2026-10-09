"""First-login bootstrap use case (P0-053).

Called once per successful Google login. It normalises the input, chooses the
ids, and delegates the transactional work to the store. Repeat logins are
idempotent: they return the same ids and create nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from creatoriqx_api.modules.workspaces.application.ports import (
    BootstrapCommand,
    PersonalWorkspaceStore,
)
from creatoriqx_api.modules.workspaces.domain.bootstrap import (
    BootstrapResult,
    personal_workspace_name,
)
from creatoriqx_api.platform.ids import new_id


class WorkspaceBootstrapService:
    """Ensures a user, a personal workspace and an owner membership exist."""

    def __init__(
        self,
        store: PersonalWorkspaceStore,
        id_factory: Callable[[], uuid.UUID] = new_id,
    ) -> None:
        self._store = store
        self._new_id = id_factory

    async def ensure_personal_workspace(
        self,
        *,
        subject: str,
        email: str,
        correlation_id: str | None = None,
    ) -> BootstrapResult:
        """Resolve (and if needed create) the personal workspace for a verified login."""
        clean_subject = subject.strip()
        clean_email = email.strip().lower()
        if not clean_subject:
            raise ValueError("subject must not be empty")
        if not clean_email:
            raise ValueError("email must not be empty")
        command = BootstrapCommand(
            subject=clean_subject,
            email=clean_email,
            user_id=self._new_id(),
            workspace_id=self._new_id(),
            membership_id=self._new_id(),
            workspace_name=personal_workspace_name(clean_email),
            correlation_id=correlation_id,
        )
        return await self._store.ensure(command)
