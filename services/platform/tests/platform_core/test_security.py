from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.security.password_policy import DEFAULT_PASSWORD_POLICY


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
