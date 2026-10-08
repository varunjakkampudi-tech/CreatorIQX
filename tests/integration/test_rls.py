"""Row-level security: the meta-test guard and real cross-tenant behaviour (P0-042).

Runs against creatoriqx_test. Needs ``py scripts/dev.py up``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, cast

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import CursorResult, exc, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from creatoriqx_api.platform.database import set_tenant_context

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"

# Every table with a workspace_id column must have forced RLS and a policy.
_TENANT_TABLE_SQL = """
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policies p
        WHERE p.schemaname = 'public' AND p.tablename = c.relname)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
  AND EXISTS (
      SELECT 1 FROM pg_attribute a
      WHERE a.attrelid = c.oid AND a.attname = 'workspace_id' AND NOT a.attisdropped
  )
"""


def _test_url(key: str) -> str:
    value = dotenv_values(REPO_ROOT / ".env").get(key)
    if not value:
        pytest.fail(f"{key} missing from .env. Run: py scripts/dev.py setup")
    base, _ = value.rsplit("/", 1)
    return f"{base}/creatoriqx_test"


def _owner_dsn() -> str:
    return _test_url("DATABASE_OWNER_URL").replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
def _schema_at_head() -> None:
    os.environ["ALEMBIC_DATABASE_URL"] = _test_url("DATABASE_OWNER_URL")
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


async def _rls_gaps(conn: asyncpg.Connection) -> list[str]:
    gaps: list[str] = []
    rows = await conn.fetch(_TENANT_TABLE_SQL)
    if not rows:
        return ["no tenant tables found (meta-test query is broken)"]
    for name, enabled, forced, policies in rows:
        if not (enabled and forced):
            gaps.append(f"{name}: RLS not forced")
        if policies == 0:
            gaps.append(f"{name}: no policy")
    return gaps


def test_every_tenant_table_is_protected() -> None:
    async def body() -> None:
        conn = await asyncpg.connect(_owner_dsn())
        try:
            assert await _rls_gaps(conn) == []
        finally:
            await conn.close()

    asyncio.run(body())


def test_meta_test_detects_a_dropped_policy() -> None:
    async def body() -> None:
        conn = await asyncpg.connect(_owner_dsn())
        transaction = conn.transaction()
        await transaction.start()
        try:
            await conn.execute("DROP POLICY memberships_read ON memberships")
            await conn.execute("DROP POLICY memberships_write ON memberships")
            assert "memberships: no policy" in await _rls_gaps(conn)
        finally:
            await transaction.rollback()
            await conn.close()

    asyncio.run(body())


async def _add_user(session: AsyncSession, user_id: uuid.UUID, email: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, email) VALUES (:i, :e)"), {"i": user_id, "e": email}
    )


async def _add_workspace(session: AsyncSession, workspace_id: uuid.UUID, name: str) -> None:
    await session.execute(
        text("INSERT INTO workspaces (id, name) VALUES (:i, :n)"), {"i": workspace_id, "n": name}
    )


async def _add_membership(
    session: AsyncSession, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO memberships (id, user_id, workspace_id, role) VALUES (:i, :u, :w, 'owner')"
        ),
        {"i": uuid.uuid4(), "u": user_id, "w": workspace_id},
    )


def test_tenant_context_isolates_rows_across_workspaces() -> None:
    engine = create_async_engine(_test_url("DATABASE_APP_URL"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()

    async def body() -> None:
        try:
            async with factory() as session:
                await _add_user(session, user_a, "a@x.com")
                await _add_user(session, user_b, "b@x.com")
                await _add_workspace(session, ws_a, "A")
                await _add_workspace(session, ws_b, "B")

                await set_tenant_context(session, workspace_id=ws_a, user_id=user_a)
                await _add_membership(session, user_a, ws_a)
                await set_tenant_context(session, workspace_id=ws_b, user_id=user_b)
                await _add_membership(session, user_b, ws_b)

                # Back in workspace A: only A's membership is visible.
                await set_tenant_context(session, workspace_id=ws_a, user_id=user_a)
                visible = list(
                    (await session.execute(text("SELECT workspace_id FROM memberships")))
                    .scalars()
                    .all()
                )
                assert visible == [ws_a]

                # Writing into workspace B from context A is rejected by WITH CHECK;
                # a savepoint keeps the seeded rows after the expected failure.
                with pytest.raises(exc.DBAPIError):
                    async with session.begin_nested():
                        await _add_membership(session, user_a, ws_b)

                # Updating B's rows from context A changes nothing (rows invisible).
                result = await session.execute(
                    text("UPDATE memberships SET role = 'viewer' WHERE workspace_id = :w"),
                    {"w": ws_b},
                )
                assert cast("CursorResult[Any]", result).rowcount == 0

                await session.rollback()  # leave the test database clean
        finally:
            await engine.dispose()

    asyncio.run(body())
