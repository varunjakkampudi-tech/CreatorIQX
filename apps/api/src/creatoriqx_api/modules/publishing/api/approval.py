"""Approval gate routes (spec feature 13, ADR 0006).

POST /videos/{video_id}/approve    freeze an immutable publish snapshot
GET  /videos/{video_id}/snapshot   the video's latest approved snapshot
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.publishing.application.approval_service import ApprovalService
from creatoriqx_api.modules.publishing.domain.errors import PublishSnapshotNotFoundError
from creatoriqx_api.modules.publishing.domain.snapshot import PublishSnapshot
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.platform.idempotency import require_idempotency_key

router = APIRouter(prefix="/videos/{video_id}", tags=["approval"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]
IdempotencyKeyDep = Annotated[str, Depends(require_idempotency_key)]


def get_approval_service(request: Request) -> ApprovalService:
    service: ApprovalService = request.app.state.approval_service
    return service


ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]


class ApproveIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    scheduled_at: datetime | None = None
    wants_scheduling: bool = False


class PublishSnapshotOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    video_id: uuid.UUID
    script_version_id: uuid.UUID
    metadata_version_id: uuid.UUID
    chapter_version_id: uuid.UUID | None
    thumbnail_variant_id: uuid.UUID | None
    disclosure_altered: bool
    disclosure_synthetic: bool
    scheduled_at: datetime | None
    approved_by: uuid.UUID
    approved_at: datetime


@router.post(
    "/approve",
    response_model=PublishSnapshotOut,
    status_code=201,
    summary="Approve the video: freeze an immutable publish snapshot",
)
async def approve_video(
    video_id: uuid.UUID,
    body: ApproveIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: ApprovalServiceDep,
    _idempotency_key: IdempotencyKeyDep,
) -> PublishSnapshotOut:
    snapshot = await service.approve(
        workspace_id=session.workspace_id,
        video_id=video_id,
        actor_user_id=session.user_id,
        scheduled_at=body.scheduled_at,
        wants_scheduling=body.wants_scheduling,
        correlation_id=None,
    )
    return _out(snapshot)


@router.get(
    "/snapshot",
    response_model=PublishSnapshotOut,
    summary="The video's latest approved publish snapshot",
)
async def get_snapshot(
    video_id: uuid.UUID, access: ViewerAccessDep, service: ApprovalServiceDep
) -> PublishSnapshotOut:
    snapshot = await service.get_latest_snapshot(
        workspace_id=access.workspace_id, video_id=video_id
    )
    if snapshot is None:
        raise PublishSnapshotNotFoundError()
    return _out(snapshot)


def _out(snapshot: PublishSnapshot) -> PublishSnapshotOut:
    return PublishSnapshotOut(
        id=snapshot.id,
        video_id=snapshot.video_id,
        script_version_id=snapshot.script_version_id,
        metadata_version_id=snapshot.metadata_version_id,
        chapter_version_id=snapshot.chapter_version_id,
        thumbnail_variant_id=snapshot.thumbnail_variant_id,
        disclosure_altered=snapshot.disclosure_altered,
        disclosure_synthetic=snapshot.disclosure_synthetic,
        scheduled_at=snapshot.scheduled_at,
        approved_by=snapshot.approved_by,
        approved_at=snapshot.approved_at,
    )
