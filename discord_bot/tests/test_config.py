from __future__ import annotations

import pytest
from pydantic import ValidationError

from discord_bot.config import DiscordBotSettings


def _settings(**overrides) -> DiscordBotSettings:
    values = {
        "environment": "local",
        "discord_bot_token": "local-token",
        "discord_application_id": 0,
        "api_url": "http://127.0.0.1:8000",
        "platform_service_secret": "dev-only-change-me",
    }
    values.update(overrides)
    return DiscordBotSettings(_env_file=None, **values)


def test_local_profile_keeps_development_defaults() -> None:
    settings = _settings()

    assert settings.environment == "local"
    assert settings.platform_service_secret == "dev-only-change-me"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_production_like_profiles_reject_the_default_service_secret(environment: str) -> None:
    with pytest.raises(ValidationError, match="platform_service_secret"):
        _settings(
            environment=environment,
            discord_bot_token="t" * 64,
            discord_application_id=123456,
            api_url="https://api.example.com",
        )


def test_production_rejects_a_placeholder_bot_token() -> None:
    with pytest.raises(ValidationError, match="discord_bot_token"):
        _settings(
            environment="production",
            discord_bot_token="your-bot-token-here",
            discord_application_id=123456,
            api_url="https://api.example.com",
            platform_service_secret="s" * 32,
        )


@pytest.mark.parametrize(
    "api_url",
    ["http://api.example.com", "https://user:password@api.example.com"],
)
def test_production_rejects_an_insecure_api_url(api_url: str) -> None:
    with pytest.raises(ValidationError, match="api_url"):
        _settings(
            environment="production",
            discord_bot_token="t" * 64,
            discord_application_id=123456,
            api_url=api_url,
            platform_service_secret="s" * 32,
        )


def test_production_accepts_strong_secure_configuration() -> None:
    settings = _settings(
        environment="production",
        discord_bot_token="t" * 64,
        discord_application_id=123456,
        api_url="https://api.example.com",
        platform_service_secret="s" * 32,
    )

    assert settings.environment == "production"
