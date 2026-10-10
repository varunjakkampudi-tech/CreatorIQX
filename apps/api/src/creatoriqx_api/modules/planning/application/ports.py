"""Ports for the planner and video-lifecycle use cases (spec §6 ports and adapters)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from creatoriqx_api.modules.planning.domain.plan import Plan
from creatoriqx_api.modules.planning.domain.video import Video, VideoStatus


@dataclass(frozen=True, slots=True)
class NewPlan:
    """What the application layer asks a :class:`PlanStore` to persist."""

    workspace_id: uuid.UUID
    title: str
    notes: str
    series: str | None
    scheduled_date: date | None


@dataclass(frozen=True, slots=True)
class NewVideo:
    """What the application layer asks a :class:`VideoStore` to persist."""

    workspace_id: uuid.UUID
    channel_id: uuid.UUID | None
    plan_id: uuid.UUID | None
    title: str
    status: VideoStatus


class PlanStore(Protocol):
    """Persists plans and the one-way promotion to a video (spec §7)."""

    async def create(self, plan: NewPlan) -> Plan: ...

    async def get(self, *, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> Plan | None: ...

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[Plan]: ...

    async def mark_promoted(
        self, *, workspace_id: uuid.UUID, plan_id: uuid.UUID, video_id: uuid.UUID
    ) -> Plan: ...


class VideoStore(Protocol):
    """Persists videos and enforces that every status write is audited (spec §3)."""

    async def create(
        self, video: NewVideo, *, actor_user_id: uuid.UUID, correlation_id: str | None
    ) -> Video: ...

    async def get(self, *, workspace_id: uuid.UUID, video_id: uuid.UUID) -> Video | None: ...

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[Video]: ...

    async def update_status(
        self,
        *,
        workspace_id: uuid.UUID,
        video_id: uuid.UUID,
        status: VideoStatus,
        actor_user_id: uuid.UUID,
        correlation_id: str | None,
    ) -> Video: ...
