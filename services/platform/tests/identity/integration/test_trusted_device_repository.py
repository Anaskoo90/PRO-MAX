from __future__ import annotations

import uuid

import pytest
from app.identity.domain.entities import User
from app.identity.domain.organization import Organization
from app.identity.domain.security_entities import TrustedDevice
from app.identity.domain.value_objects import Email
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def _seed_user(uow) -> User:
    owner_id = UserId(new_uuid7())
    organization = Organization.create(
        name="Trusted Devices Test",
        slug=f"trusted-devices-{uuid.uuid4().hex[:12]}",
        owner_user_id=owner_id,
    )
    await uow.organizations.add(organization)
    await uow.session.flush()
    user = User.register(
        org_id=OrgId(organization.id),
        email=Email(f"trusted-{uuid.uuid4().hex[:12]}@example.com"),
        password_hash="hash",
        display_name="Trusted Device User",
    )
    await uow.users.add(user)
    await uow.session.flush()
    return user


async def test_delete_for_user_cannot_delete_another_users_device(uow) -> None:
    owner = await _seed_user(uow)
    other_user = await _seed_user(uow)
    device = TrustedDevice.create(
        user_id=UserId(owner.id),
        device_fingerprint_hash=f"fingerprint-{uuid.uuid4().hex}",
        label="Owner laptop",
    )
    await uow.trusted_devices.add(device)
    await uow.session.flush()

    await uow.trusted_devices.delete_for_user(device.id, UserId(other_user.id))
    await uow.session.flush()

    preserved = await uow.trusted_devices.get_by_fingerprint_hash(
        UserId(owner.id), device.device_fingerprint_hash
    )
    assert preserved is not None

    await uow.trusted_devices.delete_for_user(device.id, UserId(owner.id))
    await uow.session.flush()

    deleted = await uow.trusted_devices.get_by_fingerprint_hash(
        UserId(owner.id), device.device_fingerprint_hash
    )
    assert deleted is None
