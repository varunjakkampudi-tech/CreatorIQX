"""Script routes (spec feature 5).

POST /videos/{video_id}/scripts                  create a version
GET  /videos/{video_id}/scripts                   compare versions
POST /videos/{video_id}/scripts/{id}/restore      restore an old version
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.content.application.script_service import ScriptService
from creatoriqx_api.modules.content.domain.script import ScriptAuthor, ScriptVersion
from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/videos/{video_id}/scripts", tags=["scripts"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]


def get_script_service(request: Request) -> ScriptService:
    service: ScriptService = request.app.state.script_service
    return service


ScriptServiceDep = Annotated[ScriptService, Depends(get_script_service)]


class CreateScriptVersionIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant_label: str = "default"
    author: ScriptAuthor = ScriptAuthor.HUMAN
    hook: str = ""
    outline: str = ""
    body: str = ""


class ScriptVersionOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    variant_label: str
    author: str
    hook: str
    outline: str
    body: str
    parent_version_id: uuid.UUID | None
    is_current: bool


@router.post(
    "", response_model=ScriptVersionOut, status_code=201, summary="Create a script version"
)
async def create_script_version(
    video_id: uuid.UUID,
    body: CreateScriptVersionIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: ScriptServiceDep,
) -> ScriptVersionOut:
    version = await service.create_version(
        workspace_id=session.workspace_id,
        video_id=video_id,
        variant_label=body.variant_label,
        author=body.author,
        hook=body.hook,
        outline=body.outline,
        body=body.body,
    )
    return _out(version)


@router.get("", response_model=list[ScriptVersionOut], summary="Compare script versions")
async def list_script_versions(
    video_id: uuid.UUID, access: ViewerAccessDep, service: ScriptServiceDep
) -> list[ScriptVersionOut]:
    versions = await service.list_versions(workspace_id=access.workspace_id, video_id=video_id)
    return [_out(v) for v in versions]


@router.post(
    "/{version_id}/restore",
    response_model=ScriptVersionOut,
    status_code=201,
    summary="Restore an old script version",
)
async def restore_script_version(
    video_id: uuid.UUID,
    version_id: uuid.UUID,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: ScriptServiceDep,
) -> ScriptVersionOut:
    version = await service.restore_version(
        workspace_id=session.workspace_id, video_id=video_id, version_id=version_id
    )
    return _out(version)


def _out(version: ScriptVersion) -> ScriptVersionOut:
    return ScriptVersionOut(
        id=version.id,
        variant_label=version.variant_label,
        author=version.author.value,
        hook=version.hook,
        outline=version.outline,
        body=version.body,
        parent_version_id=version.parent_version_id,
        is_current=version.is_current,
    )
