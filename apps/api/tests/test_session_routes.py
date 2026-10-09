"""HTTP behaviour of the session routes (P0-051, ADR 0010).

Covers /auth/session and /auth/logout end to end through the app factory, with
an in-memory store and a controllable clock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.settings import Settings

START = datetime(2026, 10, 9, 9, 0, tzinfo=UTC)
POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
SESSION_COOKIE = "__Host-creatoriqx_session"
USER_ID = uuid.UUID(int=1)
WORKSPACE_ID = uuid.UUID(int=2)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(clock: FakeClock) -> TestClient:
    settings = Settings(
        database_app_url=SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        redis_url=SecretStr("redis://localhost:1/0"),
    )
    app = create_app(settings, checks=[])
    store = InMemoryKeyValueStore(clock)
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, POLICY, clock)
    return TestClient(app, base_url="https://testserver")


async def _sign_in(client: TestClient) -> tuple[str, str]:
    service: SessionService = client.app.state.session_service  # type: ignore[attr-defined]
    session = await service.create(
        subject="google-sub-1",
        email="creator@example.com",
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
    )
    client.cookies.set(SESSION_COOKIE, session.id)
    return session.id, session.csrf_token


def test_session_endpoint_requires_a_cookie(client: TestClient) -> None:
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "/problems/session-required"


async def test_session_endpoint_returns_user_and_csrf_token(client: TestClient) -> None:
    _, csrf = await _sign_in(client)
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["email"] == "creator@example.com"
    assert body["subject"] == "google-sub-1"
    assert body["user_id"] == str(USER_ID)
    assert body["workspace_id"] == str(WORKSPACE_ID)
    assert body["csrf_token"] == csrf


async def test_logout_needs_the_csrf_header(client: TestClient) -> None:
    await _sign_in(client)
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 403
    assert response.json()["type"] == "/problems/csrf-token-invalid"
    assert client.get("/api/v1/auth/session").status_code == 200  # still signed in


async def test_logout_with_csrf_ends_the_session_and_clears_the_cookie(
    client: TestClient,
) -> None:
    _, csrf = await _sign_in(client)
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/v1/auth/session").status_code == 401


async def test_idle_session_is_reported_as_expired(client: TestClient, clock: FakeClock) -> None:
    await _sign_in(client)
    clock.now += timedelta(minutes=31)
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 401
    assert response.json()["type"] == "/problems/session-expired"
