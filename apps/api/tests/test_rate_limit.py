"""Tests for the token-bucket rate limiter (P0-055, spec §6, §10).

Covers the pure bucket math (``InMemoryTokenBucketLimiter``, injectable
clock) and the route-level behavior: a burst beyond the configured capacity
on ``/auth/login`` returns 429 problem+json with a ``Retry-After`` header,
and two different client IPs each get their own bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.requests import Request as StarletteRequest

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.identity.api.dependencies import enforce_auth_rate_limit
from creatoriqx_api.modules.identity.application.auth_service import AuthService
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.auth import OIDCUserInfo
from creatoriqx_api.modules.identity.domain.errors import RateLimitExceededError
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
    WorkspaceBootstrapService,
)
from creatoriqx_api.modules.workspaces.infrastructure.memory_store import (
    InMemoryPersonalWorkspaceStore,
)
from creatoriqx_api.platform.rate_limit import InMemoryTokenBucketLimiter
from creatoriqx_api.settings import Settings

_TEST_POLICY = SessionPolicy(
    idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12)
)


# ---------------------------------------------------------------------------
# Pure bucket math (InMemoryTokenBucketLimiter), no FastAPI involved
# ---------------------------------------------------------------------------


class _FakeClock:
    """A controllable monotonic clock: advances only when told to."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class TestInMemoryTokenBucketLimiter:
    async def test_allows_up_to_capacity_then_blocks(self) -> None:
        clock = _FakeClock()
        limiter = InMemoryTokenBucketLimiter(clock=clock)

        for _ in range(3):
            result = await limiter.check("k", capacity=3, refill_per_second=1.0)
            assert result.allowed is True

        blocked = await limiter.check("k", capacity=3, refill_per_second=1.0)
        assert blocked.allowed is False
        assert blocked.retry_after_seconds >= 1

    async def test_refills_over_time(self) -> None:
        clock = _FakeClock()
        limiter = InMemoryTokenBucketLimiter(clock=clock)

        for _ in range(2):
            assert (await limiter.check("k", capacity=2, refill_per_second=1.0)).allowed is True
        assert (await limiter.check("k", capacity=2, refill_per_second=1.0)).allowed is False

        clock.now += 1.0  # one token refills
        result = await limiter.check("k", capacity=2, refill_per_second=1.0)
        assert result.allowed is True

    async def test_refill_never_exceeds_capacity(self) -> None:
        clock = _FakeClock()
        limiter = InMemoryTokenBucketLimiter(clock=clock)
        await limiter.check("k", capacity=2, refill_per_second=1.0)  # spend 1, 1 left

        clock.now += 1000.0  # far more than enough to "overfill"
        # Still only 2 tokens available (capacity), not unbounded.
        assert (await limiter.check("k", capacity=2, refill_per_second=1.0)).allowed is True
        assert (await limiter.check("k", capacity=2, refill_per_second=1.0)).allowed is True
        assert (await limiter.check("k", capacity=2, refill_per_second=1.0)).allowed is False

    async def test_independent_keys_have_independent_buckets(self) -> None:
        clock = _FakeClock()
        limiter = InMemoryTokenBucketLimiter(clock=clock)
        await limiter.check("a", capacity=1, refill_per_second=1.0)
        blocked_a = await limiter.check("a", capacity=1, refill_per_second=1.0)
        allowed_b = await limiter.check("b", capacity=1, refill_per_second=1.0)

        assert blocked_a.allowed is False
        assert allowed_b.allowed is True


# ---------------------------------------------------------------------------
# Route-level: /auth/login burst -> 429 problem+json, per-IP isolation
# ---------------------------------------------------------------------------


@dataclass
class _FakeOIDCProvider:
    user: OIDCUserInfo | None = None

    def build_authorization_url(
        self, redirect_uri: str, state: str, nonce: str, code_verifier: str
    ) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str
    ) -> dict[str, object]:
        raise AssertionError("not needed for login-route rate-limit tests")

    async def validate_id_token(
        self, token_response: dict[str, object], nonce: str
    ) -> OIDCUserInfo:
        raise AssertionError("not needed for login-route rate-limit tests")


def _make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_app_url": SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        "redis_url": SecretStr("redis://localhost:1/0"),
        "oidc_client_id": "test-client-id",
        "oidc_client_secret": SecretStr("test-client-secret"),
        "readiness_timeout_seconds": 0.2,
        "auth_rate_limit_capacity": 2,
        "auth_rate_limit_window_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _make_client(**setting_overrides: object) -> TestClient:
    settings = _make_settings(**setting_overrides)
    app = create_app(settings, checks=[])
    store = InMemoryKeyValueStore()
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, _TEST_POLICY)
    app.state.bootstrap_service = WorkspaceBootstrapService(InMemoryPersonalWorkspaceStore())
    app.state.auth_service = AuthService(
        provider=_FakeOIDCProvider(user=None), allowed_emails=frozenset()
    )
    app.state.rate_limiter = InMemoryTokenBucketLimiter()
    return TestClient(app, base_url="https://testserver")


class TestAuthRateLimit:
    def test_burst_beyond_capacity_returns_429_problem_json(self) -> None:
        client = _make_client()  # capacity=2

        for _ in range(2):
            response = client.get("/api/v1/auth/login", follow_redirects=False)
            assert response.status_code == 302

        blocked = client.get("/api/v1/auth/login", follow_redirects=False)
        assert blocked.status_code == 429
        assert blocked.headers["content-type"] == "application/problem+json"
        assert "Retry-After" in blocked.headers
        body = blocked.json()
        assert body["status"] == 429
        assert body["type"] == "/problems/rate-limited"


# ---------------------------------------------------------------------------
# enforce_auth_rate_limit dependency: per-IP keying, directly
# ---------------------------------------------------------------------------


def _fake_request(app: object, client_host: str) -> StarletteRequest:
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "client": (client_host, 12345),
        "method": "GET",
        "path": "/api/v1/auth/login",
    }
    return StarletteRequest(scope)


class TestEnforceAuthRateLimitDependency:
    async def test_two_client_ips_get_independent_buckets(self) -> None:
        app = create_app(_make_settings(), checks=[])
        app.state.rate_limiter = InMemoryTokenBucketLimiter()

        limiter = app.state.rate_limiter
        for _ in range(2):
            await enforce_auth_rate_limit(_fake_request(app, "1.1.1.1"), limiter)
            await enforce_auth_rate_limit(_fake_request(app, "2.2.2.2"), limiter)

        # Both IPs are now at capacity (2 each) but neither has touched the
        # other's bucket.
        with pytest.raises(RateLimitExceededError):
            await enforce_auth_rate_limit(_fake_request(app, "1.1.1.1"), limiter)
        with pytest.raises(RateLimitExceededError):
            await enforce_auth_rate_limit(_fake_request(app, "2.2.2.2"), limiter)
