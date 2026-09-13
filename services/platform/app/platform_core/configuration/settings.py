"""
Base application settings, environment-driven via pydantic-settings.

Bounded contexts extend PlatformSettings (not replace it) for
context-specific config, e.g.:

    class BillingSettings(PlatformSettings):
        stripe_api_key: str

so every context inherits the same env-loading, validation, and profile
semantics rather than reimplementing config loading per context.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.platform_core.configuration.profiles import EnvironmentProfile

# The platform package root (services/platform/, where .env actually lives,
# alongside pyproject.toml and alembic/) — four levels up from this file:
# configuration/ -> platform_core/ -> app/ -> services/platform/.
# Resolved from this file's own location rather than a bare ".env", which
# pydantic-settings would otherwise resolve against the process's current
# working directory at import time — meaning it only worked when uvicorn
# happened to be launched from inside services/platform.
_PLATFORM_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PLATFORM_ROOT / ".env"


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: EnvironmentProfile = EnvironmentProfile.LOCAL
    service_name: str = "guilddesk-platform"

    database_url: PostgresDsn
    redis_url: RedisDsn
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    api_version: str = "v1"
    cors_allowed_origins: list[str] = Field(default_factory=list)
    web_app_base_url: AnyHttpUrl = "http://localhost:5173"
    jwt_signing_key: str = Field(
        min_length=32,
        validation_alias="GUILDDESK_SECRET_JWT_SIGNING_KEY",
    )
    token_hash_pepper: SecretStr = Field(
        min_length=32,
        validation_alias="GUILDDESK_SECRET_TOKEN_HASH_PEPPER",
    )
    field_encryption_key: SecretStr = Field(
        min_length=44,
        max_length=44,
        validation_alias="GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY",
    )

    smtp_host: str | None = None
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_address: str = "no-reply@guilddesk.local"
    smtp_from_name: str = "GuildDesk"
    smtp_use_ssl: bool = False
    smtp_start_tls: bool = False
    smtp_timeout_seconds: float = Field(default=10.0, gt=0)

    otel_exporter_endpoint: str | None = None

    @field_validator("smtp_host", "smtp_username", "smtp_password", mode="before")
    @classmethod
    def _empty_smtp_values_are_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("field_encryption_key")
    @classmethod
    def _field_encryption_key_must_be_fernet_compatible(cls, value: SecretStr) -> SecretStr:
        try:
            decoded = base64.b64decode(
                value.get_secret_value().encode(), altchars=b"-_", validate=True
            )
        except (binascii.Error, ValueError) as exc:
            raise ValueError("field encryption key must be a URL-safe base64 Fernet key") from exc
        if len(decoded) != 32:
            raise ValueError("field encryption key must decode to exactly 32 bytes")
        return value

    @model_validator(mode="after")
    def _validate_production_constraints(self) -> PlatformSettings:
        """Configuration Validation: fail fast at startup, not at first request."""
        if self.smtp_use_ssl and self.smtp_start_tls:
            raise ValueError("smtp_use_ssl and smtp_start_tls cannot both be enabled")
        if (self.smtp_username is None) != (self.smtp_password is None):
            raise ValueError("smtp_username and smtp_password must be configured together")
        if self.environment.is_production_like and not self.cors_allowed_origins:
            raise ValueError(
                "cors_allowed_origins must be explicitly set in staging/production"
            )
        if self.environment.is_production_like and not self.smtp_host:
            raise ValueError("smtp_host must be configured in staging/production")
        return self


@lru_cache
def get_settings() -> PlatformSettings:
    """Cached singleton — settings are read once per process, at startup."""
    return PlatformSettings()  # type: ignore[call-arg]  # populated from env
