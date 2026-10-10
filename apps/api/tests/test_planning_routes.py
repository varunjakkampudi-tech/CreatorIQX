"""HTTP behaviour of the planner and video-board routes (Phase 1B, spec §4 feature 4, §3).

Covers the full request path (route -> dependency -> service) through the app
factory, with in-memory doubles standing in for the session/access services
and ``FakePlanStore``/``FakeVideoStore`` (duplicated from
``test_planning_services.py`` rather than imported, since the test suite has
no precedent for importing fixtures across test modules) standing in for
Postgres - no real database needed, the same approach ``test_cross_tenant.py``
uses for the rest of the app's routes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.identity.api.dependencies import CSRF_HEADER
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.planning.application.planner_service import PlannerService
from creatoriqx_api.modules.planning.application.ports import NewPlan, NewVideo
from creatoriqx_api.modules.planning.application.video_lifecycle_service import (
    VideoLifecycleService,
)
from creatoriqx_api.modules.planning.domain.plan import Plan
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.modules.workspaces.infrastructure.memory_access_store import (
    InMemoryWorkspaceAccessStore,
)
from creatoriqx_api.settings import Settings


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


POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
SESSION_COOKIE = "__Host-creatoriqx_session"
WORKSPACE_ID = uuid.UUID(int=301)
USER_ID = uuid.UUID(int=401)
VIEWER_ID = uuid.UUID(int=402)


def _settings() -> Settings:
    return Settings(
        database_app_url=SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        redis_url=SecretStr("redis://localhost:1/0"),
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(_settings(), checks=[])
    store = InMemoryKeyValueStore()
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, POLICY)
    access = InMemoryWorkspaceAccessStore()
    access.grant(
        WorkspaceAccess(workspace_id=WORKSPACE_ID, name="workspace", role=Role.EDITOR), USER_ID
    )
    access.grant(
        WorkspaceAccess(workspace_id=WORKSPACE_ID, name="workspace", role=Role.VIEWER), VIEWER_ID
    )
    app.state.workspace_access_service = WorkspaceAccessService(access)
    # The real SqlPlanStore/SqlVideoStore need Postgres; these fakes exercise
    # the same ports the route dependencies resolve, same approach the rest
    # of the suite uses to test routes without a database.
    plan_store = FakePlanStore()
    video_store = FakeVideoStore()
    app.state.planner_service = PlannerService(plan_store, video_store)
    app.state.video_lifecycle_service = VideoLifecycleService(video_store)
    with TestClient(app, base_url="https://testserver") as built:
        yield built


async def _sign_in(client: TestClient, *, user_id: uuid.UUID) -> str:
    app: FastAPI = client.app  # type: ignore[assignment]
    service: SessionService = app.state.session_service
    session = await service.create(
        subject=str(user_id),
        email="creator@example.com",
        user_id=user_id,
        workspace_id=WORKSPACE_ID,
    )
    client.cookies.set(SESSION_COOKIE, session.id)
    return session.csrf_token


async def test_create_plan_then_list_it(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)

    created = client.post(
        "/api/v1/planner/plans",
        json={"title": "Ship the sequel", "notes": "needs b-roll"},
        headers={CSRF_HEADER: csrf},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Ship the sequel"
    assert body["promoted_video_id"] is None

    listed = client.get("/api/v1/planner/plans")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [body["id"]]


async def test_viewer_cannot_create_a_plan(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=VIEWER_ID)
    response = client.post(
        "/api/v1/planner/plans",
        json={"title": "Not allowed"},
        headers={CSRF_HEADER: csrf},
    )
    assert response.status_code == 403


async def test_promote_plan_creates_a_planned_video_on_the_board(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    plan = client.post(
        "/api/v1/planner/plans",
        json={"title": "A great idea"},
        headers={CSRF_HEADER: csrf},
    ).json()

    promoted = client.post(
        f"/api/v1/planner/plans/{plan['id']}/promote", headers={CSRF_HEADER: csrf}
    )
    assert promoted.status_code == 201
    video = promoted.json()
    assert video["status"] == "planned"
    assert video["plan_id"] == plan["id"]

    board = client.get("/api/v1/videos")
    assert board.status_code == 200
    assert [v["id"] for v in board.json()] == [video["id"]]


async def test_transition_video_follows_the_state_machine(client: TestClient) -> None:
    csrf = await _sign_in(client, user_id=USER_ID)
    plan = client.post(
        "/api/v1/planner/plans",
        json={"title": "A great idea"},
        headers={CSRF_HEADER: csrf},
    ).json()
    video = client.post(
        f"/api/v1/planner/plans/{plan['id']}/promote", headers={CSRF_HEADER: csrf}
    ).json()

    moved = client.post(
        f"/api/v1/videos/{video['id']}/transition",
        json={"to_status": "drafting"},
        headers={CSRF_HEADER: csrf},
    )
    assert moved.status_code == 200
    assert moved.json()["status"] == "drafting"

    rejected = client.post(
        f"/api/v1/videos/{video['id']}/transition",
        json={"to_status": "published"},
        headers={CSRF_HEADER: csrf},
    )
    assert rejected.status_code == 409
    assert rejected.json()["type"] == "/problems/video-invalid-transition"
