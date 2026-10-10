"""Tests for ``PlannerService`` and ``VideoLifecycleService`` (spec §3, feature 4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from creatoriqx_api.modules.planning.application.planner_service import (
    PlannerService,
)
from creatoriqx_api.modules.planning.application.ports import NewPlan, NewVideo
from creatoriqx_api.modules.planning.application.video_lifecycle_service import (
    VideoLifecycleService,
)
from creatoriqx_api.modules.planning.domain.errors import (
    InvalidTransitionError,
    PlanAlreadyPromotedError,
    PlanNotFoundError,
    VideoNotFoundError,
)
from creatoriqx_api.modules.planning.domain.plan import Plan
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus

_WORKSPACE = uuid.uuid4()
_ACTOR = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class FakePlanStore:
    plans: dict[uuid.UUID, Plan] = field(default_factory=dict)

    async def create(self, plan: NewPlan) -> Plan:
        now = _now()
        record = Plan(
            id=uuid.uuid4(),
            workspace_id=plan.workspace_id,
            title=plan.title,
            notes=plan.notes,
            series=plan.series,
            scheduled_date=plan.scheduled_date,
            promoted_video_id=None,
            created_at=now,
            updated_at=now,
        )
        self.plans[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> Plan | None:
        plan = self.plans.get(plan_id)
        if plan is None or plan.workspace_id != workspace_id:
            return None
        return plan

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[Plan]:
        return [p for p in self.plans.values() if p.workspace_id == workspace_id]

    async def mark_promoted(
        self, *, workspace_id: uuid.UUID, plan_id: uuid.UUID, video_id: uuid.UUID
    ) -> Plan:
        plan = self.plans[plan_id]
        updated = Plan(
            id=plan.id,
            workspace_id=plan.workspace_id,
            title=plan.title,
            notes=plan.notes,
            series=plan.series,
            scheduled_date=plan.scheduled_date,
            promoted_video_id=video_id,
            created_at=plan.created_at,
            updated_at=_now(),
        )
        self.plans[plan_id] = updated
        return updated


@dataclass
class FakeVideoStore:
    videos: dict[uuid.UUID, Video] = field(default_factory=dict)

    async def create(
        self, video: NewVideo, *, actor_user_id: uuid.UUID, correlation_id: str | None
    ) -> Video:
        now = _now()
        record = Video(
            id=uuid.uuid4(),
            workspace_id=video.workspace_id,
            channel_id=video.channel_id,
            plan_id=video.plan_id,
            title=video.title,
            status=video.status,
            created_at=now,
            updated_at=now,
        )
        self.videos[record.id] = record
        return record

    async def get(self, *, workspace_id: uuid.UUID, video_id: uuid.UUID) -> Video | None:
        video = self.videos.get(video_id)
        if video is None or video.workspace_id != workspace_id:
            return None
        return video

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[Video]:
        return [v for v in self.videos.values() if v.workspace_id == workspace_id]

    async def update_status(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        status: VideoStatus,
        actor_user_id: uuid.UUID,
        correlation_id: str | None,
    ) -> Video:
        video = self.videos[video_id]
        updated = Video(
            id=video.id,
            workspace_id=video.workspace_id,
            channel_id=video.channel_id,
            plan_id=video.plan_id,
            title=video.title,
            status=status,
            created_at=video.created_at,
            updated_at=_now(),
        )
        self.videos[video_id] = updated
        return updated


class TestPlannerService:
    async def test_create_plan_persists_it(self) -> None:
        service = PlannerService(FakePlanStore(), FakeVideoStore())
        plan = await service.create_plan(workspace_id=_WORKSPACE, title="A video idea")
        assert plan.title == "A video idea"
        assert plan.promoted_video_id is None

    async def test_promote_creates_a_planned_video_and_links_it(self) -> None:
        plan_store = FakePlanStore()
        video_store = FakeVideoStore()
        service = PlannerService(plan_store, video_store)
        plan = await service.create_plan(workspace_id=_WORKSPACE, title="A video idea")

        video = await service.promote_to_video(
            workspace_id=_WORKSPACE, plan_id=plan.id, actor_user_id=_ACTOR
        )

        assert video.status is VideoStatus.PLANNED
        assert video.plan_id == plan.id
        assert video.title == plan.title
        promoted_plan = await plan_store.get(workspace_id=_WORKSPACE, plan_id=plan.id)
        assert promoted_plan is not None
        assert promoted_plan.promoted_video_id == video.id

    async def test_promote_missing_plan_raises(self) -> None:
        service = PlannerService(FakePlanStore(), FakeVideoStore())
        with pytest.raises(PlanNotFoundError):
            await service.promote_to_video(
                workspace_id=_WORKSPACE, plan_id=uuid.uuid4(), actor_user_id=_ACTOR
            )

    async def test_promote_twice_raises(self) -> None:
        plan_store = FakePlanStore()
        service = PlannerService(plan_store, FakeVideoStore())
        plan = await service.create_plan(workspace_id=_WORKSPACE, title="A video idea")
        await service.promote_to_video(
            workspace_id=_WORKSPACE, plan_id=plan.id, actor_user_id=_ACTOR
        )

        with pytest.raises(PlanAlreadyPromotedError):
            await service.promote_to_video(
                workspace_id=_WORKSPACE, plan_id=plan.id, actor_user_id=_ACTOR
            )

    async def test_board_returns_plans_and_videos_for_the_workspace_only(self) -> None:
        plan_store = FakePlanStore()
        video_store = FakeVideoStore()
        service = PlannerService(plan_store, video_store)
        await service.create_plan(workspace_id=_WORKSPACE, title="Mine")
        await service.create_plan(workspace_id=uuid.uuid4(), title="Someone else's")

        board = await service.board(workspace_id=_WORKSPACE)

        assert len(board.plans) == 1
        assert board.plans[0].title == "Mine"
        assert board.videos == []


class TestVideoLifecycleService:
    async def test_transition_moves_a_video_forward(self) -> None:
        video_store = FakeVideoStore()
        video = await video_store.create(
            NewVideo(
                workspace_id=_WORKSPACE,
                channel_id=None,
                plan_id=None,
                title="A video",
                status=VideoStatus.IDEA,
            ),
            actor_user_id=_ACTOR,
            correlation_id=None,
        )
        service = VideoLifecycleService(video_store)

        updated = await service.transition(
            workspace_id=_WORKSPACE,
            video_id=video.id,
            to_status=VideoStatus.PLANNED,
            actor_user_id=_ACTOR,
        )

        assert updated.status is VideoStatus.PLANNED

    async def test_disallowed_transition_raises_and_does_not_persist(self) -> None:
        video_store = FakeVideoStore()
        video = await video_store.create(
            NewVideo(
                workspace_id=_WORKSPACE,
                channel_id=None,
                plan_id=None,
                title="A video",
                status=VideoStatus.IDEA,
            ),
            actor_user_id=_ACTOR,
            correlation_id=None,
        )
        service = VideoLifecycleService(video_store)

        with pytest.raises(InvalidTransitionError):
            await service.transition(
                workspace_id=_WORKSPACE,
                video_id=video.id,
                to_status=VideoStatus.PUBLISHED,
                actor_user_id=_ACTOR,
            )

        unchanged = await video_store.get(workspace_id=_WORKSPACE, video_id=video.id)
        assert unchanged is not None
        assert unchanged.status is VideoStatus.IDEA

    async def test_transition_missing_video_raises(self) -> None:
        service = VideoLifecycleService(FakeVideoStore())
        with pytest.raises(VideoNotFoundError):
            await service.transition(
                workspace_id=_WORKSPACE,
                video_id=uuid.uuid4(),
                to_status=VideoStatus.PLANNED,
                actor_user_id=_ACTOR,
            )

    async def test_list_board_scopes_to_workspace(self) -> None:
        video_store = FakeVideoStore()
        await video_store.create(
            NewVideo(
                workspace_id=_WORKSPACE,
                channel_id=None,
                plan_id=None,
                title="Mine",
                status=VideoStatus.IDEA,
            ),
            actor_user_id=_ACTOR,
            correlation_id=None,
        )
        await video_store.create(
            NewVideo(
                workspace_id=uuid.uuid4(),
                channel_id=None,
                plan_id=None,
                title="Someone else's",
                status=VideoStatus.IDEA,
            ),
            actor_user_id=_ACTOR,
            correlation_id=None,
        )
        service = VideoLifecycleService(video_store)

        board = await service.list_board(workspace_id=_WORKSPACE)

        assert [v.title for v in board] == ["Mine"]
