"""Application settings, read from environment variables only (spec §14).

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

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    app_env: AppEnv = "local"
    log_level: LogLevel = "INFO"
    database_app_url: SecretStr = Field(description="Runtime role DSN (ADR 0002)")
    redis_url: SecretStr = Field(description="Redis DSN")
    product_config_path: Path = _DEFAULT_PRODUCT_CONFIG
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=10)

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
