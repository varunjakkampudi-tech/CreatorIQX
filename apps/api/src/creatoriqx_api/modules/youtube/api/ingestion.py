"""Trigger a channel's data sync as a background job (spec §6 Workflows).

  POST /youtube/channels/{channel_id}/sync   enqueue a refresh of the channel's own data

Ingestion itself runs on the worker (``jobs.infrastructure.tasks.youtube_ingest_channel``),
never inline in the request, since it makes several YouTube API calls and
must be retry-safe under Celery's at-least-once delivery.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.jobs.domain.ports import JobRequest, TaskQueue
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/youtube", tags=["youtube"])

INGEST_CHANNEL_JOB = "youtube.ingest_channel"


def get_task_queue(request: Request) -> TaskQueue:
    queue: TaskQueue = request.app.state.task_queue
    return queue


TaskQueueDep = Annotated[TaskQueue, Depends(get_task_queue)]
EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]


class SyncTriggeredOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str


@router.post(
    "/channels/{channel_id}/sync",
    response_model=SyncTriggeredOut,
    status_code=202,
    summary="Refresh a channel's data from YouTube",
)
async def trigger_sync(
    channel_id: uuid.UUID,
    session: CsrfSessionDep,
    _access: EditorAccessDep,
    queue: TaskQueueDep,
) -> SyncTriggeredOut:
    handle = queue.enqueue(
        JobRequest(
            # CeleryTaskQueue.enqueue only forwards `payload` and
            # `correlation_id` as task kwargs (it does not pass
            # `workspace_id` through to the worker), so the workspace id
            # the task needs to scope its work must travel inside the
            # payload too, not only in this JobRequest field.
            name=INGEST_CHANNEL_JOB,
            payload={"channel_id": str(channel_id), "workspace_id": str(session.workspace_id)},
            workspace_id=session.workspace_id,
        )
    )
    return SyncTriggeredOut(job_id=handle.job_id)
