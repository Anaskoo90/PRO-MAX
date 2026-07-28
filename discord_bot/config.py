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

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent / ".env"


class DiscordBotSettings(BaseSettings):
    # Absolute path, not a bare ".env": pydantic-settings resolves a
    # relative env_file against the process's current working directory,
    # which would silently do nothing if the bot is launched from anywhere
    # other than this package's own folder.
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    discord_bot_token: str
    discord_application_id: int
    discord_guild_id: int | None = None
    api_url: str = "http://127.0.0.1:8000"


@lru_cache
def get_settings() -> DiscordBotSettings:
    return DiscordBotSettings()
