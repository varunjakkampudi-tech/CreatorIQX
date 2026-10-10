"""YouTube connection routes (spec §3, §10).

  POST /youtube/connect                         start a connect attempt, get the Google URL
  GET  /youtube/connect/callback                Google's redirect back; completes the connection
  GET  /youtube/channels                        channels connected in this workspace
  POST /youtube/channels/{channel_id}/disconnect revoke a connection

The callback is a browser navigation, not an XHR, so it carries no CSRF
header; the one-time ``state`` token (bound to the workspace that started the
flow, stored server-side with a short TTL) is the CSRF defense here, same
as the login flow's own state parameter.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep, SessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.modules.youtube.application.connection_service import (
    ChannelConnectionService,
)
from creatoriqx_api.modules.youtube.domain.connection import ConnectedChannel, ConnectionStatus

router = APIRouter(prefix="/youtube", tags=["youtube"])


def get_connection_service(request: Request) -> ChannelConnectionService:
    service: ChannelConnectionService = request.app.state.youtube_connection_service
    return service


ConnectionServiceDep = Annotated[ChannelConnectionService, Depends(get_connection_service)]
EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]


class StartConnectIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    redirect_uri: str


class StartConnectOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    authorization_url: str


class ConnectedChannelOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    youtube_channel_id: str
    title: str
    thumbnail_url: str | None
    subscriber_count: int | None
    video_count: int | None
    last_synced_at: str | None
    connection_status: ConnectionStatus

    @classmethod
    def from_domain(cls, channel: ConnectedChannel) -> ConnectedChannelOut:
        return cls(
            id=channel.id,
            youtube_channel_id=channel.youtube_channel_id,
            title=channel.title,
            thumbnail_url=channel.thumbnail_url,
            subscriber_count=channel.subscriber_count,
            video_count=channel.video_count,
            last_synced_at=channel.last_synced_at.isoformat() if channel.last_synced_at else None,
            connection_status=channel.connection_status,
        )


@router.post("/connect", response_model=StartConnectOut, summary="Start a YouTube connection")
async def start_connect(
    body: StartConnectIn,
    session: CsrfSessionDep,
    _access: EditorAccessDep,
    service: ConnectionServiceDep,
) -> StartConnectOut:
    url = await service.start_connect(
        workspace_id=session.workspace_id, user_id=session.user_id, redirect_uri=body.redirect_uri
    )
    return StartConnectOut(authorization_url=url)


@router.get(
    "/connect/callback",
    response_model=ConnectedChannelOut,
    summary="Complete a YouTube connection",
)
async def complete_connect(
    response: Response,
    state: str,
    code: str,
    session: SessionDep,
    service: ConnectionServiceDep,
) -> ConnectedChannelOut:
    response.headers["Cache-Control"] = "no-store"
    channel = await service.complete_connect(
        state=state, code=code, workspace_id=session.workspace_id, user_id=session.user_id
    )
    return ConnectedChannelOut.from_domain(channel)


@router.get("/channels", response_model=list[ConnectedChannelOut], summary="Connected channels")
async def list_channels(
    response: Response, session: SessionDep, service: ConnectionServiceDep
) -> list[ConnectedChannelOut]:
    response.headers["Cache-Control"] = "no-store"
    channels = await service.list_channels(session.workspace_id)
    return [ConnectedChannelOut.from_domain(channel) for channel in channels]


@router.post("/channels/{channel_id}/disconnect", status_code=204, summary="Disconnect a channel")
async def disconnect(
    channel_id: uuid.UUID,
    session: CsrfSessionDep,
    _access: EditorAccessDep,
    service: ConnectionServiceDep,
) -> None:
    await service.disconnect(workspace_id=session.workspace_id, channel_id=channel_id)
