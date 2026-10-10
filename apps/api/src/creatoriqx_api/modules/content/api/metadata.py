"""Metadata/SEO routes (spec feature 9).

POST /videos/{video_id}/metadata                 create a version
GET  /videos/{video_id}/metadata                  compare versions
POST /videos/{video_id}/metadata/{id}/restore     restore an old version
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.content.application.metadata_service import MetadataService
from creatoriqx_api.modules.content.domain.metadata import MetadataVersion
from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/videos/{video_id}/metadata", tags=["metadata"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]


def get_metadata_service(request: Request) -> MetadataService:
    service: MetadataService = request.app.state.metadata_service
    return service


MetadataServiceDep = Annotated[MetadataService, Depends(get_metadata_service)]


class CreateMetadataVersionIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    description: str = ""
    tags: tuple[str, ...] = ()
    category: str | None = None
    disclosure_altered: bool = False
    disclosure_synthetic: bool = False
    rationale: str = ""


class MetadataVersionOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    title: str
    description: str
    tags: list[str]
    category: str | None
    disclosure_altered: bool
    disclosure_synthetic: bool
    rationale: str
    parent_version_id: uuid.UUID | None
    is_current: bool
    character_limit_warnings: list[str] = []


@router.post(
    "", response_model=MetadataVersionOut, status_code=201, summary="Create a metadata version"
)
async def create_metadata_version(
    video_id: uuid.UUID,
    body: CreateMetadataVersionIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: MetadataServiceDep,
) -> MetadataVersionOut:
    version, warnings = await service.create_version(
        workspace_id=session.workspace_id,
        video_id=video_id,
        title=body.title,
        description=body.description,
        tags=body.tags,
        category=body.category,
        disclosure_altered=body.disclosure_altered,
        disclosure_synthetic=body.disclosure_synthetic,
        rationale=body.rationale,
    )
    return _out(version, warnings)


@router.get("", response_model=list[MetadataVersionOut], summary="Compare metadata versions")
async def list_metadata_versions(
    video_id: uuid.UUID, access: ViewerAccessDep, service: MetadataServiceDep
) -> list[MetadataVersionOut]:
    versions = await service.list_versions(workspace_id=access.workspace_id, video_id=video_id)
    return [_out(v, []) for v in versions]


@router.post(
    "/{version_id}/restore",
    response_model=MetadataVersionOut,
    status_code=201,
    summary="Restore an old metadata version",
)
async def restore_metadata_version(
    video_id: uuid.UUID,
    version_id: uuid.UUID,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: MetadataServiceDep,
) -> MetadataVersionOut:
    version = await service.restore_version(
        workspace_id=session.workspace_id, video_id=video_id, version_id=version_id
    )
    return _out(version, [])


def _out(version: MetadataVersion, warnings: list[str]) -> MetadataVersionOut:
    return MetadataVersionOut(
        id=version.id,
        title=version.title,
        description=version.description,
        tags=list(version.tags),
        category=version.category,
        disclosure_altered=version.disclosure_altered,
        disclosure_synthetic=version.disclosure_synthetic,
        rationale=version.rationale,
        parent_version_id=version.parent_version_id,
        is_current=version.is_current,
        character_limit_warnings=warnings,
    )
