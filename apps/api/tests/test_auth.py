"""Tests for OIDC authentication (P0-050, spec §10, ADR 0004).

Covers the full hexagonal stack: domain types, application service logic,
and the API routes with a mocked OIDC provider (no real Google calls).

Acceptance criteria:
  - Valid login succeeds
  - Bad state, bad nonce, wrong audience, expired token, unverified email,
    and non-allow-listed email are each rejected
"""

from __future__ import annotations

import base64
import hashlib
import urllib.parse
from dataclasses import dataclass
from datetime import timedelta

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from creatoriqx_api.main import create_app
from creatoriqx_api.modules.identity.application.auth_service import AuthService, LoginFlowState
from creatoriqx_api.modules.identity.application.session_service import SessionService
from creatoriqx_api.modules.identity.domain.auth import (
    OIDCProviderError,
    OIDCTokenValidationError,
    OIDCUserInfo,
)
from creatoriqx_api.modules.identity.domain.errors import (
    AuthenticationError,
    EmailNotAllowedError,
    OIDCStateMismatchError,
)
from creatoriqx_api.modules.identity.domain.session import SessionPolicy
from creatoriqx_api.modules.identity.infrastructure.key_value_store import InMemoryKeyValueStore
from creatoriqx_api.modules.workspaces.application.bootstrap_service import (
    WorkspaceBootstrapService,
)
from creatoriqx_api.modules.workspaces.infrastructure.memory_store import (
    InMemoryPersonalWorkspaceStore,
)
from creatoriqx_api.platform.health import HealthCheck
from creatoriqx_api.settings import Settings

_TEST_POLICY = SessionPolicy(
    idle_timeout=timedelta(minutes=30), absolute_timeout=timedelta(hours=12)
)

# ---------------------------------------------------------------------------
# Fake OIDC provider for unit tests
# ---------------------------------------------------------------------------


@dataclass
class FakeOIDCProvider:
    """In-memory OIDC provider that satisfies the OIDCProvider protocol.

    Configurable to return a specific user or raise specific errors.
    """

    user: OIDCUserInfo | None = None
    exchange_error: Exception | None = None
    validate_error: Exception | None = None
    # Record calls for assertion.
    last_code: str | None = None
    last_nonce: str | None = None

    def build_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_verifier: str,
    ) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, object]:
        self.last_code = code
        if self.exchange_error:
            raise self.exchange_error
        return {"id_token": "fake.jwt.token", "access_token": "fake_access"}

    async def validate_id_token(
        self,
        token_response: dict[str, object],
        nonce: str,
    ) -> OIDCUserInfo:
        self.last_nonce = nonce
        if self.validate_error:
            raise self.validate_error
        if self.user is None:
            raise OIDCTokenValidationError("No user configured in fake provider")
        return self.user


VALID_USER = OIDCUserInfo(
    subject="google-uid-123",
    email="creator@example.com",
    name="Test Creator",
    picture="https://example.com/photo.jpg",
)


# ---------------------------------------------------------------------------
# Domain type tests
# ---------------------------------------------------------------------------


class TestOIDCUserInfo:
    def test_frozen_and_immutable(self) -> None:
        user = OIDCUserInfo(subject="s", email="e@e.com")
        with pytest.raises(AttributeError):
            user.email = "other@e.com"  # type: ignore[misc]

    def test_optional_fields_default_to_none(self) -> None:
        user = OIDCUserInfo(subject="s", email="e@e.com")
        assert user.name is None
        assert user.picture is None


class TestOIDCTokenValidationError:
    def test_carries_reason(self) -> None:
        exc = OIDCTokenValidationError("Nonce mismatch")
        assert exc.reason == "Nonce mismatch"
        assert "Nonce mismatch" in str(exc)


# ---------------------------------------------------------------------------
# AuthService unit tests (application layer)
# ---------------------------------------------------------------------------


class TestAuthServiceStartLogin:
    def test_returns_url_and_flow_state(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        service = AuthService(provider, allowed_emails=frozenset())
        url, flow = service.start_login("http://localhost/callback")

        assert "accounts.google.com" in url
        assert len(flow.state) > 20
        assert len(flow.nonce) > 20
        assert len(flow.code_verifier) > 40
        assert flow.redirect_uri == "http://localhost/callback"

    def test_each_login_generates_unique_state(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        service = AuthService(provider, allowed_emails=frozenset())
        _, flow1 = service.start_login("http://localhost/callback")
        _, flow2 = service.start_login("http://localhost/callback")
        assert flow1.state != flow2.state
        assert flow1.nonce != flow2.nonce
        assert flow1.code_verifier != flow2.code_verifier


class TestAuthServiceCompleteLogin:
    @pytest.fixture
    def provider(self) -> FakeOIDCProvider:
        return FakeOIDCProvider(user=VALID_USER)

    @pytest.fixture
    def flow(self) -> LoginFlowState:
        return LoginFlowState(
            state="test-state-abc",
            nonce="test-nonce-xyz",
            code_verifier="test-verifier",
            redirect_uri="http://localhost/callback",
        )

    async def test_valid_login_succeeds(
        self, provider: FakeOIDCProvider, flow: LoginFlowState
    ) -> None:
        service = AuthService(provider, allowed_emails=frozenset())
        user = await service.complete_login(
            code="auth-code-123",
            callback_state="test-state-abc",
            flow_state=flow,
        )
        assert user.email == "creator@example.com"
        assert user.subject == "google-uid-123"

    async def test_bad_state_is_rejected(
        self, provider: FakeOIDCProvider, flow: LoginFlowState
    ) -> None:
        service = AuthService(provider, allowed_emails=frozenset())
        with pytest.raises(OIDCStateMismatchError, match="State parameter mismatch"):
            await service.complete_login(
                code="auth-code-123",
                callback_state="WRONG-STATE",
                flow_state=flow,
            )

    async def test_exchange_failure_raises_auth_error(self, flow: LoginFlowState) -> None:
        provider = FakeOIDCProvider(
            exchange_error=OIDCProviderError("Token endpoint error"),
        )
        service = AuthService(provider, allowed_emails=frozenset())
        with pytest.raises(AuthenticationError, match="Token exchange failed"):
            await service.complete_login(
                code="auth-code-123",
                callback_state="test-state-abc",
                flow_state=flow,
            )

    async def test_bad_nonce_is_rejected(self, flow: LoginFlowState) -> None:
        provider = FakeOIDCProvider(
            validate_error=OIDCTokenValidationError("Nonce mismatch"),
        )
        service = AuthService(provider, allowed_emails=frozenset())
        with pytest.raises(AuthenticationError, match="Nonce mismatch"):
            await service.complete_login(
                code="auth-code-123",
                callback_state="test-state-abc",
                flow_state=flow,
            )

    async def test_wrong_audience_is_rejected(self, flow: LoginFlowState) -> None:
        provider = FakeOIDCProvider(
            validate_error=OIDCTokenValidationError("ID token audience mismatch"),
        )
        service = AuthService(provider, allowed_emails=frozenset())
        with pytest.raises(AuthenticationError, match="audience mismatch"):
            await service.complete_login(
                code="auth-code-123",
                callback_state="test-state-abc",
                flow_state=flow,
            )

    async def test_expired_token_is_rejected(self, flow: LoginFlowState) -> None:
        provider = FakeOIDCProvider(
            validate_error=OIDCTokenValidationError("ID token has expired"),
        )
        service = AuthService(provider, allowed_emails=frozenset())
        with pytest.raises(AuthenticationError, match="expired"):
            await service.complete_login(
                code="auth-code-123",
                callback_state="test-state-abc",
                flow_state=flow,
            )

    async def test_unverified_email_is_rejected(self, flow: LoginFlowState) -> None:
        provider = FakeOIDCProvider(
            validate_error=OIDCTokenValidationError("Email not verified by Google"),
        )
        service = AuthService(provider, allowed_emails=frozenset())
        with pytest.raises(AuthenticationError, match="Email not verified"):
            await service.complete_login(
                code="auth-code-123",
                callback_state="test-state-abc",
                flow_state=flow,
            )

    async def test_non_allowlisted_email_is_rejected(
        self, provider: FakeOIDCProvider, flow: LoginFlowState
    ) -> None:
        service = AuthService(
            provider,
            allowed_emails=frozenset({"allowed@example.com"}),
        )
        with pytest.raises(EmailNotAllowedError, match="not on the allow-list"):
            await service.complete_login(
                code="auth-code-123",
                callback_state="test-state-abc",
                flow_state=flow,
            )

    async def test_allowlisted_email_is_case_insensitive(
        self, provider: FakeOIDCProvider, flow: LoginFlowState
    ) -> None:
        service = AuthService(
            provider,
            allowed_emails=frozenset({"Creator@Example.COM"}),
        )
        user = await service.complete_login(
            code="auth-code-123",
            callback_state="test-state-abc",
            flow_state=flow,
        )
        assert user.email == "creator@example.com"

    async def test_empty_allow_list_permits_any_email(
        self, provider: FakeOIDCProvider, flow: LoginFlowState
    ) -> None:
        service = AuthService(provider, allowed_emails=frozenset())
        user = await service.complete_login(
            code="auth-code-123",
            callback_state="test-state-abc",
            flow_state=flow,
        )
        assert user.email == "creator@example.com"


class TestCodeChallenge:
    def test_s256_challenge_matches_rfc7636(self) -> None:
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert AuthService.generate_code_challenge(verifier) == expected


# ---------------------------------------------------------------------------
# API route integration tests (with mocked provider)
# ---------------------------------------------------------------------------


def _make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_app_url": SecretStr("postgresql+asyncpg://u:p@localhost:1/db"),
        "redis_url": SecretStr("redis://localhost:1/0"),
        "oidc_client_id": "test-client-id",
        "oidc_client_secret": SecretStr("test-client-secret"),
        "readiness_timeout_seconds": 0.2,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _make_client(
    provider: FakeOIDCProvider,
    allowed_emails: frozenset[str] | None = None,
) -> TestClient:
    """Build a test client with a fake OIDC provider injected."""
    emails_csv = ",".join(allowed_emails) if allowed_emails else ""
    settings = _make_settings(auth_allowed_emails=emails_csv)
    checks: list[HealthCheck] = []
    app = create_app(settings, checks=checks)
    # In-memory sessions and login flows: no Redis needed for route tests.
    store = InMemoryKeyValueStore()
    app.state.key_value_store = store
    app.state.session_service = SessionService(store, _TEST_POLICY)
    # Bootstrap in memory: the route tests need no Postgres (P0-053).
    app.state.bootstrap_service = WorkspaceBootstrapService(InMemoryPersonalWorkspaceStore())
    # Override the auth service with our fake provider.
    app.state.auth_service = AuthService(
        provider=provider,
        allowed_emails=frozenset(e.strip().lower() for e in emails_csv.split(",") if e.strip())
        if emails_csv
        else frozenset(),
    )
    # Secure cookies only travel over HTTPS, so the test client uses an HTTPS origin.
    return TestClient(app, base_url="https://testserver")


class TestLoginRoute:
    def test_login_redirects_to_google(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        client = _make_client(provider)
        response = client.get("/api/v1/auth/login", follow_redirects=False)
        assert response.status_code == 302
        assert "accounts.google.com" in response.headers["location"]

    def test_login_stores_flow_state_in_session(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        client = _make_client(provider)
        response = client.get("/api/v1/auth/login", follow_redirects=False)
        assert response.status_code == 302
        # The login flow is bound to the browser by a single-use cookie.
        assert "creatoriqx_oidc_flow" in response.cookies


class TestCallbackRoute:
    def _do_login_and_callback(
        self,
        provider: FakeOIDCProvider,
        allowed_emails: frozenset[str] | None = None,
        callback_state: str | None = None,
        code: str = "auth-code-123",
        include_code: bool = True,
        include_state: bool = True,
        error: str | None = None,
    ) -> httpx2.Response:
        """Helper: perform a login, then hit the callback with the stored state."""
        client = _make_client(provider, allowed_emails=allowed_emails)
        # Step 1: Hit /login to generate flow state in the session.
        login_response = client.get("/api/v1/auth/login", follow_redirects=False)
        assert login_response.status_code == 302

        # Extract the state from the redirect URL (our fake puts it in the query).
        redirect_url = login_response.headers["location"]
        parsed = urllib.parse.urlparse(redirect_url)
        query_params = urllib.parse.parse_qs(parsed.query)
        session_state = query_params["state"][0]

        # Step 2: Hit /callback with the state from the session.
        params: dict[str, str] = {}
        if include_code:
            params["code"] = code
        if include_state:
            params["state"] = callback_state or session_state
        if error:
            params["error"] = error
        return client.get("/api/v1/auth/callback", params=params, follow_redirects=False)

    def test_valid_callback_redirects_to_app_with_session_cookie(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        response = self._do_login_and_callback(provider)
        assert response.status_code == 303
        assert response.headers["location"] == "http://localhost:3000/"
        # Session cookie: __Host- prefix, Secure, HttpOnly, SameSite=Lax, Path=/.
        set_cookie = response.headers["set-cookie"]
        assert "__Host-creatoriqx_session=" in set_cookie
        assert "Secure" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "Path=/" in set_cookie
        # The single-use flow cookie is cleared in the same response.
        assert "creatoriqx_oidc_flow=" in set_cookie
        assert "Max-Age=0" in set_cookie

    def test_mismatched_state_returns_400(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        response = self._do_login_and_callback(provider, callback_state="WRONG-STATE")
        assert response.status_code == 400

    def test_missing_code_returns_401(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        response = self._do_login_and_callback(provider, include_code=False)
        assert response.status_code == 401

    def test_missing_state_returns_401(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        response = self._do_login_and_callback(provider, include_state=False)
        assert response.status_code == 401

    def test_google_error_returns_401(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        response = self._do_login_and_callback(provider, error="access_denied")
        assert response.status_code == 401

    def test_token_exchange_failure_returns_401(self) -> None:
        provider = FakeOIDCProvider(
            exchange_error=OIDCProviderError("Token endpoint returned 400"),
        )
        response = self._do_login_and_callback(provider)
        assert response.status_code == 401

    def test_expired_token_returns_401(self) -> None:
        provider = FakeOIDCProvider(
            validate_error=OIDCTokenValidationError("ID token has expired"),
        )
        response = self._do_login_and_callback(provider)
        assert response.status_code == 401

    def test_unverified_email_returns_401(self) -> None:
        provider = FakeOIDCProvider(
            validate_error=OIDCTokenValidationError("Email not verified by Google"),
        )
        response = self._do_login_and_callback(provider)
        assert response.status_code == 401

    def test_non_allowlisted_email_returns_403(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        response = self._do_login_and_callback(
            provider, allowed_emails=frozenset({"other@example.com"})
        )
        assert response.status_code == 403

    def test_callback_without_prior_login_returns_400(self) -> None:
        """Callback without a session (no prior /login call)."""
        provider = FakeOIDCProvider(user=VALID_USER)
        client = _make_client(provider)
        # Hit callback directly without going through /login first.
        response = client.get(
            "/api/v1/auth/callback",
            params={"code": "x", "state": "y"},
        )
        assert response.status_code == 400

    def test_responses_are_problem_json_on_error(self) -> None:
        provider = FakeOIDCProvider(user=VALID_USER)
        response = self._do_login_and_callback(provider, error="access_denied")
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert "type" in body
        assert "title" in body


class TestAuthRouterNotMountedWithoutClientId:
    """When oidc_client_id is empty, the auth routes should not be mounted."""

    def test_login_returns_404_without_oidc_config(self) -> None:
        settings = _make_settings(oidc_client_id="")
        app = create_app(settings, checks=[])
        client = TestClient(app)
        response = client.get("/api/v1/auth/login", follow_redirects=False)
        # Should be 404 or 405 since the route doesn't exist.
        assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Settings allow-list property tests
# ---------------------------------------------------------------------------


class TestAllowedEmailsSet:
    def test_empty_string_returns_empty_frozenset(self) -> None:
        settings = _make_settings(auth_allowed_emails="")
        assert settings.allowed_emails_set == frozenset()

    def test_parses_comma_separated_emails(self) -> None:
        settings = _make_settings(auth_allowed_emails="a@b.com, c@d.com")
        assert settings.allowed_emails_set == frozenset({"a@b.com", "c@d.com"})

    def test_lowercases_all_emails(self) -> None:
        settings = _make_settings(auth_allowed_emails="A@B.COM")
        assert settings.allowed_emails_set == frozenset({"a@b.com"})

    def test_strips_whitespace(self) -> None:
        settings = _make_settings(auth_allowed_emails="  a@b.com , c@d.com  ")
        assert settings.allowed_emails_set == frozenset({"a@b.com", "c@d.com"})
