from datetime import timedelta

from app.identity.domain.entities import User, UserStatus
from app.identity.domain.exceptions import AccountNotActiveError, EmailAlreadyVerifiedError
from app.identity.domain.value_objects import Email
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

import pytest


def _new_user() -> User:
    return User.register(
        org_id=OrgId(new_uuid7()), email=Email("person@example.com"), password_hash="hash", display_name="Person"
    )


def test_register_starts_pending_verification() -> None:
    user = _new_user()
    assert user.status == UserStatus.PENDING_VERIFICATION


def test_verify_email_activates_account() -> None:
    user = _new_user()
    user.verify_email()
    assert user.status == UserStatus.ACTIVE


def test_verify_email_twice_raises() -> None:
    user = _new_user()
    user.verify_email()
    with pytest.raises(EmailAlreadyVerifiedError):
        user.verify_email()


def test_assert_can_authenticate_rejects_unverified_account() -> None:
    user = _new_user()
    with pytest.raises(AccountNotActiveError):
        user.assert_can_authenticate()


def test_account_locks_after_threshold_failed_logins() -> None:
    user = _new_user()
    for _ in range(5):
        user.record_failed_login(lockout_threshold=5, lockout_duration=timedelta(minutes=15))
    assert user.is_locked() is True


def test_account_not_locked_below_threshold() -> None:
    user = _new_user()
    for _ in range(4):
        user.record_failed_login(lockout_threshold=5, lockout_duration=timedelta(minutes=15))
    assert user.is_locked() is False


def test_successful_login_resets_failed_attempts() -> None:
    user = _new_user()
    for _ in range(4):
        user.record_failed_login(lockout_threshold=5, lockout_duration=timedelta(minutes=15))
    user.record_successful_login()
    assert user.failed_login_attempts == 0
    assert user.is_locked() is False
