"""Readiness against the real local services (P0-030). Needs ``py scripts/dev.py up``."""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.settings import Settings

pytestmark = pytest.mark.integration

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _settings(**overrides: str) -> Settings:
    values = dotenv_values(ENV_FILE)
    if not values.get("DATABASE_APP_URL"):
        pytest.fail(".env is missing or incomplete. Run: py scripts/dev.py setup")
    values.update(overrides)
    return Settings(
        database_app_url=SecretStr(str(values["DATABASE_APP_URL"])),
        redis_url=SecretStr(str(values["REDIS_URL"])),
        session_secret=SecretStr(str(values["SESSION_SECRET"])),
    )


def test_ready_when_postgres_and_redis_answer() -> None:
    response = TestClient(create_app(_settings())).get("/readyz")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"postgres": "ok", "redis": "ok"}


def test_not_ready_when_postgres_is_unreachable() -> None:
    # Port 1 refuses connections: equivalent to Postgres being stopped.
    dead = "postgresql+asyncpg://creatoriqx_app:x@127.0.0.1:1/creatoriqx"
    response = TestClient(create_app(_settings(DATABASE_APP_URL=dead))).get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "unavailable", "redis": "ok"}
