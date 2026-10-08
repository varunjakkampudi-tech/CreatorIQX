"""Tests for the app factory and the health, readiness and metrics endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app, default_checks
from creatoriqx_api.platform.health import HealthCheck, PostgresCheck, RedisCheck
from creatoriqx_api.settings import Settings


class FakeCheck:
    def __init__(self, name: str, *, fails: bool = False, delay: float = 0.0) -> None:
        self.name = name
        self._fails = fails
        self._delay = delay

    async def check(self) -> None:
        await asyncio.sleep(self._delay)
        if self._fails:
            raise ConnectionError("postgresql://user:leaked-password@host/db refused")


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_app_url": SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        "redis_url": SecretStr("redis://localhost:1/0"),
        "session_secret": SecretStr("test-session-secret-at-least-32-chars"),
        "readiness_timeout_seconds": 0.2,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def client_with(checks: Sequence[HealthCheck], **overrides: object) -> TestClient:
    return TestClient(create_app(make_settings(**overrides), checks=checks))


def test_healthz_reports_alive_without_touching_dependencies() -> None:
    response = client_with([FakeCheck("postgres", fails=True)]).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["cache-control"] == "no-store"


def test_readyz_is_200_when_all_checks_pass() -> None:
    response = client_with([FakeCheck("postgres"), FakeCheck("redis")]).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}


def test_readyz_is_503_and_names_the_failing_dependency() -> None:
    response = client_with([FakeCheck("postgres", fails=True), FakeCheck("redis")]).get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "unavailable", "redis": "ok"}


def test_readyz_never_leaks_error_details() -> None:
    response = client_with([FakeCheck("postgres", fails=True)]).get("/readyz")
    assert "leaked-password" not in response.text


def test_slow_dependency_times_out_as_unavailable() -> None:
    response = client_with([FakeCheck("postgres", delay=2.0)]).get("/readyz")
    assert response.status_code == 503


def test_metrics_endpoint_serves_prometheus_text() -> None:
    response = client_with([]).get("/metrics/")
    assert response.status_code == 200
    assert "python_info" in response.text


def test_openapi_is_versioned_and_titled_with_product_name() -> None:
    schema = client_with([]).get("/api/v1/openapi.json").json()
    assert schema["info"]["title"] == "CreatorIQX API"


@pytest.mark.parametrize(("env", "docs_status"), [("local", 200), ("production", 404)])
def test_interactive_docs_are_disabled_in_production(env: str, docs_status: int) -> None:
    assert client_with([], app_env=env).get("/api/v1/docs").status_code == docs_status


def test_default_checks_cover_postgres_and_redis() -> None:
    checks = default_checks(make_settings())
    assert [type(c) for c in checks] == [PostgresCheck, RedisCheck]
    assert [c.name for c in checks] == ["postgres", "redis"]
