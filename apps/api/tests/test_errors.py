"""Tests that errors become RFC 9457 problem+json without leaking internals."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from creatoriqx_api.platform.errors import PROBLEM_JSON, DomainError, install_error_handlers

SECRET_DETAIL = "connection string postgres://user:pw@host failed"


class WorkspaceNotFoundError(DomainError):
    status = 404
    title = "Workspace not found"
    code = "workspace-not-found"


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    class Body(BaseModel):
        count: int

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(SECRET_DETAIL)

    @app.get("/missing")
    async def missing() -> None:
        raise WorkspaceNotFoundError("no such workspace")

    @app.post("/validate")
    async def validate(_body: Body) -> dict[str, str]:
        return {"ok": "yes"}

    return app


def _client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


def test_domain_error_becomes_problem_json() -> None:
    response = _client().get("/missing")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["type"] == "/problems/workspace-not-found"
    assert body["title"] == "Workspace not found"
    assert body["status"] == 404
    assert body["detail"] == "no such workspace"


def test_unhandled_exception_is_500_without_leaking_detail() -> None:
    response = _client().get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json() == {
        "type": "/problems/internal-error",
        "title": "Internal server error",
        "status": 500,
    }
    assert SECRET_DETAIL not in response.text
    assert "Traceback" not in response.text


def test_validation_error_is_422_problem() -> None:
    response = _client().post("/validate", json={"count": "not-an-int"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["type"] == "/problems/validation-error"


def test_unknown_route_is_404_problem() -> None:
    response = _client().get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["type"] == "/problems/http-404"
