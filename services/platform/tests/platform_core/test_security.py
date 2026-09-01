import pytest

from app.platform_core.configuration.settings import PlatformSettings
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY


def test_jwt_signing_key_is_required_and_loaded_from_secret_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/guilddesk")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", "a" * 32)

    settings = PlatformSettings(_env_file=None)

    assert settings.jwt_signing_key == "a" * 32


def test_jwt_signing_key_cannot_be_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/guilddesk")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("GUILDDESK_SECRET_JWT_SIGNING_KEY", raising=False)

    with pytest.raises(ValueError, match="GUILDDESK_SECRET_JWT_SIGNING_KEY"):
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
