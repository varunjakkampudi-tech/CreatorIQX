"""Workspace authorization rules (P0-054, spec §10 Authorization).

Pure rules: which role satisfies which requirement, and what a caller is
allowed to know about the workspace in their session context. No SQL, no HTTP.

Deny by default: a caller with no membership in the workspace their session
names is refused, exactly like a caller whose role is too low. The refusal
never distinguishes the two, so it cannot be used to discover which
workspaces exist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.platform.errors import DomainError

_RANK: dict[Role, int] = {Role.VIEWER: 1, Role.EDITOR: 2, Role.OWNER: 3}


class InsufficientRoleError(DomainError):
    """The caller is not a member of the workspace, or their role is too low."""

    status = 403
    title = "Not permitted in this workspace"
    code = "insufficient-role"


def role_satisfies(actual: Role, required: Role) -> bool:
    """True when ``actual`` is at least as privileged as ``required``.

    owner outranks editor, which outranks viewer.
    """
    return _RANK[actual] >= _RANK[required]


@dataclass(frozen=True, slots=True)
class WorkspaceAccess:
    """A verified membership: the workspace, its name, and the caller's role in it."""

    workspace_id: uuid.UUID
    name: str
    role: Role

    def satisfies(self, required: Role) -> bool:
        return role_satisfies(self.role, required)
