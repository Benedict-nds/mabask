from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import default_data_dir, sqlite_url


def _settings_env_file() -> str | None:
    raw = os.environ.get("AETHERQORE_ENV_FILE", ".env")
    if not raw:
        return None
    return raw if Path(raw).is_file() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_name: str = "AetherQore POS"
    environment: str = "development"
    debug: bool = False
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    database_url: str = ""
    data_dir: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    frontend_url: str = "http://127.0.0.1:3000"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    backup_keep: int = 14

    ai_provider: str = ""
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_base_url: str = "https://api.openai.com/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_provider.strip() and self.ai_api_key.strip())

    @property
    def resolved_data_dir(self) -> Path:
        if self.data_dir.strip():
            return Path(self.data_dir).expanduser().resolve()
        return default_data_dir()

    @property
    def resolved_database_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        if self.environment == "test":
            return "sqlite://"
        if self.environment == "production":
            return sqlite_url(self.resolved_data_dir / "data" / "aetherqore.db")
        return "postgresql+psycopg2://aetherqore:aetherqore@localhost:5432/aetherqore"


WEAK_SECRETS = {"dev-only-change-me", "dev-secret-change-me", "change-me", "secret"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings(_env_file=_settings_env_file())
    if settings.environment == "production" and settings.secret_key in WEAK_SECRETS:
        raise RuntimeError("SECRET_KEY must be set to a strong value when ENVIRONMENT=production")
    return settings
