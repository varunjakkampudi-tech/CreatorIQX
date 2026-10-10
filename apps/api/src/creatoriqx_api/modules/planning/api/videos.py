"""Video Board routes (spec §3 state machine, §11 "Video Board (kanban of the
state machine)").

  GET  /videos                  the board: every video, with its current status
  POST /videos/{id}/transition   move a video to an allowed next status
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.planning.application.video_lifecycle_service import (
    VideoLifecycleService,
)
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/videos", tags=["videos"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]


def get_video_lifecycle_service(request: Request) -> VideoLifecycleService:
    service: VideoLifecycleService = request.app.state.video_lifecycle_service
    return service


VideoLifecycleServiceDep = Annotated[VideoLifecycleService, Depends(get_video_lifecycle_service)]


class VideoOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    channel_id: uuid.UUID | None
    plan_id: uuid.UUID | None
    title: str
    status: str


class TransitionIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    to_status: VideoStatus


@router.get("", response_model=list[VideoOut], summary="The video board")
async def list_videos(access: ViewerAccessDep, service: VideoLifecycleServiceDep) -> list[VideoOut]:
    videos = await service.list_board(workspace_id=access.workspace_id)
    return [_video_out(video) for video in videos]


@router.post(
    "/{video_id}/transition",
    response_model=VideoOut,
    summary="Move a video to an allowed next status",
)
async def transition_video(
    video_id: uuid.UUID,
    body: TransitionIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: VideoLifecycleServiceDep,
) -> VideoOut:
    video = await service.transition(
        workspace_id=session.workspace_id,
        video_id=video_id,
        to_status=body.to_status,
        actor_user_id=session.user_id,
        correlation_id=None,
    )
    return _video_out(video)


def _video_out(video: Video) -> VideoOut:
    return VideoOut(
        id=video.id,
        channel_id=video.channel_id,
        plan_id=video.plan_id,
        title=video.title,
        status=video.status.value,
    )
