import pytest
from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY

_FIELD_ENCRYPTION_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _set_required_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/guilddesk")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", "a" * 32)
    monkeypatch.setenv("GUILDDESK_SECRET_TOKEN_HASH_PEPPER", "b" * 32)
    monkeypatch.setenv("GUILDDESK_SECRET_FIELD_ENCRYPTION_KEY", _FIELD_ENCRYPTION_KEY)


def test_jwt_signing_key_is_required_and_loaded_from_secret_environment(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_token_pepper_and_field_encryption_key_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
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
