from datetime import timedelta

from app.identity.application.security import IpRestrictionChecker, fingerprint_device
from app.identity.domain.exceptions import IpAddressRestrictedError
from app.identity.domain.security_entities import TrustedDevice
from app.platform_core.shared_kernel.types import UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow

import pytest


def test_trusted_device_is_valid_before_expiry() -> None:
    device = TrustedDevice.create(user_id=UserId(new_uuid7()), device_fingerprint_hash="abc", label="laptop")
    assert device.is_valid() is True


def test_trusted_device_is_invalid_after_expiry() -> None:
    device = TrustedDevice.create(
        user_id=UserId(new_uuid7()), device_fingerprint_hash="abc", label="laptop", ttl=timedelta(seconds=-1)
    )
    assert device.is_valid() is False


def test_fingerprint_device_is_deterministic() -> None:
    a = fingerprint_device(user_agent="Mozilla/5.0", accept_language="en-US")
    b = fingerprint_device(user_agent="Mozilla/5.0", accept_language="en-US")
    assert a == b


def test_fingerprint_device_differs_for_different_inputs() -> None:
    a = fingerprint_device(user_agent="Mozilla/5.0", accept_language="en-US")
    b = fingerprint_device(user_agent="Chrome/120", accept_language="en-US")
    assert a != b


def test_ip_restriction_checker_allows_when_no_lists_configured() -> None:
    IpRestrictionChecker().check(ip_address="203.0.113.5", allowlist=[], denylist=[])


def test_ip_restriction_checker_blocks_denylisted_ip() -> None:
    with pytest.raises(IpAddressRestrictedError):
        IpRestrictionChecker().check(ip_address="1.2.3.4", allowlist=[], denylist=["1.2.3.0/24"])


def test_ip_restriction_checker_blocks_ip_outside_allowlist() -> None:
    with pytest.raises(IpAddressRestrictedError):
        IpRestrictionChecker().check(ip_address="8.8.8.8", allowlist=["10.0.0.0/8"], denylist=[])


def test_ip_restriction_checker_allows_ip_inside_allowlist() -> None:
    IpRestrictionChecker().check(ip_address="10.1.2.3", allowlist=["10.0.0.0/8"], denylist=[])
