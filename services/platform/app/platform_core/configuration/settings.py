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
from typing import Literal

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

_INSECURE_JWT_SIGNING_KEYS = frozenset(
    {
        "local-compose-jwt-signing-key-change-me",
        "replace-with-at-least-32-random-characters",
    }
)
_INSECURE_TOKEN_PEPPERS = frozenset(
    {
        "local-compose-token-hash-pepper-change-me",
        "replace-with-at-least-32-random-characters",
    }
)
_INSECURE_FIELD_ENCRYPTION_KEYS = frozenset(
    {"MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="}
)


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
    rabbitmq_exchange: str = "guilddesk.events"
    rabbitmq_connection_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    outbox_relay_interval_seconds: float = Field(default=1.0, gt=0, le=300)
    outbox_relay_batch_size: int = Field(default=100, ge=1, le=1000)

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

    oauth_discord_client_id: str | None = None
    oauth_discord_client_secret: SecretStr | None = None
    oauth_discord_redirect_uri: AnyHttpUrl | None = None

    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: Path = Path("./.local-storage")
    s3_endpoint_url: AnyHttpUrl | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None

    ai_provider: Literal["disabled", "openai", "anthropic"] = "disabled"
    ai_fallback_provider: Literal["openai", "anthropic"] | None = None
    ai_openai_api_key: SecretStr | None = None
    ai_openai_base_url: AnyHttpUrl = "https://api.openai.com/v1"
    ai_openai_model: str = "gpt-4o-mini"
    ai_openai_embedding_model: str = "text-embedding-3-small"
    ai_openai_embedding_dimensions: int = Field(default=1536, gt=0)
    ai_anthropic_api_key: SecretStr | None = None
    ai_anthropic_base_url: AnyHttpUrl = "https://api.anthropic.com/v1"
    ai_anthropic_model: str = "claude-3-5-haiku-latest"
    ai_anthropic_version: str = "2023-06-01"
    ai_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    ai_max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    ai_requests_per_minute: int = Field(default=20, ge=1, le=1000)
    ai_max_prompt_characters: int = Field(default=50000, ge=1000, le=1000000)

    otel_exporter_endpoint: str | None = None

    @field_validator(
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "oauth_discord_client_id",
        "oauth_discord_client_secret",
        "oauth_discord_redirect_uri",
        "s3_endpoint_url",
        "s3_bucket",
        "s3_access_key",
        "s3_secret_key",
        "ai_fallback_provider",
        "ai_openai_api_key",
        "ai_anthropic_api_key",
        mode="before",
    )
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
        discord_oauth_values = (
            self.oauth_discord_client_id,
            self.oauth_discord_client_secret,
            self.oauth_discord_redirect_uri,
        )
        if any(value is not None for value in discord_oauth_values) and not all(
            value is not None for value in discord_oauth_values
        ):
            raise ValueError(
                "oauth_discord_client_id, oauth_discord_client_secret, and "
                "oauth_discord_redirect_uri must be configured together"
            )
        if (self.s3_access_key is None) != (self.s3_secret_key is None):
            raise ValueError("s3_access_key and s3_secret_key must be configured together")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("s3_bucket must be configured when storage_backend is 's3'")
        configured_ai_keys = {
            "openai": self.ai_openai_api_key,
            "anthropic": self.ai_anthropic_api_key,
        }
        if self.ai_provider != "disabled" and configured_ai_keys[self.ai_provider] is None:
            raise ValueError(
                f"ai_{self.ai_provider}_api_key must be configured when "
                f"ai_provider is '{self.ai_provider}'"
            )
        if self.ai_provider == "disabled" and self.ai_fallback_provider is not None:
            raise ValueError("ai_fallback_provider requires an enabled ai_provider")
        if self.ai_fallback_provider == self.ai_provider:
            raise ValueError("ai_fallback_provider must differ from ai_provider")
        if (
            self.ai_fallback_provider is not None
            and configured_ai_keys[self.ai_fallback_provider] is None
        ):
            raise ValueError(
                f"ai_{self.ai_fallback_provider}_api_key must be configured when "
                "that provider is selected as fallback"
            )
        if self.environment.is_production_like and not self.cors_allowed_origins:
            raise ValueError(
                "cors_allowed_origins must be explicitly set in staging/production"
            )
        if self.environment.is_production_like and not self.smtp_host:
            raise ValueError("smtp_host must be configured in staging/production")
        if self.environment.is_production_like and self.storage_backend != "s3":
            raise ValueError("storage_backend must be 's3' in staging/production")
        if self.environment.is_production_like:
            token_pepper = self.token_hash_pepper.get_secret_value()
            field_encryption_key = self.field_encryption_key.get_secret_value()
            if self.jwt_signing_key in _INSECURE_JWT_SIGNING_KEYS:
                raise ValueError(
                    "jwt_signing_key must not use a documented development placeholder "
                    "in staging/production"
                )
            if token_pepper in _INSECURE_TOKEN_PEPPERS:
                raise ValueError(
                    "token_hash_pepper must not use a documented development placeholder "
                    "in staging/production"
                )
            if field_encryption_key in _INSECURE_FIELD_ENCRYPTION_KEYS:
                raise ValueError(
                    "field_encryption_key must not use the documented development key "
                    "in staging/production"
                )
            if self.jwt_signing_key == token_pepper:
                raise ValueError(
                    "jwt_signing_key and token_hash_pepper must be independent secrets"
                )
            if self.web_app_base_url.scheme != "https":
                raise ValueError(
                    "web_app_base_url must use HTTPS in staging/production"
                )
            if any(not origin.startswith("https://") for origin in self.cors_allowed_origins):
                raise ValueError(
                    "cors_allowed_origins must contain only HTTPS origins in "
                    "staging/production"
                )
            if (
                self.oauth_discord_redirect_uri is not None
                and self.oauth_discord_redirect_uri.scheme != "https"
            ):
                raise ValueError(
                    "oauth_discord_redirect_uri must use HTTPS in staging/production"
                )
            if self.s3_endpoint_url is not None and self.s3_endpoint_url.scheme != "https":
                raise ValueError(
                    "s3_endpoint_url must use HTTPS in staging/production"
                )
            if not self.smtp_use_ssl and not self.smtp_start_tls:
                raise ValueError(
                    "SMTP must use SSL or STARTTLS in staging/production"
                )
        return self


@lru_cache
def get_settings() -> PlatformSettings:
    """Cached singleton — settings are read once per process, at startup."""
    return PlatformSettings()  # type: ignore[call-arg]  # populated from env
