"""Chapter routes (spec feature 10).

POST /videos/{video_id}/chapters                   create a version manually
POST /videos/{video_id}/chapters/generate           draft from a transcript version
GET  /videos/{video_id}/chapters                    compare versions
POST /videos/{video_id}/chapters/{id}/restore       restore an old version
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.content.application.chapter_service import ChapterService
from creatoriqx_api.modules.content.domain.chapters import Chapter, ChapterVersion
from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/videos/{video_id}/chapters", tags=["chapters"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]


def get_chapter_service(request: Request) -> ChapterService:
    service: ChapterService = request.app.state.chapter_service
    return service


ChapterServiceDep = Annotated[ChapterService, Depends(get_chapter_service)]


class ChapterIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_seconds: int
    title: str


class CreateChapterVersionIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    transcript_id: uuid.UUID
    chapters: list[ChapterIn]


class GenerateChaptersIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    transcript_id: uuid.UUID


class ChapterVersionOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    transcript_id: uuid.UUID
    chapters: list[ChapterIn]
    parent_version_id: uuid.UUID | None
    is_current: bool


@router.post(
    "", response_model=ChapterVersionOut, status_code=201, summary="Create a chapter version"
)
async def create_chapter_version(
    video_id: uuid.UUID,
    body: CreateChapterVersionIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: ChapterServiceDep,
) -> ChapterVersionOut:
    chapters = tuple(Chapter(start_seconds=c.start_seconds, title=c.title) for c in body.chapters)
    version = await service.create_version(
        workspace_id=session.workspace_id,
        video_id=video_id,
        transcript_id=body.transcript_id,
        chapters=chapters,
    )
    return _out(version)


@router.post(
    "/generate",
    response_model=ChapterVersionOut,
    status_code=201,
    summary="Draft chapters from a transcript",
)
async def generate_chapter_version(
    video_id: uuid.UUID,
    body: GenerateChaptersIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: ChapterServiceDep,
) -> ChapterVersionOut:
    version = await service.generate_from_transcript(
        workspace_id=session.workspace_id,
        video_id=video_id,
        transcript_id=body.transcript_id,
    )
    return _out(version)


@router.get("", response_model=list[ChapterVersionOut], summary="Compare chapter versions")
async def list_chapter_versions(
    video_id: uuid.UUID, access: ViewerAccessDep, service: ChapterServiceDep
) -> list[ChapterVersionOut]:
    versions = await service.list_versions(workspace_id=access.workspace_id, video_id=video_id)
    return [_out(v) for v in versions]


@router.post(
    "/{version_id}/restore",
    response_model=ChapterVersionOut,
    status_code=201,
    summary="Restore an old chapter version",
)
async def restore_chapter_version(
    video_id: uuid.UUID,
    version_id: uuid.UUID,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: ChapterServiceDep,
) -> ChapterVersionOut:
    version = await service.restore_version(
        workspace_id=session.workspace_id, video_id=video_id, version_id=version_id
    )
    return _out(version)


def _out(version: ChapterVersion) -> ChapterVersionOut:
    return ChapterVersionOut(
        id=version.id,
        transcript_id=version.transcript_id,
        chapters=[
            ChapterIn(start_seconds=c.start_seconds, title=c.title) for c in version.chapters
        ],
        parent_version_id=version.parent_version_id,
        is_current=version.is_current,
    )
