"""
Exercises OrganizationManagementService.register_organization_with_owner
against the real database — the transaction that resolves the
Organization/User chicken-and-egg bootstrap problem, worth covering
end-to-end since a mapper or FK mistake there would only surface at
integration time, not in the pure-domain unit tests.
"""

from __future__ import annotations

import pytest

from app.identity.application.organization_management import OrganizationManagementService
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_register_organization_with_owner_persists_both_aggregates(uow) -> None:
    def uow_factory():
        return uow

    service = OrganizationManagementService(
        uow_factory=uow_factory, password_hasher=PasswordHashingService(), dispatcher=EventDispatcher()
    )

    org_dto, owner_user_id = await service.register_organization_with_owner(
        org_name="Acme",
        slug=f"acme-{new_uuid7().hex[:8]}",
        owner_email=f"owner-{new_uuid7().hex[:8]}@example.com",
        owner_password="Correct-Horse-Battery-9",
        owner_display_name="Owner",
    )

    assert org_dto.owner_user_id == owner_user_id

    persisted_org = await uow.organizations.get_by_id(org_dto.id)
    persisted_owner = await uow.users.get_by_id(owner_user_id)
    assert persisted_org is not None
    assert persisted_owner is not None
    assert persisted_owner.org_id == persisted_org.id
