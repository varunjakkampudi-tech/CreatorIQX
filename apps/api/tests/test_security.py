"""Tests for security headers, strict CORS, and the body-size limit (P0-032)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.settings import Settings

ALLOWED_ORIGIN = "http://localhost:3000"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_app_url": SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        "redis_url": SecretStr("redis://localhost:1/0"),
        "app_base_url": ALLOWED_ORIGIN,
        "max_request_body_bytes": 1000,
        "session_secret": SecretStr("test-session-secret-at-least-32-chars"),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _client(base_url: str = "http://testserver", **overrides: object) -> TestClient:
    return TestClient(create_app(_settings(**overrides), checks=[]), base_url=base_url)


def test_security_headers_present_on_every_response() -> None:
    headers = _client().get("/healthz").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in headers["content-security-policy"]


def test_hsts_absent_over_http() -> None:
    assert "strict-transport-security" not in _client("http://testserver").get("/healthz").headers


def test_hsts_present_over_https() -> None:
    headers = _client("https://testserver").get("/healthz").headers
    assert "max-age=" in headers["strict-transport-security"]


def test_allowed_origin_gets_cors_header() -> None:
    response = _client().get("/healthz", headers={"Origin": ALLOWED_ORIGIN})
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_foreign_origin_is_not_granted_cors() -> None:
    response = _client().get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_body_over_limit_is_rejected_by_content_length() -> None:
    response = _client().post("/healthz", content=b"x" * 2000)
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "/problems/request-too-large"


def test_body_within_limit_is_not_blocked_by_the_guard() -> None:
    # /healthz has no POST route, so passing the guard yields 405, not 413.
    response = _client().post("/healthz", content=b"x" * 100)
    assert response.status_code != 413


@pytest.mark.parametrize("scheme", ["http://testserver", "https://testserver"])
def test_request_id_header_still_present(scheme: str) -> None:
    assert _client(scheme).get("/healthz").headers["x-request-id"]
