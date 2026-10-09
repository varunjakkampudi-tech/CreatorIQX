"""Application settings, read from environment variables only (spec A14).

Secrets are ``SecretStr`` so they never appear in logs, reprs or error output.
Local development loads ``.env`` through the process runner (for example
``uvicorn --env-file .env``), never from inside the application.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository layout: apps/api/src/creatoriqx_api/settings.py -> repo root is parents[4].
_DEFAULT_PRODUCT_CONFIG = (
    Path(__file__).resolve().parents[4] / "packages" / "config" / "product.json"
)

AppEnv = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """Validated runtime configuration. Unknown variables are ignored."""

    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", frozen=True, populate_by_name=True
    )

    app_env: AppEnv = "local"
    log_level: LogLevel = "INFO"
    database_app_url: SecretStr = Field(description="Runtime role DSN (ADR 0002)")
    redis_url: SecretStr = Field(description="Redis DSN (sessions, login flows, quota)")
    app_base_url: str = Field(
        default="http://localhost:3000",
        description="Browser origin; the only allowed CORS origin and the post-login redirect",
    )
    max_request_body_bytes: int = Field(
        default=1_000_000, gt=0, description="Reject larger request bodies with 413"
    )
    product_config_path: Path = _DEFAULT_PRODUCT_CONFIG
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=10)

    # OIDC login (ADR 0004): login-only client, identity scopes only. The
    # validation_alias matches .env.example's GOOGLE_LOGIN_CLIENT_ID/SECRET
    # (pydantic-settings would otherwise look for the bare field names,
    # OIDC_CLIENT_ID/SECRET, so .env's values were silently never read -
    # found while writing the P0-022 quickstart). populate_by_name=True above
    # keeps the field name itself usable too, for Settings(oidc_client_id=...)
    # in tests and other direct construction.
    oidc_client_id: str = Field(
        default="",
        validation_alias="GOOGLE_LOGIN_CLIENT_ID",
        description="Google OAuth client ID for login",
    )
    oidc_client_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="GOOGLE_LOGIN_CLIENT_SECRET",
        description="Google OAuth client secret for login",
    )
    auth_allowed_emails: str = Field(
        default="",
        description=(
            "Comma-separated email allow-list for login. "
            "Empty means no restriction (not recommended for production)"
        ),
    )
    oidc_flow_ttl_seconds: int = Field(
        default=600, ge=60, le=900, description="How long a started login may take to finish"
    )

    # Server-side sessions (ADR 0010).
    session_idle_timeout_minutes: int = Field(
        default=60, ge=5, le=1440, description="Sign out after this long without activity"
    )
    session_absolute_timeout_hours: int = Field(
        default=12, ge=1, le=168, description="Sign out this long after login, regardless"
    )

    # Auth rate limiting (P0-055): a Redis token bucket per IP and, when a
    # session cookie is present, per session - applied to /auth/login and
    # /auth/callback. capacity is the burst size; window_seconds sets the
    # sustained refill rate (capacity / window_seconds tokens per second).
    auth_rate_limit_capacity: int = Field(
        default=10, ge=1, description="Burst size for the auth-endpoint token bucket"
    )
    auth_rate_limit_window_seconds: int = Field(
        default=60, gt=0, description="Window the bucket fully refills over"
    )

    @property
    def allowed_emails_set(self) -> frozenset[str]:
        """Parse the comma-separated allow-list into a frozen set."""
        if not self.auth_allowed_emails.strip():
            return frozenset()
        return frozenset(
            e.strip().lower() for e in self.auth_allowed_emails.split(",") if e.strip()
        )

    @property
    def product_name(self) -> str:
        """The configurable product name (single source: packages/config/product.json)."""
        data = json.loads(self.product_config_path.read_text(encoding="utf-8"))
        name = data.get("productName")
        if not isinstance(name, str) or not name:
            raise ValueError(f"productName missing in {self.product_config_path}")
        return name


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, loaded once from the environment."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
