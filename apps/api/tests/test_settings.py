"""Tests for environment-driven settings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from creatoriqx_api.settings import Settings

DSN = "postgresql+asyncpg://creatoriqx_app:s3cret-pw@localhost:55432/creatoriqx"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("DATABASE_APP_URL", DSN)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:56379/0")
    return monkeypatch


@pytest.mark.usefixtures("env")
def test_loads_from_environment() -> None:
    settings = Settings()  # type: ignore[call-arg]
    assert settings.app_env == "local"
    assert settings.database_app_url.get_secret_value() == DSN


@pytest.mark.usefixtures("env")
def test_secrets_never_appear_in_repr_or_str() -> None:
    settings = Settings()  # type: ignore[call-arg]
    assert "s3cret-pw" not in repr(settings)
    assert "s3cret-pw" not in str(settings)


def test_missing_required_values_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_APP_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


@pytest.mark.usefixtures("env")
def test_session_timeouts_have_safe_defaults() -> None:
    settings = Settings()  # type: ignore[call-arg]
    assert settings.session_idle_timeout_minutes == 60
    assert settings.session_absolute_timeout_hours == 12


@pytest.mark.usefixtures("env")
@pytest.mark.parametrize(
    ("name", "value"),
    [("SESSION_IDLE_TIMEOUT_MINUTES", "0"), ("SESSION_ABSOLUTE_TIMEOUT_HOURS", "9999")],
)
def test_session_timeouts_are_bounded(env: pytest.MonkeyPatch, name: str, value: str) -> None:
    env.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_unknown_app_env_is_rejected(env: pytest.MonkeyPatch) -> None:
    env.setenv("APP_ENV", "prod-typo")
    with pytest.raises(ValidationError, match="app_env"):
        Settings()  # type: ignore[call-arg]


@pytest.mark.usefixtures("env")
def test_product_name_comes_from_shared_config() -> None:
    assert Settings().product_name == "CreatorIQX"  # type: ignore[call-arg]


def test_product_name_follows_config_file(env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "product.json"
    config.write_text(json.dumps({"productName": "RenamedProduct"}), encoding="utf-8")
    env.setenv("PRODUCT_CONFIG_PATH", str(config))
    assert Settings().product_name == "RenamedProduct"  # type: ignore[call-arg]


def test_product_config_without_name_is_an_error(env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "product.json"
    config.write_text("{}", encoding="utf-8")
    env.setenv("PRODUCT_CONFIG_PATH", str(config))
    with pytest.raises(ValueError, match="productName missing"):
        _ = Settings().product_name  # type: ignore[call-arg]


@pytest.mark.usefixtures("env")
def test_google_login_env_vars_populate_oidc_settings(env: pytest.MonkeyPatch) -> None:
    """.env.example names these GOOGLE_LOGIN_CLIENT_ID/SECRET (P0-022); the field names
    are oidc_client_id/secret, so without a validation_alias they were silently never
    read from the environment - found while writing the P0-022 quickstart."""
    env.setenv("GOOGLE_LOGIN_CLIENT_ID", "demo-client-id")
    env.setenv("GOOGLE_LOGIN_CLIENT_SECRET", "demo-client-secret")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.oidc_client_id == "demo-client-id"
    assert settings.oidc_client_secret.get_secret_value() == "demo-client-secret"


@pytest.mark.usefixtures("env")
def test_oidc_settings_still_constructible_by_field_name() -> None:
    """populate_by_name=True keeps direct kwarg construction working (test_auth.py,
    test_cross_tenant.py build Settings(oidc_client_id=..., ...) directly)."""
    settings = Settings(oidc_client_id="direct-kwarg-id")  # type: ignore[call-arg]
    assert settings.oidc_client_id == "direct-kwarg-id"
