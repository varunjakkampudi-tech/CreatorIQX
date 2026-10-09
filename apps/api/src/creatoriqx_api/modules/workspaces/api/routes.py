"""Workspace routes (P0-054).

  GET /workspaces/current   the workspace the session is acting in, and the caller's role

Scoped by ``require_role``: the workspace comes from the session, never from a
parameter, so there is no identifier for a caller to tamper with.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.api.dependencies import ViewerAccessDep

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


class CurrentWorkspaceOut(BaseModel):
    """The session's workspace and what the caller may do in it."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    name: str
    role: Role


@router.get("/current", response_model=CurrentWorkspaceOut, summary="The current workspace")
async def read_current_workspace(
    response: Response, access: ViewerAccessDep
) -> CurrentWorkspaceOut:
    response.headers["Cache-Control"] = "no-store"
    return CurrentWorkspaceOut(id=access.workspace_id, name=access.name, role=access.role)
