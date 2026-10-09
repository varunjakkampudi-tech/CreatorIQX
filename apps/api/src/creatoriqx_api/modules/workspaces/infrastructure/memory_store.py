"""In-memory bootstrap store for unit tests only. Never wired into the running app.

It mirrors the SQL store's contract: idempotent per subject, one workspace per
new user, a refusal when an email belongs to another subject. It also keeps the
audit actions and outbox event types it would have written, so tests can assert
on them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from creatoriqx_api.modules.workspaces.application.ports import BootstrapCommand
from creatoriqx_api.modules.workspaces.domain.bootstrap import (
    BootstrapResult,
    IdentityConflictError,
)


@dataclass
class _UserRow:
    user_id: uuid.UUID
    email: str
    workspace_id: uuid.UUID


@dataclass
class InMemoryPersonalWorkspaceStore:
    """Test double for ``PersonalWorkspaceStore``."""

    users: dict[str, _UserRow] = field(default_factory=dict)
    audit_actions: list[str] = field(default_factory=list)
    outbox_events: list[str] = field(default_factory=list)

    async def ensure(self, command: BootstrapCommand) -> BootstrapResult:
        existing = self.users.get(command.subject)
        if existing is not None:
            self.audit_actions.append("auth.login_succeeded")
            return BootstrapResult(
                user_id=existing.user_id,
                workspace_id=existing.workspace_id,
                user_created=False,
                workspace_created=False,
            )
        if any(row.email == command.email for row in self.users.values()):
            raise IdentityConflictError("This email is already linked to another sign-in")

        self.users[command.subject] = _UserRow(
            user_id=command.user_id,
            email=command.email,
            workspace_id=command.workspace_id,
        )
        self.audit_actions.extend(["user.created", "workspace.created", "auth.login_succeeded"])
        self.outbox_events.append("workspace.created")
        return BootstrapResult(
            user_id=command.user_id,
            workspace_id=command.workspace_id,
            user_created=True,
            workspace_created=True,
        )
