"""SQLAlchemy adapter for :class:`PlanStore`."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creatoriqx_api.modules.planning.application.ports import NewPlan
from creatoriqx_api.modules.planning.domain.errors import PlanNotFoundError
from creatoriqx_api.modules.planning.domain.plan import Plan
from creatoriqx_api.modules.planning.infrastructure.tables import PlanRow
from creatoriqx_api.platform.database import session_scope, set_tenant_context

# plans' RLS policy only checks workspace_id, never user_id; this port carries
# no acting user, so a nil UUID stands in (same convention as
# youtube.infrastructure.quota_ledger._NO_ACTOR / telemetry's _NO_ACTOR).
_NO_ACTOR = uuid.UUID(int=0)


class SqlPlanStore:
    """Persists plans under the caller's tenant context (RLS, ADR 0002)."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def create(self, plan: NewPlan) -> Plan:
        async with session_scope(self._factory) as session:
            # A plan has no actor on this port (spec feature 4: planning is
            # not a sensitive action); the tenant context still must be set
            # before FORCE RLS will accept the insert's WITH CHECK clause.
            await _set_system_tenant_context(session, workspace_id=plan.workspace_id)
            row = PlanRow(
                workspace_id=plan.workspace_id,
                title=plan.title,
                notes=plan.notes,
                series=plan.series,
                scheduled_date=plan.scheduled_date,
            )
            session.add(row)
            await session.flush()
            return _to_domain(row)

    async def get(self, *, workspace_id: uuid.UUID, plan_id: uuid.UUID) -> Plan | None:
        async with session_scope(self._factory) as session:
            await _set_system_tenant_context(session, workspace_id=workspace_id)
            result = await session.execute(
                select(PlanRow).where(PlanRow.workspace_id == workspace_id, PlanRow.id == plan_id)
            )
            row = result.scalar_one_or_none()
            return _to_domain(row) if row is not None else None

    async def list_for_workspace(self, *, workspace_id: uuid.UUID) -> list[Plan]:
        async with session_scope(self._factory) as session:
            await _set_system_tenant_context(session, workspace_id=workspace_id)
            result = await session.execute(
                select(PlanRow)
                .where(PlanRow.workspace_id == workspace_id)
                .order_by(PlanRow.created_at.desc())
            )
            return [_to_domain(row) for row in result.scalars().all()]

    async def mark_promoted(
        self, *, workspace_id: uuid.UUID, plan_id: uuid.UUID, video_id: uuid.UUID
    ) -> Plan:
        async with session_scope(self._factory) as session:
            await _set_system_tenant_context(session, workspace_id=workspace_id)
            result = await session.execute(
                select(PlanRow).where(PlanRow.workspace_id == workspace_id, PlanRow.id == plan_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise PlanNotFoundError()
            row.promoted_video_id = video_id
            await session.flush()
            return _to_domain(row)


async def _set_system_tenant_context(session: AsyncSession, *, workspace_id: uuid.UUID) -> None:
    await set_tenant_context(session, workspace_id=workspace_id, user_id=_NO_ACTOR)


def _to_domain(row: PlanRow) -> Plan:
    return Plan(
        id=row.id,
        workspace_id=row.workspace_id,
        title=row.title,
        notes=row.notes,
        series=row.series,
        scheduled_date=row.scheduled_date,
        promoted_video_id=row.promoted_video_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
