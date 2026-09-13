import pytest
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY

_FIELD_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
_PRODUCTION_FIELD_ENCRYPTION_KEY = "MTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTE="


def _set_required_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/guilddesk")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", "a" * 32)
    monkeypatch.setenv("GUILDDESK_SECRET_TOKEN_HASH_PEPPER", "b" * 32)
    monkeypatch.setenv("GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY", _FIELD_ENCRYPTION_KEY)


def _set_valid_production_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", "production-jwt-key-unique-0123456789")
    monkeypatch.setenv(
        "GUILDDESK_SECRET_TOKEN_HASH_PEPPER",
        "production-token-pepper-unique-0123456789",
    )
    monkeypatch.setenv(
        "GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY", _PRODUCTION_FIELD_ENCRYPTION_KEY
    )
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://app.example.com"]')
    monkeypatch.setenv("WEB_APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_START_TLS", "true")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "guilddesk-production")


def test_jwt_signing_key_is_required_and_loaded_from_secret_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch)

    settings = PlatformSettings(_env_file=None)

    assert settings.jwt_signing_key == "a" * 32


def test_jwt_signing_key_cannot_be_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.delenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", raising=False)

    with pytest.raises(ValueError, match="GUILDDESK_SECRET_JWT_SIGNING_KEY"):
        PlatformSettings(_env_file=None)


def test_production_configuration_requires_an_email_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://app.example.com"]')
    monkeypatch.delenv("SMTP_HOST", raising=False)

    with pytest.raises(ValueError, match="smtp_host"):
        PlatformSettings(_env_file=None)


def test_smtp_tls_modes_are_mutually_exclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("SMTP_USE_SSL", "true")
    monkeypatch.setenv("SMTP_START_TLS", "true")

    with pytest.raises(ValueError, match="cannot both be enabled"):
        PlatformSettings(_env_file=None)


def test_blank_smtp_credentials_do_not_enable_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")

    settings = PlatformSettings(_env_file=None)

    assert settings.smtp_username is None
    assert settings.smtp_password is None


def test_token_pepper_and_field_encryption_key_are_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.delenv("GUILDDESK_SECRET_TOKEN_HASH_PEPPER")
    monkeypatch.delenv("GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY")

    with pytest.raises(ValueError, match="GUILDDESK_SECRET_TOKEN_HASH_PEPPER"):
        PlatformSettings(_env_file=None)


def test_field_encryption_key_must_be_a_valid_fernet_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY", "x" * 44)

    with pytest.raises(ValueError, match="field encryption key"):
        PlatformSettings(_env_file=None)


def test_discord_oauth_configuration_must_be_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("OAUTH_DISCORD_CLIENT_ID", "client-id")

    with pytest.raises(ValueError, match="must be configured together"):
        PlatformSettings(_env_file=None)


def test_s3_storage_requires_a_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)

    with pytest.raises(ValueError, match="s3_bucket"):
        PlatformSettings(_env_file=None)


def test_s3_credentials_must_be_configured_as_a_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("S3_ACCESS_KEY", "access")
    monkeypatch.delenv("S3_SECRET_KEY", raising=False)

    with pytest.raises(ValueError, match="must be configured together"):
        PlatformSettings(_env_file=None)


def test_enabled_ai_provider_requires_its_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("AI_OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ai_openai_api_key"):
        PlatformSettings(_env_file=None)


def test_ai_fallback_requires_a_distinct_configured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("AI_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.delenv("AI_ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ai_anthropic_api_key"):
        PlatformSettings(_env_file=None)


def test_blank_ai_keys_keep_gateway_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("AI_OPENAI_API_KEY", "")
    monkeypatch.setenv("AI_ANTHROPIC_API_KEY", "")

    settings = PlatformSettings(_env_file=None)

    assert settings.ai_provider == "disabled"
    assert settings.ai_openai_api_key is None
    assert settings.ai_anthropic_api_key is None


def test_production_configuration_rejects_local_file_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_required_configuration(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["https://app.example.com"]')
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    with pytest.raises(ValueError, match="storage_backend"):
        PlatformSettings(_env_file=None)


@pytest.mark.parametrize(
    ("environment_name", "secret_name", "placeholder"),
    [
        (
            "GUILDDESK_SECRET_JWT_SIGNING_KEY",
            "jwt_signing_key",
            "local-compose-jwt-signing-key-change-me",
        ),
        (
            "GUILDDESK_SECRET_TOKEN_HASH_PEPPER",
            "token_hash_pepper",
            "local-compose-token-hash-pepper-change-me",
        ),
        (
            "GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY",
            "field_encryption_key",
            _FIELD_ENCRYPTION_KEY,
        ),
    ],
)
def test_production_configuration_rejects_documented_development_secrets(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    secret_name: str,
    placeholder: str,
) -> None:
    _set_valid_production_configuration(monkeypatch)
    monkeypatch.setenv(environment_name, placeholder)

    with pytest.raises(ValueError, match=secret_name):
        PlatformSettings(_env_file=None)


def test_production_configuration_requires_independent_signing_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_configuration(monkeypatch)
    shared_secret = "production-shared-secret-is-not-allowed"
    monkeypatch.setenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", shared_secret)
    monkeypatch.setenv("GUILDDESK_SECRET_TOKEN_HASH_PEPPER", shared_secret)

    with pytest.raises(ValueError, match="independent secrets"):
        PlatformSettings(_env_file=None)


@pytest.mark.parametrize(
    ("environment_name", "value", "error_match"),
    [
        ("WEB_APP_BASE_URL", "http://app.example.com", "web_app_base_url"),
        (
            "CORS_ALLOWED_ORIGINS",
            '["http://app.example.com"]',
            "cors_allowed_origins",
        ),
        ("S3_ENDPOINT_URL", "http://storage.example.com", "s3_endpoint_url"),
    ],
)
def test_production_configuration_requires_https_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
    value: str,
    error_match: str,
) -> None:
    _set_valid_production_configuration(monkeypatch)
    monkeypatch.setenv(environment_name, value)

    with pytest.raises(ValueError, match=error_match):
        PlatformSettings(_env_file=None)


def test_production_oauth_redirect_requires_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_configuration(monkeypatch)
    monkeypatch.setenv("OAUTH_DISCORD_CLIENT_ID", "client-id")
    monkeypatch.setenv("OAUTH_DISCORD_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("OAUTH_DISCORD_REDIRECT_URI", "http://app.example.com/oauth/callback")

    with pytest.raises(ValueError, match="oauth_discord_redirect_uri"):
        PlatformSettings(_env_file=None)


def test_production_smtp_requires_transport_encryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_configuration(monkeypatch)
    monkeypatch.setenv("SMTP_START_TLS", "false")

    with pytest.raises(ValueError, match="SSL or STARTTLS"):
        PlatformSettings(_env_file=None)


def test_valid_production_configuration_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_valid_production_configuration(monkeypatch)

    settings = PlatformSettings(_env_file=None)

    assert settings.environment.value == "production"


def test_password_hash_round_trips() -> None:
    service = PasswordHashingService()
    hashed = service.hash("Correct-Horse-Battery-Staple-9")
    assert service.verify("Correct-Horse-Battery-Staple-9", hashed) is True


def test_password_hash_rejects_wrong_password() -> None:
    service = PasswordHashingService()
    hashed = service.hash("Correct-Horse-Battery-Staple-9")
    assert service.verify("wrong-password", hashed) is False


def test_password_policy_rejects_short_password() -> None:
    issues = DEFAULT_PASSWORD_POLICY.violations("short1!")
    assert any("at least" in issue for issue in issues)


def test_password_policy_accepts_strong_password() -> None:
    assert DEFAULT_PASSWORD_POLICY.is_valid("Correct-Horse-Battery-9")
