"""Workspace bootstrap rules (P0-053, ADR 0011).

First login creates a user, a personal workspace and an owner membership.
The rules here are pure: no SQL, no HTTP, no clock.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from creatoriqx_api.platform.errors import DomainError

NO_WORKSPACE = uuid.UUID(int=0)
"""Tenant context used while no workspace is in scope (user creation, login lookup).

No real identifier equals it: UUIDv7 values from ``platform.ids`` always carry a
non-zero timestamp. Row-level security then sees no workspace rows, so only
rows that are visible without a workspace (for example the caller's own
memberships) can be read.
"""

_MAX_NAME_LENGTH = 255
_FALLBACK_NAME = "Personal workspace"


class IdentityConflictError(DomainError):
    """The email is already bound to a different Google subject, or a race lost the uniqueness check."""

    status = 409
    title = "Identity conflict"
    code = "identity-conflict"


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """What the first-login bootstrap resolved for one Google subject."""

    user_id: uuid.UUID
    workspace_id: uuid.UUID
    user_created: bool
    workspace_created: bool


def personal_workspace_name(email: str) -> str:
    """A readable default name such as ``Ada's workspace``, derived from the email local part."""
    local_part = email.split("@", 1)[0].strip()
    if not local_part:
        return _FALLBACK_NAME
    return f"{local_part}'s workspace"[:_MAX_NAME_LENGTH]
