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
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-at-least-32-chars")
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
    monkeypatch.delenv("SESSION_SECRET", raising=False)
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
