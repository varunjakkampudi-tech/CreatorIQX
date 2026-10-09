"""Cross-tenant route harness (P0-054, spec §17 Security).

Walks every route in the OpenAPI document and calls it as a signed-in user who
is **not** a member of the workspace their session names. Every route must
refuse. A route that answers is a tenant-isolation hole.

The harness reads the OpenAPI document rather than a hand-written list, so a
route added later is covered the moment it appears. Exempting a route is a
deliberate act: it must be added to ``EXEMPT`` with a reason, and
``test_no_stale_exemptions`` fails once an exempt route disappears.

``test_the_harness_catches_an_unprotected_route`` seeds a route with no role
check and proves the harness turns red, so the harness itself is tested.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.identity.api.dependencies import CSRF_HEADER
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.roles import Role
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.workspaces.application.access_service import WorkspaceAccessService
from creatoriqx_api.modules.workspaces.domain.access import WorkspaceAccess
from creatoriqx_api.modules.workspaces.infrastructure.memory_access_store import (
    InMemoryWorkspaceAccessStore,
)
from creatoriqx_api.settings import Settings

POLICY = SessionPolicy(idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12))
SESSION_COOKIE = "__Host-creatoriqx_session"

# Workspace A belongs to its owner. The intruder is a real signed-in user whose
# session names workspace A, but who holds no membership there.
WORKSPACE_A = uuid.UUID(int=101)
OWNER_OF_A = uuid.UUID(int=201)
INTRUDER = uuid.UUID(int=202)

# A denial. 404 counts: hiding existence is a valid answer to a non-member.
DENIED = frozenset({401, 403, 404})

# Routes that carry no workspace data, each with the reason it is exempt.
EXEMPT: dict[tuple[str, str], str] = {
    ("GET", "/healthz"): "Liveness probe; reports no tenant data",
    ("GET", "/readyz"): "Readiness probe; reports dependency status only",
    ("GET", "/api/v1/auth/login"): "Starts the login flow; must work before any session exists",
    ("GET", "/api/v1/auth/callback"): "Finishes the login flow; the session is created here",
    ("GET", "/api/v1/auth/session"): "Returns the caller's own session record, no workspace data",
    ("POST", "/api/v1/auth/logout"): "Ends the caller's own session",
}


def _documented_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every (method, path) pair in the OpenAPI document."""
    routes: set[tuple[str, str]] = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                routes.add((method.upper(), path))
    return routes


def _concrete(path: str) -> str:
    """Fill path parameters with a syntactically valid identifier."""
    out: list[str] = []
    for part in path.split("/"):
        out.append(str(uuid.UUID(int=999)) if part.startswith("{") else part)
    return "/".join(out)


def _probe(client: TestClient, routes: set[tuple[str, str]], csrf: str) -> list[str]:
    """Call every route as the intruder; return a line per route that answered."""
    failures: list[str] = []
    for method, path in sorted(routes):
        response = client.request(
            method,
            _concrete(path),
            headers={CSRF_HEADER: csrf},
            json={} if method in {"POST", "PUT", "PATCH"} else None,
        )
        if response.status_code not in DENIED:
            failures.append(f"{method} {path} answered {response.status_code}")
    return failures


def _settings() -> Settings:
    return Settings(
        database_app_url=SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        redis_url=SecretStr("redis://localhost:1/0"),
        oidc_client_id="test-client-id",
        oidc_client_secret=SecretStr("test-client-secret"),
        readiness_timeout_seconds=0.2,
    )


def _wire_in_memory(app: FastAPI) -> None:
    """Replace Redis and Postgres with in-memory doubles; only A's owner is a member."""
    store = InMemoryKeyValueStore()
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, POLICY)
    access = InMemoryWorkspaceAccessStore()
    access.grant(
        WorkspaceAccess(workspace_id=WORKSPACE_A, name="workspace A", role=Role.OWNER), OWNER_OF_A
    )
    app.state.workspace_access_service = WorkspaceAccessService(access)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(_settings(), checks=[])
    _wire_in_memory(app)
    with TestClient(app, base_url="https://testserver") as built:
        yield built


@pytest.fixture
async def intruder_csrf(client: TestClient) -> str:
    """Sign the intruder in with a session that names workspace A."""
    service: SessionService = client.app.state.session_service  # type: ignore[attr-defined]
    session = await service.create(
        subject="intruder-sub",
        email="intruder@example.com",
        user_id=INTRUDER,
        workspace_id=WORKSPACE_A,
    )
    client.cookies.set(SESSION_COOKIE, session.id)
    return session.csrf_token


# --- the harness --------------------------------------------------------------


def test_the_document_has_routes_to_check(client: TestClient) -> None:
    # Guards against the harness passing because it found nothing.
    assert _documented_routes(client.app) - set(EXEMPT) != set()  # type: ignore[arg-type]


def test_no_stale_exemptions(client: TestClient) -> None:
    documented = _documented_routes(client.app)  # type: ignore[arg-type]
    assert set(EXEMPT) <= documented, f"exempt but gone: {sorted(set(EXEMPT) - documented)}"


async def test_every_route_refuses_a_non_member(client: TestClient, intruder_csrf: str) -> None:
    routes = _documented_routes(client.app) - set(EXEMPT)  # type: ignore[arg-type]
    assert _probe(client, routes, intruder_csrf) == []


async def test_the_harness_catches_an_unprotected_route(
    client: TestClient, intruder_csrf: str
) -> None:
    # Seed a route that reads the session but never checks membership. The
    # harness must notice, or it is not protecting anything.
    app: FastAPI = client.app  # type: ignore[assignment]

    @app.get("/api/v1/seeded-leak")
    async def _leak() -> dict[str, str]:
        return {"workspace": "A"}

    app.openapi_schema = None  # force the document to be rebuilt
    routes = _documented_routes(app) - set(EXEMPT)
    assert ("GET", "/api/v1/seeded-leak") in routes

    failures = _probe(client, routes, intruder_csrf)
    assert any("/api/v1/seeded-leak" in line for line in failures), failures
