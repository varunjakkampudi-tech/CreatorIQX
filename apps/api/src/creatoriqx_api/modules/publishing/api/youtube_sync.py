"""YouTube link and sync routes (spec §3, feature 14, ADR 0007).

  POST /videos/{video_id}/youtube/link            link to a real YouTube video
  GET  /videos/{video_id}/youtube/status          the link's current sync state
  POST /videos/{video_id}/youtube/sync            apply the latest approved snapshot
  GET  /videos/{video_id}/youtube/drift           re-check for remote drift
  POST /videos/{video_id}/youtube/drift/resolve   resolve flagged drift (explicit mode)

Wired only when ``settings.youtube_oauth_client_id`` is set, same gate as
every other YouTube route (``youtube/api/connect.py``, ``youtube/api/
ingestion.py``) - these routes need a real channel connection and write
client, which ``_wire_youtube`` builds from credentials that do not exist
in every deployment (spec §3, §10). A deployment without YouTube configured
runs without any of them, QA/approval included elsewhere in this phase are
unconditional precisely because they need none of this.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.publishing.application.youtube_sync_service import YoutubeSyncService
from creatoriqx_api.modules.publishing.domain.drift import DriftResolutionMode
from creatoriqx_api.modules.publishing.domain.errors import VideoLinkNotFoundError
from creatoriqx_api.modules.publishing.domain.sync_operation import SyncOperation
from creatoriqx_api.modules.publishing.domain.video_link import YoutubeVideoLink
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.platform.idempotency import require_idempotency_key

router = APIRouter(prefix="/videos/{video_id}/youtube", tags=["youtube-sync"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]
IdempotencyKeyDep = Annotated[str, Depends(require_idempotency_key)]


def get_youtube_sync_service(request: Request) -> YoutubeSyncService:
    service: YoutubeSyncService = request.app.state.youtube_sync_service
    return service


YoutubeSyncServiceDep = Annotated[YoutubeSyncService, Depends(get_youtube_sync_service)]


class LinkVideoIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    channel_id: uuid.UUID
    youtube_video_id: str


class YoutubeVideoLinkOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    video_id: uuid.UUID
    channel_id: uuid.UUID
    youtube_video_id: str
    sync_state: str
    last_synced_at: str | None
    last_remote_etag: str | None


class SyncOperationOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    field_group: str
    status: str
    error_details: str | None
    quota_cost: int
    remote_etag: str | None
    readback_verified: bool


class DriftOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    video_id: uuid.UUID
    drift_detected: bool


class ResolveDriftIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: DriftResolutionMode


class DriftResolvedOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    video_id: uuid.UUID
    mode: DriftResolutionMode


@router.post(
    "/link",
    response_model=YoutubeVideoLinkOut,
    status_code=201,
    summary="Link this video to a real YouTube video",
)
async def link_video(
    video_id: uuid.UUID,
    body: LinkVideoIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: YoutubeSyncServiceDep,
    _idempotency_key: IdempotencyKeyDep,
) -> YoutubeVideoLinkOut:
    link = await service.link_video(
        workspace_id=session.workspace_id,
        video_id=video_id,
        channel_id=body.channel_id,
        youtube_video_id=body.youtube_video_id,
    )
    return _link_out(link)


@router.get(
    "/status", response_model=YoutubeVideoLinkOut, summary="This video's current YouTube link"
)
async def get_status(
    video_id: uuid.UUID, access: ViewerAccessDep, service: YoutubeSyncServiceDep
) -> YoutubeVideoLinkOut:
    link = await service.get_link(workspace_id=access.workspace_id, video_id=video_id)
    if link is None:
        raise VideoLinkNotFoundError()
    return _link_out(link)


@router.post(
    "/sync",
    response_model=list[SyncOperationOut],
    summary="Apply the latest approved snapshot to the linked YouTube video",
)
async def sync_video(
    video_id: uuid.UUID,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: YoutubeSyncServiceDep,
    _idempotency_key: IdempotencyKeyDep,
) -> list[SyncOperationOut]:
    operations = await service.apply_snapshot(workspace_id=session.workspace_id, video_id=video_id)
    return [_operation_out(operation) for operation in operations]


@router.get("/drift", response_model=DriftOut, summary="Re-check the linked video for remote drift")
async def get_drift(
    video_id: uuid.UUID, access: ViewerAccessDep, service: YoutubeSyncServiceDep
) -> DriftOut:
    drifted = await service.detect_drift(workspace_id=access.workspace_id, video_id=video_id)
    return DriftOut(video_id=video_id, drift_detected=drifted)


@router.post(
    "/drift/resolve",
    response_model=DriftResolvedOut,
    summary="Resolve flagged drift with one explicit mode",
)
async def resolve_drift(
    video_id: uuid.UUID,
    body: ResolveDriftIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: YoutubeSyncServiceDep,
    _idempotency_key: IdempotencyKeyDep,
) -> DriftResolvedOut:
    await service.resolve_drift(
        workspace_id=session.workspace_id, video_id=video_id, mode=body.mode
    )
    return DriftResolvedOut(video_id=video_id, mode=body.mode)


def _link_out(link: YoutubeVideoLink) -> YoutubeVideoLinkOut:
    return YoutubeVideoLinkOut(
        id=link.id,
        video_id=link.video_id,
        channel_id=link.channel_id,
        youtube_video_id=link.youtube_video_id,
        sync_state=link.sync_state.value,
        last_synced_at=link.last_synced_at.isoformat() if link.last_synced_at else None,
        last_remote_etag=link.last_remote_etag,
    )


def _operation_out(operation: SyncOperation) -> SyncOperationOut:
    return SyncOperationOut(
        id=operation.id,
        field_group=operation.field_group.value,
        status=operation.status.value,
        error_details=operation.error_details,
        quota_cost=operation.quota_cost,
        remote_etag=operation.remote_etag,
        readback_verified=operation.readback_verified,
    )
