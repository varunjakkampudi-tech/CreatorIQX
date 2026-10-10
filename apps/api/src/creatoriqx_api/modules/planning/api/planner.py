"""Planner routes (spec feature 4).

POST /planner/plans              create a backlog/calendar entry
GET  /planner/plans              list this workspace's plans
POST /planner/plans/{id}/promote turn a plan into a Video (one click)
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from creatoriqx_api.modules.identity.api.dependencies import CsrfSessionDep
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.planning.application.planner_service import PlannerService
from creatoriqx_api.modules.planning.domain.plan import Plan
from creatoriqx_api.modules.workspaces.api.dependencies import require_role
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess

router = APIRouter(prefix="/planner", tags=["planner"])

EditorAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.EDITOR))]
ViewerAccessDep = Annotated[WorkspaceAccess, Depends(require_role(Role.VIEWER))]


def get_planner_service(request: Request) -> PlannerService:
    service: PlannerService = request.app.state.planner_service
    return service


PlannerServiceDep = Annotated[PlannerService, Depends(get_planner_service)]


class CreatePlanIn(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    notes: str = ""
    series: str | None = None
    scheduled_date: date | None = None


class PlanOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    title: str
    notes: str
    series: str | None
    scheduled_date: date | None
    promoted_video_id: uuid.UUID | None


class VideoOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    channel_id: uuid.UUID | None
    plan_id: uuid.UUID | None
    title: str
    status: str


@router.post("/plans", response_model=PlanOut, status_code=201, summary="Add a backlog idea")
async def create_plan(
    body: CreatePlanIn,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: PlannerServiceDep,
) -> PlanOut:
    plan = await service.create_plan(
        workspace_id=session.workspace_id,
        title=body.title,
        notes=body.notes,
        series=body.series,
        scheduled_date=body.scheduled_date,
    )
    return _plan_out(plan)


@router.get("/plans", response_model=list[PlanOut], summary="The backlog/calendar")
async def list_plans(access: ViewerAccessDep, service: PlannerServiceDep) -> list[PlanOut]:
    board = await service.board(workspace_id=access.workspace_id)
    return [_plan_out(plan) for plan in board.plans]


@router.post(
    "/plans/{plan_id}/promote",
    response_model=VideoOut,
    status_code=201,
    summary="Turn a plan into a Video",
)
async def promote_plan(
    plan_id: uuid.UUID,
    _access: EditorAccessDep,
    session: CsrfSessionDep,
    service: PlannerServiceDep,
) -> VideoOut:
    video = await service.promote_to_video(
        workspace_id=session.workspace_id,
        plan_id=plan_id,
        actor_user_id=session.user_id,
        correlation_id=None,
    )
    return VideoOut(
        id=video.id,
        channel_id=video.channel_id,
        plan_id=video.plan_id,
        title=video.title,
        status=video.status.value,
    )


def _plan_out(plan: Plan) -> PlanOut:
    return PlanOut(
        id=plan.id,
        title=plan.title,
        notes=plan.notes,
        series=plan.series,
        scheduled_date=plan.scheduled_date,
        promoted_video_id=plan.promoted_video_id,
    )
