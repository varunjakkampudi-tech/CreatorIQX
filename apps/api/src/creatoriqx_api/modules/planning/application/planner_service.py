"""The planner use case: backlog/calendar entries, and promoting one to a video.

Spec feature 4 acceptance: "Plans persist and can become Video records in
one click." Promotion creates the video at ``planned`` - the plan has
already done the work ``idea`` describes, so skipping straight to
``planned`` matches the lifecycle's own semantics rather than immediately
re-transitioning.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from creatoriqx_api.modules.planning.application.ports import (
    NewPlan,
    NewVideo,
    PlanStore,
    VideoStore,
)
from creatoriqx_api.modules.planning.domain.errors import (
    PlanAlreadyPromotedError,
    PlanNotFoundError,
)
from creatoriqx_api.modules.planning.domain.plan import Plan
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus


@dataclass(frozen=True, slots=True)
class PlannerBoard:
    """Everything the Planner screen needs in one call."""

    plans: list[Plan]
    videos: list[Video]


class PlannerService:
    """Create and promote backlog/calendar entries."""

    def __init__(self, plan_store: PlanStore, video_store: VideoStore) -> None:
        self._plans = plan_store
        self._videos = video_store

    async def create_plan(
        self,
        *,
        workspace_id: uuid.UUID,
        title: str,
        notes: str = "",
        series: str | None = None,
        scheduled_date: date | None = None,
    ) -> Plan:
        return await self._plans.create(
            NewPlan(
                workspace_id=workspace_id,
                title=title,
                notes=notes,
                series=series,
                scheduled_date=scheduled_date,
            )
        )

    async def board(self, *, workspace_id: uuid.UUID) -> PlannerBoard:
        """Plans and videos together, for the Planner/Video Board screens."""
        plans = await self._plans.list_for_workspace(workspace_id=workspace_id)
        videos = await self._videos.list_for_workspace(workspace_id=workspace_id)
        return PlannerBoard(plans=plans, videos=videos)

    async def promote_to_video(
        self,
        *,
        workspace_id: uuid.UUID,
        plan_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        correlation_id: str | None = None,
    ) -> Video:
        plan = await self._plans.get(workspace_id=workspace_id, plan_id=plan_id)
        if plan is None:
            raise PlanNotFoundError()
        if plan.promoted_video_id is not None:
            raise PlanAlreadyPromotedError()

        video = await self._videos.create(
            NewVideo(
                workspace_id=workspace_id,
                channel_id=None,
                plan_id=plan_id,
                title=plan.title,
                status=VideoStatus.PLANNED,
            ),
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        await self._plans.mark_promoted(
            workspace_id=workspace_id, plan_id=plan_id, video_id=video.id
        )
        return video
