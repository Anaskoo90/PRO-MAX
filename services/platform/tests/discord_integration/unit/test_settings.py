from __future__ import annotations

import pytest
from app.discord_integration.settings import DiscordIntegrationSettings

_FIELD_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _set_required_configuration(
    monkeypatch: pytest.MonkeyPatch, *, environment: str = "local"
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:password@localhost:5432/guilddesk",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", "a" * 32)
    monkeypatch.setenv("GUILDDESK_SECRET_TOKEN_HASH_PEPPER", "b" * 32)
    monkeypatch.setenv(
        "GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY", _FIELD_ENCRYPTION_KEY
    )
    if environment in {"staging", "production"}:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://app.example.com"]')
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("STORAGE_BACKEND", "s3")
        monkeypatch.setenv("S3_BUCKET", "guilddesk-files")


def test_local_discord_settings_keep_the_development_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch)

    settings = DiscordIntegrationSettings(_env_file=None)

    assert settings.discord_application_id == ""
    assert (
        settings.discord_bot_service_secret.get_secret_value()
        == "dev-only-change-me"
    )


def test_production_rejects_the_default_bot_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch, environment="production")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "123456")
    monkeypatch.delenv(
        "GUILDDESK_SECRET_DISCORD_BOT_SERVICE_SECRET", raising=False
    )

    with pytest.raises(
        ValueError, match="GUILDDESK_SECRET_DISCORD_BOT_SERVICE_SECRET"
    ):
        DiscordIntegrationSettings(_env_file=None)


def test_production_requires_the_discord_application_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch, environment="production")
    monkeypatch.setenv(
        "GUILDDESK_SECRET_DISCORD_BOT_SERVICE_SECRET", "c" * 32
    )
    monkeypatch.delenv("DISCORD_APPLICATION_ID", raising=False)

    with pytest.raises(ValueError, match="discord_application_id"):
        DiscordIntegrationSettings(_env_file=None)


def test_production_accepts_strong_discord_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch, environment="production")
    monkeypatch.setenv("DISCORD_APPLICATION_ID", "123456")
    monkeypatch.setenv(
        "GUILDDESK_SECRET_DISCORD_BOT_SERVICE_SECRET", "c" * 32
    )

    settings = DiscordIntegrationSettings(_env_file=None)

    assert settings.discord_application_id == "123456"
    assert settings.discord_bot_service_secret.get_secret_value() == "c" * 32
