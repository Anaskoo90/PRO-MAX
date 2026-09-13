"""
Bot configuration, read from environment variables / a local `.env` file
(never committed with real secrets — see .env.example for the template).

Mirrors the platform's own configuration approach (pydantic-settings), kept
independent: this bot has its own settings model rather than importing
services/platform's, since the two are meant to evolve and deploy
separately.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent / ".env"


class DiscordBotSettings(BaseSettings):
    # Absolute path, not a bare ".env": pydantic-settings resolves a
    # relative env_file against the process's current working directory,
    # which would silently do nothing if the bot is launched from anywhere
    # other than this package's own folder.
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    environment: Literal["local", "test", "staging", "production"] = "local"
    discord_bot_token: str = Field(min_length=1)
    discord_application_id: int
    discord_guild_id: int | None = None
    api_url: str = "http://127.0.0.1:8000"

    # Shared secret sent as X-GuildDesk-Bot-Secret on every call to the
    # backend's bot-facing Discord Integration endpoints — must match the
    # backend's DiscordIntegrationSettings.discord_bot_service_secret.
    # Defaulted to the same dev placeholder the backend defaults to, so a
    # fresh dev setup works out of the box; override both sides for a real
    # deployment.
    platform_service_secret: str = "dev-only-change-me"

    @model_validator(mode="after")
    def _validate_production_constraints(self) -> Self:
        if self.environment not in {"staging", "production"}:
            return self

        if self.discord_application_id <= 0:
            raise ValueError("discord_application_id must be configured in staging/production")
        if (
            self.discord_bot_token == "your-bot-token-here"
            or len(self.discord_bot_token.strip()) < 32
        ):
            raise ValueError(
                "discord_bot_token must contain at least 32 non-placeholder characters "
                "in staging/production"
            )
        if (
            self.platform_service_secret == "dev-only-change-me"
            or len(self.platform_service_secret.strip()) < 32
        ):
            raise ValueError(
                "platform_service_secret must contain at least 32 non-default characters "
                "in staging/production"
            )

        api_url = urlsplit(self.api_url)
        if api_url.scheme != "https" or not api_url.hostname:
            raise ValueError("api_url must use HTTPS in staging/production")
        if api_url.username or api_url.password:
            raise ValueError("api_url must not contain embedded credentials")
        return self


@lru_cache
def get_settings() -> DiscordBotSettings:
    return DiscordBotSettings()
