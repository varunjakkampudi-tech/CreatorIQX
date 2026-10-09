"""Workspace access checks against real PostgreSQL (P0-054).

Runs against creatoriqx_test as the runtime role under forced RLS. Needs
``py scripts/dev.py up``. Proves that the access store answers from real
membership rows, and that a non-member is refused even though row-level
security would have let them read the workspace's membership list.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
    WorkspaceBootstrapService,
)
from creatoriqx_api.modules.workspaces.domain.access import InsufficientRoleError
from creatoriqx_api.modules.workspaces.infrastructure.sql_access_store import (
    SqlWorkspaceAccessStore,
)
from creatoriqx_api.modules.workspaces.infrastructure.sql_store import SqlPersonalWorkspaceStore

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


def _test_url(key: str) -> str:
    value = dotenv_values(REPO_ROOT / ".env").get(key)
    if not value:
        pytest.fail(f"{key} missing from .env. Run: py scripts/dev.py setup")
    base, _ = value.rsplit("/", 1)
    return f"{base}/creatoriqx_test"


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
def access(factory: async_sessionmaker[AsyncSession]) -> WorkspaceAccessService:
    return WorkspaceAccessService(SqlWorkspaceAccessStore(factory))


@pytest.fixture
def bootstrap(factory: async_sessionmaker[AsyncSession]) -> WorkspaceBootstrapService:
    return WorkspaceBootstrapService(SqlPersonalWorkspaceStore(factory))


def _new_identity() -> tuple[str, str]:
    token = uuid.uuid4().hex
    return f"sub-{token}", f"{token}@example.com"


async def test_the_owner_of_a_fresh_workspace_is_authorized(
    bootstrap: WorkspaceBootstrapService, access: WorkspaceAccessService
) -> None:
    subject, email = _new_identity()
    created = await bootstrap.ensure_personal_workspace(subject=subject, email=email)

    granted = await access.authorize(
        workspace_id=created.workspace_id, user_id=created.user_id, required=Role.OWNER
    )
    assert granted.role is Role.OWNER
    assert granted.workspace_id == created.workspace_id
    assert granted.name.endswith("'s workspace")


@pytest.mark.parametrize("required", [Role.VIEWER, Role.EDITOR, Role.OWNER])
async def test_the_owner_satisfies_every_role(
    bootstrap: WorkspaceBootstrapService, access: WorkspaceAccessService, required: Role
) -> None:
    subject, email = _new_identity()
    created = await bootstrap.ensure_personal_workspace(subject=subject, email=email)
    resolved = await access.authorize(
        workspace_id=created.workspace_id, user_id=created.user_id, required=required
    )
    assert resolved.role is Role.OWNER


async def test_a_user_from_another_workspace_is_refused(
    bootstrap: WorkspaceBootstrapService, access: WorkspaceAccessService
) -> None:
    alice_sub, alice_email = _new_identity()
    bob_sub, bob_email = _new_identity()
    alice = await bootstrap.ensure_personal_workspace(subject=alice_sub, email=alice_email)
    bob = await bootstrap.ensure_personal_workspace(subject=bob_sub, email=bob_email)

    # Bob's session names Alice's workspace. The membership check refuses him,
    # which is the application layer doing its job; RLS is the second layer.
    with pytest.raises(InsufficientRoleError):
        await access.authorize(
            workspace_id=alice.workspace_id, user_id=bob.user_id, required=Role.VIEWER
        )

    # Bob is still fine in his own workspace.
    own = await access.authorize(
        workspace_id=bob.workspace_id, user_id=bob.user_id, required=Role.OWNER
    )
    assert own.workspace_id == bob.workspace_id


async def test_an_unknown_workspace_is_refused(
    bootstrap: WorkspaceBootstrapService, access: WorkspaceAccessService
) -> None:
    subject, email = _new_identity()
    created = await bootstrap.ensure_personal_workspace(subject=subject, email=email)
    with pytest.raises(InsufficientRoleError):
        await access.authorize(
            workspace_id=uuid.uuid4(), user_id=created.user_id, required=Role.VIEWER
        )
