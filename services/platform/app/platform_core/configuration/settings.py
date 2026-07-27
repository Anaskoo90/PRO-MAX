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

from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.platform_core.configuration.profiles import EnvironmentProfile


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    otel_exporter_endpoint: str | None = None

    @model_validator(mode="after")
    def _validate_production_constraints(self) -> "PlatformSettings":
        """Configuration Validation: fail fast at startup, not at first request."""
        if self.environment.is_production_like and not self.cors_allowed_origins:
            raise ValueError(
                "cors_allowed_origins must be explicitly set in staging/production"
            )
        return self


@lru_cache
def get_settings() -> PlatformSettings:
    """Cached singleton — settings are read once per process, at startup."""
    return PlatformSettings()  # type: ignore[call-arg]  # populated from env
