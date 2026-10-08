"""Async database engine, unit of work, and per-request tenant context.

The app connects as the runtime role (``database_app_url``, ADR 0002). Migrations
connect as the owner role through Alembic, never through this module. Row-level
security reads the tenant from transaction-local settings established by
``set_tenant_context``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from creatoriqx_api.settings import Settings

# Transaction-local (is_local = true): set with SET LOCAL semantics via set_config,
# so the value is scoped to the current transaction and never leaks across a pooled
# connection. Read by the RLS policies as current_setting('app.workspace_id', true).
_SET_CONTEXT = text(
    "SELECT set_config('app.workspace_id', :workspace_id, true), "
    "set_config('app.user_id', :user_id, true)"
)


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine for the runtime role."""
    return create_async_engine(
        settings.database_app_url.get_secret_value(),
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to ``engine``."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def set_tenant_context(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Bind the tenant for the current transaction; RLS enforces isolation from here."""
    await session.execute(
        _SET_CONTEXT, {"workspace_id": str(workspace_id), "user_id": str(user_id)}
    )


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Unit of work: commit on success, roll back on error, always close."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
