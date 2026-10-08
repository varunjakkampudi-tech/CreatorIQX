"""Constraint tests for the identity schema against creatoriqx_test (P0-041).

Each test runs inside a transaction that is rolled back, so nothing persists.
Needs ``py scripts/dev.py up``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


def _dsn() -> str:
    values = dotenv_values(REPO_ROOT / ".env")
    owner = values.get("DATABASE_OWNER_URL")
    if not owner:
        pytest.fail("DATABASE_OWNER_URL missing from .env. Run: py scripts/dev.py setup")
    base, _ = owner.rsplit("/", 1)
    return f"{base}/creatoriqx_test".replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
def _schema_at_head() -> None:
    os.environ["ALEMBIC_DATABASE_URL"] = _dsn().replace("postgresql://", "postgresql+asyncpg://", 1)
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@asynccontextmanager
async def _rolled_back() -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(_dsn())
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


def _run(coro: Callable[[asyncpg.Connection], Awaitable[None]]) -> None:
    async def _main() -> None:
        async with _rolled_back() as connection:
            await coro(connection)

    asyncio.run(_main())


async def _add_user(conn: asyncpg.Connection, email: str) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute("INSERT INTO users (id, email) VALUES ($1, $2)", uid, email)
    return uid


async def _add_workspace(conn: asyncpg.Connection, name: str) -> uuid.UUID:
    wid = uuid.uuid4()
    await conn.execute("INSERT INTO workspaces (id, name) VALUES ($1, $2)", wid, name)
    return wid


async def _add_membership(
    conn: asyncpg.Connection, user_id: uuid.UUID, workspace_id: uuid.UUID, role: str
) -> None:
    # memberships has forced RLS (P0-042): set the tenant context first so the
    # WITH CHECK policy accepts the row, then the schema constraints apply.
    await conn.execute(
        "SELECT set_config('app.workspace_id', $1, true), set_config('app.user_id', $2, true)",
        str(workspace_id),
        str(user_id),
    )
    await conn.execute(
        "INSERT INTO memberships (id, user_id, workspace_id, role) VALUES ($1, $2, $3, $4::role)",
        uuid.uuid4(),
        user_id,
        workspace_id,
        role,
    )


def test_duplicate_membership_is_rejected() -> None:
    async def body(conn: asyncpg.Connection) -> None:
        user = await _add_user(conn, "dup@example.com")
        workspace = await _add_workspace(conn, "Dup WS")
        await _add_membership(conn, user, workspace, "owner")
        with pytest.raises(asyncpg.UniqueViolationError):
            await _add_membership(conn, user, workspace, "editor")

    _run(body)


@pytest.mark.parametrize("role", ["owner", "editor", "viewer"])
def test_valid_roles_are_accepted(role: str) -> None:
    async def body(conn: asyncpg.Connection) -> None:
        user = await _add_user(conn, f"{role}@example.com")
        workspace = await _add_workspace(conn, f"WS {role}")
        await _add_membership(conn, user, workspace, role)

    _run(body)


def test_unknown_role_is_rejected() -> None:
    async def body(conn: asyncpg.Connection) -> None:
        user = await _add_user(conn, "admin@example.com")
        workspace = await _add_workspace(conn, "Admin WS")
        with pytest.raises(asyncpg.exceptions.InvalidTextRepresentationError):
            await _add_membership(conn, user, workspace, "admin")

    _run(body)


def test_membership_requires_an_existing_user() -> None:
    async def body(conn: asyncpg.Connection) -> None:
        workspace = await _add_workspace(conn, "Orphan WS")
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await _add_membership(conn, uuid.uuid4(), workspace, "owner")

    _run(body)


def test_duplicate_email_is_rejected() -> None:
    async def body(conn: asyncpg.Connection) -> None:
        await _add_user(conn, "same@example.com")
        with pytest.raises(asyncpg.UniqueViolationError):
            await _add_user(conn, "same@example.com")

    _run(body)
