"""Platform tables: audit_log append-only, and RLS on usage_events,
idempotency_keys and audit_log (P0-043).

Runs against creatoriqx_test. Needs ``py scripts/dev.py up``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from creatoriqx_api.platform.database import set_tenant_context

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


def _test_url(key: str) -> str:
    value = dotenv_values(REPO_ROOT / ".env").get(key)
    if not value:
        pytest.fail(f"{key} missing from .env. Run: py scripts/dev.py setup")
    base, _ = value.rsplit("/", 1)
    return f"{base}/creatoriqx_test"


def _owner_dsn() -> str:
    return _test_url("DATABASE_OWNER_URL").replace("postgresql+asyncpg://", "postgresql://", 1)


def _app_dsn() -> str:
    return _test_url("DATABASE_APP_URL").replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
def _schema_at_head() -> None:
    os.environ["ALEMBIC_DATABASE_URL"] = _test_url("DATABASE_OWNER_URL")
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


async def _seed_audit_row(conn: asyncpg.Connection, action: str) -> uuid.UUID:
    row_id = uuid.uuid4()
    await conn.execute("INSERT INTO audit_log (id, action) VALUES ($1, $2)", row_id, action)
    return row_id


def test_app_role_cannot_update_or_delete_audit_log() -> None:
    async def body() -> None:
        owner = await asyncpg.connect(_owner_dsn())
        app = await asyncpg.connect(_app_dsn())
        try:
            row_id = await _seed_audit_row(owner, "test.append_only.app_role")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute("UPDATE audit_log SET action = 'x' WHERE id = $1", row_id)
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app.execute("DELETE FROM audit_log WHERE id = $1", row_id)
        finally:
            # The trigger blocks DELETE for every role, including the owner
            # (that is the point); disable it only for test cleanup.
            await owner.execute(
                "ALTER TABLE audit_log DISABLE TRIGGER audit_log_block_update_delete"
            )
            await owner.execute("DELETE FROM audit_log WHERE action = 'test.append_only.app_role'")
            await owner.execute(
                "ALTER TABLE audit_log ENABLE TRIGGER audit_log_block_update_delete"
            )
            await owner.close()
            await app.close()

    asyncio.run(body())


def test_rls_alone_already_blocks_update_and_delete_for_the_owner_role() -> None:
    """With no UPDATE/DELETE policy defined, forced RLS denies both commands
    by default: the owner's write touches zero rows without ever reaching
    the trigger. This is the layer that actually protects the owner role
    day to day; the trigger below is the backstop if a policy is ever added."""

    async def body() -> None:
        owner = await asyncpg.connect(_owner_dsn())
        try:
            row_id = await _seed_audit_row(owner, "test.append_only.rls_default_deny")
            update_tag = await owner.execute(
                "UPDATE audit_log SET action = 'x' WHERE id = $1", row_id
            )
            delete_tag = await owner.execute("DELETE FROM audit_log WHERE id = $1", row_id)
            assert update_tag == "UPDATE 0"
            assert delete_tag == "DELETE 0"
        finally:
            await owner.execute(
                "ALTER TABLE audit_log DISABLE TRIGGER audit_log_block_update_delete"
            )
            await owner.execute(
                "DELETE FROM audit_log WHERE action = 'test.append_only.rls_default_deny'"
            )
            await owner.execute(
                "ALTER TABLE audit_log ENABLE TRIGGER audit_log_block_update_delete"
            )
            await owner.close()

    asyncio.run(body())


def test_trigger_blocks_update_and_delete_even_if_a_future_policy_allowed_it() -> None:
    """Defence in depth, proven: today RLS has no UPDATE/DELETE policy on
    audit_log, so those commands already touch zero rows for every role,
    trigger or not. This test simulates the policy gap that would remove
    that first layer (someone adds a permissive policy by mistake) and
    proves the trigger still blocks the write on its own, including for the
    table owner, who is otherwise exempt from nothing else here."""

    async def body() -> None:
        owner = await asyncpg.connect(_owner_dsn())
        try:
            await owner.execute(
                "CREATE POLICY test_audit_log_permissive_write ON audit_log "
                "FOR UPDATE USING (true) WITH CHECK (true)"
            )
            await owner.execute(
                "CREATE POLICY test_audit_log_permissive_delete ON audit_log "
                "FOR DELETE USING (true)"
            )
            row_id = await _seed_audit_row(owner, "test.append_only.owner_role")
            with pytest.raises(asyncpg.RaiseError, match="append-only"):
                await owner.execute("UPDATE audit_log SET action = 'x' WHERE id = $1", row_id)
            with pytest.raises(asyncpg.RaiseError, match="append-only"):
                await owner.execute("DELETE FROM audit_log WHERE id = $1", row_id)
        finally:
            await owner.execute(
                "DROP POLICY IF EXISTS test_audit_log_permissive_write ON audit_log"
            )
            await owner.execute(
                "DROP POLICY IF EXISTS test_audit_log_permissive_delete ON audit_log"
            )
            await owner.execute(
                "ALTER TABLE audit_log DISABLE TRIGGER audit_log_block_update_delete"
            )
            await owner.execute(
                "DELETE FROM audit_log WHERE action = 'test.append_only.owner_role'"
            )
            await owner.execute(
                "ALTER TABLE audit_log ENABLE TRIGGER audit_log_block_update_delete"
            )
            await owner.close()

    asyncio.run(body())


def test_usage_events_and_idempotency_keys_are_isolated_per_workspace() -> None:
    engine = create_async_engine(_test_url("DATABASE_APP_URL"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()

    async def body() -> None:
        try:
            async with factory() as session:
                await set_tenant_context(session, workspace_id=ws_a, user_id=uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO usage_events (id, workspace_id, name, schema_version) "
                        "VALUES (:i, :w, 'auth.login_succeeded', 1)"
                    ),
                    {"i": uuid.uuid4(), "w": ws_a},
                )
                await session.execute(
                    text(
                        "INSERT INTO idempotency_keys "
                        "(id, workspace_id, key, request_hash) VALUES (:i, :w, 'k1', 'h1')"
                    ),
                    {"i": uuid.uuid4(), "w": ws_a},
                )

                await set_tenant_context(session, workspace_id=ws_b, user_id=uuid.uuid4())
                visible_usage = (
                    await session.execute(text("SELECT count(*) FROM usage_events"))
                ).scalar_one()
                visible_keys = (
                    await session.execute(text("SELECT count(*) FROM idempotency_keys"))
                ).scalar_one()
                assert visible_usage == 0
                assert visible_keys == 0

                await set_tenant_context(session, workspace_id=ws_a, user_id=uuid.uuid4())
                visible_usage = (
                    await session.execute(text("SELECT count(*) FROM usage_events"))
                ).scalar_one()
                assert visible_usage == 1

                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(body())


def test_audit_log_read_policy_allows_own_workspace_and_null_workspace() -> None:
    engine = create_async_engine(_test_url("DATABASE_APP_URL"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ws_a, ws_b = uuid.uuid4(), uuid.uuid4()

    async def _insert(session: AsyncSession, workspace_id: uuid.UUID | None, action: str) -> None:
        await session.execute(
            text("INSERT INTO audit_log (id, workspace_id, action) VALUES (:i, :w, :a)"),
            {"i": uuid.uuid4(), "w": workspace_id, "a": action},
        )

    async def body() -> None:
        try:
            async with factory() as session:
                await set_tenant_context(session, workspace_id=ws_a, user_id=uuid.uuid4())
                await _insert(session, ws_a, "test.read_policy.a")
                await _insert(session, None, "test.read_policy.null")

                await set_tenant_context(session, workspace_id=ws_b, user_id=uuid.uuid4())
                await _insert(session, ws_b, "test.read_policy.b")

                await set_tenant_context(session, workspace_id=ws_a, user_id=uuid.uuid4())
                actions = set(
                    (
                        await session.execute(
                            text(
                                "SELECT action FROM audit_log "
                                "WHERE action LIKE 'test.read_policy.%'"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert actions == {"test.read_policy.a", "test.read_policy.null"}

                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(body())
