"""First-login bootstrap against real PostgreSQL under forced RLS (P0-053, ADR 0011).

Runs against creatoriqx_test as the runtime role. Needs ``py scripts/dev.py up``.
Acceptance: two logins create exactly one workspace; audit and outbox rows are
present; repeat login is idempotent; concurrent first logins cannot duplicate
the workspace; a workspace is invisible to a user who is not a member.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
    WorkspaceBootstrapService,
)
from creatoriqx_api.modules.workspaces.domain.bootstrap import (
    NO_WORKSPACE,
    IdentityConflictError,
    personal_workspace_name,
)
from creatoriqx_api.modules.workspaces.infrastructure.sql_store import SqlPersonalWorkspaceStore
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


@pytest.fixture(scope="module", autouse=True)
def _schema_at_head() -> None:
    os.environ["ALEMBIC_DATABASE_URL"] = _test_url("DATABASE_OWNER_URL")
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    built = create_async_engine(_test_url("DATABASE_APP_URL"), pool_pre_ping=True)
    yield built
    await built.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
def service(factory: async_sessionmaker[AsyncSession]) -> WorkspaceBootstrapService:
    return WorkspaceBootstrapService(SqlPersonalWorkspaceStore(factory))


def _new_identity() -> tuple[str, str]:
    """A fresh Google subject and email, so every test owns its own person."""
    token = uuid.uuid4().hex
    return f"sub-{token}", f"{token}@example.com"


async def _read_as(
    factory: async_sessionmaker[AsyncSession],
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    sql: str,
    params: dict[str, Any] | None = None,
) -> list[tuple[Any, ...]]:
    """Run one read under a tenant context, the way a request would."""
    async with factory() as session, session.begin():
        await set_tenant_context(session, workspace_id=workspace_id, user_id=user_id)
        result = await session.execute(text(sql), params or {})
        return [tuple(row) for row in result.all()]


async def test_first_login_writes_user_workspace_membership_audit_and_outbox(
    service: WorkspaceBootstrapService, factory: async_sessionmaker[AsyncSession]
) -> None:
    subject, email = _new_identity()
    result = await service.ensure_personal_workspace(subject=subject, email=email)
    assert result.user_created and result.workspace_created

    ws, user = result.workspace_id, result.user_id
    [(name,)] = await _read_as(
        factory, workspace_id=ws, user_id=user, sql="SELECT name FROM workspaces WHERE id = :w",
        params={"w": ws},
    )
    assert name == personal_workspace_name(email)

    members = await _read_as(
        factory,
        workspace_id=ws,
        user_id=user,
        sql="SELECT user_id, role FROM memberships WHERE workspace_id = :w",
        params={"w": ws},
    )
    assert members == [(user, Role.OWNER.value)]

    actions = await _read_as(
        factory,
        workspace_id=ws,
        user_id=user,
        sql="SELECT action FROM audit_log WHERE workspace_id = :w ORDER BY action",
        params={"w": ws},
    )
    assert sorted(action for (action,) in actions) == [
        "auth.login_succeeded",
        "workspace.created",
    ]

    # user.created has no workspace, so it is read under the no-workspace sentinel.
    user_audit = await _read_as(
        factory,
        workspace_id=NO_WORKSPACE,
        user_id=user,
        sql="SELECT action FROM audit_log WHERE actor_user_id = :u AND workspace_id IS NULL",
        params={"u": user},
    )
    assert user_audit == [("user.created",)]

    outbox = await _read_as(
        factory,
        workspace_id=ws,
        user_id=user,
        sql="SELECT event_type FROM outbox_events WHERE payload->>'workspace_id' = :w",
        params={"w": str(ws)},
    )
    assert outbox == [("workspace.created",)]


async def test_repeat_login_returns_the_same_ids_and_writes_no_second_workspace(
    service: WorkspaceBootstrapService, factory: async_sessionmaker[AsyncSession]
) -> None:
    subject, email = _new_identity()
    first = await service.ensure_personal_workspace(subject=subject, email=email)
    second = await service.ensure_personal_workspace(subject=subject, email=email)

    assert second.user_id == first.user_id
    assert second.workspace_id == first.workspace_id
    assert second.user_created is False and second.workspace_created is False

    ws, user = first.workspace_id, first.user_id
    [(membership_count,)] = await _read_as(
        factory,
        workspace_id=ws,
        user_id=user,
        sql="SELECT count(*) FROM memberships WHERE user_id = :u",
        params={"u": user},
    )
    assert membership_count == 1

    [(logins,)] = await _read_as(
        factory,
        workspace_id=ws,
        user_id=user,
        sql="SELECT count(*) FROM audit_log WHERE workspace_id = :w AND action = 'auth.login_succeeded'",
        params={"w": ws},
    )
    assert logins == 2


async def test_concurrent_first_logins_create_exactly_one_workspace(
    service: WorkspaceBootstrapService, factory: async_sessionmaker[AsyncSession]
) -> None:
    subject, email = _new_identity()
    results = await asyncio.gather(
        *(service.ensure_personal_workspace(subject=subject, email=email) for _ in range(5))
    )
    assert len({r.workspace_id for r in results}) == 1
    assert len({r.user_id for r in results}) == 1
    assert sum(r.workspace_created for r in results) == 1

    ws, user = results[0].workspace_id, results[0].user_id
    [(count,)] = await _read_as(
        factory,
        workspace_id=ws,
        user_id=user,
        sql="SELECT count(*) FROM memberships WHERE user_id = :u",
        params={"u": user},
    )
    assert count == 1


async def test_a_workspace_is_invisible_to_a_user_who_is_not_a_member(
    service: WorkspaceBootstrapService, factory: async_sessionmaker[AsyncSession]
) -> None:
    alice_sub, alice_email = _new_identity()
    bob_sub, bob_email = _new_identity()
    alice = await service.ensure_personal_workspace(subject=alice_sub, email=alice_email)
    bob = await service.ensure_personal_workspace(subject=bob_sub, email=bob_email)

    seen_by_bob = await _read_as(
        factory,
        workspace_id=bob.workspace_id,
        user_id=bob.user_id,
        sql="SELECT id FROM workspaces WHERE id = :w",
        params={"w": alice.workspace_id},
    )
    assert seen_by_bob == []

    own = await _read_as(
        factory,
        workspace_id=bob.workspace_id,
        user_id=bob.user_id,
        sql="SELECT id FROM workspaces",
    )
    assert own == [(bob.workspace_id,)]


async def test_an_email_bound_to_another_subject_is_refused_and_writes_nothing(
    service: WorkspaceBootstrapService, factory: async_sessionmaker[AsyncSession]
) -> None:
    subject, email = _new_identity()
    await service.ensure_personal_workspace(subject=subject, email=email)

    with pytest.raises(IdentityConflictError):
        await service.ensure_personal_workspace(subject=f"other-{subject}", email=email)

    conn = await asyncpg.connect(_owner_dsn())
    try:
        count = await conn.fetchval("SELECT count(*) FROM users WHERE email = $1", email)
    finally:
        await conn.close()
    assert count == 1


async def test_workspaces_table_has_forced_rls_and_its_three_policies() -> None:
    conn = await asyncpg.connect(_owner_dsn())
    try:
        row = await conn.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'workspaces'"
        )
        policies = await conn.fetch(
            "SELECT policyname FROM pg_policies WHERE tablename = 'workspaces' ORDER BY policyname"
        )
    finally:
        await conn.close()
    assert row is not None and row["relrowsecurity"] and row["relforcerowsecurity"]
    assert [p["policyname"] for p in policies] == [
        "workspaces_insert",
        "workspaces_read",
        "workspaces_update",
    ]
