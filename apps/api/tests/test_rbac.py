"""RBAC rules and the two identity routes (P0-054, spec §10 Authorization).

Domain ranking, the authorize use case, and ``GET /api/v1/me`` and
``GET /api/v1/workspaces/current`` end to end with in-memory stores.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.domain.access import (
    InsufficientRoleError,
    WorkspaceAccess,
    role_satisfies,
)
from creatoriqx_api.modules.workspaces.infrastructure.memory_access_store import (
    InMemoryWorkspaceAccessStore,
)
from creatoriqx_api.platform.errors import DomainError
from creatoriqx_api.settings import Settings

POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
SESSION_COOKIE = "__Host-creatoriqx_session"
USER = uuid.UUID(int=11)
OTHER_USER = uuid.UUID(int=12)
WORKSPACE = uuid.UUID(int=21)
WORKSPACE_NAME = "ada's workspace"


# --- domain -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "required", "allowed"),
    [
        (Role.OWNER, Role.OWNER, True),
        (Role.OWNER, Role.EDITOR, True),
        (Role.OWNER, Role.VIEWER, True),
        (Role.EDITOR, Role.OWNER, False),
        (Role.EDITOR, Role.EDITOR, True),
        (Role.EDITOR, Role.VIEWER, True),
        (Role.VIEWER, Role.OWNER, False),
        (Role.VIEWER, Role.EDITOR, False),
        (Role.VIEWER, Role.VIEWER, True),
    ],
)
def test_role_ranking(actual: Role, required: Role, allowed: bool) -> None:
    assert role_satisfies(actual, required) is allowed


def test_every_role_is_ranked() -> None:
    # A new role must be given a rank, or role_satisfies would raise at runtime.
    for role in Role:
        assert role_satisfies(role, Role.VIEWER) in (True, False)


def test_insufficient_role_is_a_403_domain_error() -> None:
    error = InsufficientRoleError()
    assert isinstance(error, DomainError)
    assert error.status == 403
    assert error.code == "insufficient-role"


def test_access_satisfies_delegates_to_the_ranking() -> None:
    access = WorkspaceAccess(workspace_id=WORKSPACE, name=WORKSPACE_NAME, role=Role.EDITOR)
    assert access.satisfies(Role.VIEWER) is True
    assert access.satisfies(Role.OWNER) is False


# --- application --------------------------------------------------------------


def _service(role: Role = Role.OWNER) -> WorkspaceAccessService:
    store = InMemoryWorkspaceAccessStore()
    store.grant(WorkspaceAccess(workspace_id=WORKSPACE, name=WORKSPACE_NAME, role=role), USER)
    return WorkspaceAccessService(store)


async def test_authorize_returns_the_membership_for_a_permitted_caller() -> None:
    access = await _service(Role.EDITOR).authorize(
        workspace_id=WORKSPACE, user_id=USER, required=Role.VIEWER
    )
    assert access.role is Role.EDITOR
    assert access.name == WORKSPACE_NAME


async def test_authorize_refuses_a_role_that_is_too_low() -> None:
    with pytest.raises(InsufficientRoleError):
        await _service(Role.VIEWER).authorize(
            workspace_id=WORKSPACE, user_id=USER, required=Role.OWNER
        )


async def test_authorize_refuses_a_user_who_is_not_a_member() -> None:
    with pytest.raises(InsufficientRoleError):
        await _service().authorize(
            workspace_id=WORKSPACE, user_id=OTHER_USER, required=Role.VIEWER
        )


async def test_authorize_refuses_a_workspace_the_caller_does_not_belong_to() -> None:
    with pytest.raises(InsufficientRoleError):
        await _service().authorize(
            workspace_id=uuid.UUID(int=99), user_id=USER, required=Role.VIEWER
        )


async def test_refusal_does_not_say_which_reason_applied() -> None:
    # A non-member and an under-privileged member get the same code, so the
    # response cannot be used to discover which workspaces exist.
    non_member = InsufficientRoleError()
    with pytest.raises(InsufficientRoleError) as low:
        await _service(Role.VIEWER).authorize(
            workspace_id=WORKSPACE, user_id=USER, required=Role.OWNER
        )
    assert low.value.code == non_member.code
    assert low.value.status == non_member.status


# --- routes -------------------------------------------------------------------


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(
        database_app_url=SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        redis_url=SecretStr("redis://localhost:1/0"),
    )
    app = create_app(settings, checks=[])
    store = InMemoryKeyValueStore()
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, POLICY)
    access_store = InMemoryWorkspaceAccessStore()
    access_store.grant(
        WorkspaceAccess(workspace_id=WORKSPACE, name=WORKSPACE_NAME, role=Role.OWNER), USER
    )
    app.state.workspace_access_service = WorkspaceAccessService(access_store)
    with TestClient(app, base_url="https://testserver") as built:
        yield built


async def _sign_in(client: TestClient, *, user_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
    service: SessionService = client.app.state.session_service  # type: ignore[attr-defined]
    session = await service.create(
        subject="google-sub-1",
        email="creator@example.com",
        user_id=user_id,
        workspace_id=workspace_id,
    )
    client.cookies.set(SESSION_COOKIE, session.id)


async def test_me_returns_the_caller_and_their_role(client: TestClient) -> None:
    await _sign_in(client, user_id=USER, workspace_id=WORKSPACE)
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "user_id": str(USER),
        "email": "creator@example.com",
        "workspace_id": str(WORKSPACE),
        "role": "owner",
    }


async def test_current_workspace_returns_the_session_workspace(client: TestClient) -> None:
    await _sign_in(client, user_id=USER, workspace_id=WORKSPACE)
    response = client.get("/api/v1/workspaces/current")
    assert response.status_code == 200
    assert response.json() == {
        "id": str(WORKSPACE),
        "name": WORKSPACE_NAME,
        "role": "owner",
    }


@pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/workspaces/current"])
def test_routes_require_a_session(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["type"] == "/problems/session-required"


@pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/workspaces/current"])
async def test_routes_refuse_a_session_naming_a_workspace_the_user_left(
    client: TestClient, path: str
) -> None:
    # The session is valid and names a real workspace, but this user holds no
    # membership in it: a removed member must not keep working.
    await _sign_in(client, user_id=OTHER_USER, workspace_id=WORKSPACE)
    response = client.get(path)
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/insufficient-role"
