"""The signed-in user (P0-054).

  GET /me   who the caller is, and their role in the workspace they are acting in

Identity comes from the server-side session; the role comes from a verified
membership, so a user removed from the workspace is refused here too rather
than being shown a workspace they no longer belong to.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import SessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.api.dependencies import ViewerAccessDep

router = APIRouter(tags=["identity"])


class MeOut(BaseModel):
    """The caller's own identity and current workspace role."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    email: str
    workspace_id: uuid.UUID
    role: Role


@router.get("/me", response_model=MeOut, summary="The signed-in user")
async def read_me(response: Response, session: SessionDep, access: ViewerAccessDep) -> MeOut:
    response.headers["Cache-Control"] = "no-store"
    return MeOut(
        user_id=session.user_id,
        email=session.email,
        workspace_id=access.workspace_id,
        role=access.role,
    )
