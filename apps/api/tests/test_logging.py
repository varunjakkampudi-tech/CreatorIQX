"""Tests for structured logging, redaction, and the correlation middleware."""

from __future__ import annotations

import pytest
import structlog
from fastapi.testclient import TestClient
from pydantic import SecretStr
from structlog.testing import capture_logs

from creatoriqx_api.main import create_app
from creatoriqx_api.platform.logging import REDACTED, _redact
from creatoriqx_api.settings import Settings

TOKEN = "super-secret-token-value-123"


def _client() -> TestClient:
    settings = Settings(
        database_app_url=SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        redis_url=SecretStr("redis://localhost:1/0"),
    )
    return TestClient(create_app(settings, checks=[]))


def test_redact_masks_sensitive_keys() -> None:
    event = _redact(None, "", {"authorization": "Bearer x", "x_api_key": "k", "msg": "hi"})
    assert event["authorization"] == REDACTED
    assert event["x_api_key"] == REDACTED
    assert event["msg"] == "hi"


def test_redact_masks_bearer_tokens_in_free_text() -> None:
    event = _redact(None, "", {"event": f"got header Bearer {TOKEN} from client"})
    assert TOKEN not in event["event"]
    assert REDACTED in event["event"]


def test_request_log_never_contains_header_values() -> None:
    client = _client()
    with capture_logs() as logs:
        client.get("/healthz", headers={"Authorization": f"Bearer {TOKEN}"})
    assert any(e.get("event") == "request" for e in logs)
    assert not any(TOKEN in str(value) for entry in logs for value in entry.values())


def test_correlation_id_is_returned_in_the_response() -> None:
    response = _client().get("/healthz")
    assert response.headers["x-request-id"]


def test_supplied_correlation_id_is_echoed() -> None:
    response = _client().get("/healthz", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["x-request-id"] == "trace-abc-123"


@pytest.mark.parametrize("bad_id", ["x" * 500, "has\nnewline"])
def test_unsafe_incoming_id_is_replaced(bad_id: str) -> None:
    response = _client().get("/healthz", headers={"X-Request-ID": bad_id})
    returned = response.headers["x-request-id"]
    assert returned != bad_id
    assert len(returned) == 32  # a generated uuid4 hex


def test_each_request_gets_a_distinct_id() -> None:
    client = _client()
    first = client.get("/healthz").headers["x-request-id"]
    second = client.get("/healthz").headers["x-request-id"]
    assert first != second


@pytest.fixture(autouse=True)
def _reset_contextvars() -> None:
    structlog.contextvars.clear_contextvars()
