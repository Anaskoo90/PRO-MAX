"""Organization bootstrap integrity (Milestone 5).

register_organization_with_owner must (1) publish an OrganizationCreated
event that names the *real* owner, and (2) refuse to run - persisting
nothing - when the owner system role is not available, instead of creating an
organization whose owner holds no role.
"""

from __future__ import annotations

import uuid

import pytest
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.exceptions import OwnerRoleNotConfiguredError
from app.identity.infrastructure.orm_models import OrganizationOrmModel, UserOrmModel
from app.identity.infrastructure.outbox import OutboxMessageOrmModel
from app.identity.infrastructure.seed_data import seed_identity
from app.platform_core.errors.handlers import _map_status_code
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import OrgId
from sqlalchemy import func, select

pytestmark = pytest.mark.asyncio

_PASSWORD = "Correct-Horse-Battery-9"


def _service(uow, **kwargs) -> OrganizationManagementService:
    return OrganizationManagementService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(), dispatcher=EventDispatcher(), **kwargs
    )


def _registration(slug: str | None = None) -> dict:
    token = uuid.uuid4().hex[:12]
    return dict(
        org_name="Acme",
        slug=slug or f"acme-{token}",
        owner_email=f"owner-{token}@example.com",
        owner_password=_PASSWORD,
        owner_display_name="Owner",
    )


async def test_organization_created_event_names_the_real_owner(uow) -> None:
    await seed_identity(uow, extra_permissions=())

    org_dto, owner_user_id = await _service(uow).register_organization_with_owner(**_registration())

    rows = (
        await uow.session.execute(select(OutboxMessageOrmModel).where(OutboxMessageOrmModel.org_id == org_dto.id))
    ).scalars().all()
    created = [r.payload["payload"]["data"] for r in rows if r.payload["payload"]["event_type"] == "identity.organization_created"]
    assert len(created) == 1
    assert created[0]["owner_user_id"] == str(owner_user_id)  # not a discarded placeholder id
    assert (await uow.users.get_by_id(created[0]["owner_user_id"])) is not None  # and it is a real user


async def test_owner_gets_the_owner_role_and_the_user_registered_event_matches(uow) -> None:
    await seed_identity(uow, extra_permissions=())

    org_dto, owner_user_id = await _service(uow).register_organization_with_owner(**_registration())

    owner_role = await uow.roles.get_by_name(None, "org_owner")
    assert await uow.user_role_assignments.get(owner_user_id, owner_role.id) is not None
    rows = (
        await uow.session.execute(select(OutboxMessageOrmModel).where(OutboxMessageOrmModel.org_id == org_dto.id))
    ).scalars().all()
    registered = [r.payload["payload"]["data"] for r in rows if r.payload["payload"]["event_type"] == "identity.user_registered"]
    assert [d["aggregate_id"] for d in registered] == [str(owner_user_id)]


async def test_registration_fails_safely_when_the_owner_role_is_missing(uow) -> None:
    # Deliberately NOT seeded: no 'org_owner' system role exists.
    registration = _registration()

    with pytest.raises(OwnerRoleNotConfiguredError) as excinfo:
        await _service(uow).register_organization_with_owner(**registration)

    assert _map_status_code(excinfo.value) == 500  # a deployment problem, not a client error
    # nothing was persisted: no organization, no owner user, no outbox events
    assert await uow.organizations.get_by_slug(registration["slug"]) is None
    assert (await uow.session.execute(select(func.count()).select_from(OrganizationOrmModel).where(OrganizationOrmModel.slug == registration["slug"]))).scalar_one() == 0
    assert (await uow.session.execute(select(func.count()).select_from(UserOrmModel).where(UserOrmModel.email == registration["owner_email"]))).scalar_one() == 0


async def test_registration_fails_safely_when_a_custom_owner_role_name_is_not_seeded(uow) -> None:
    await seed_identity(uow, extra_permissions=())  # 'org_owner' exists, but the service is told to use another name
    registration = _registration()

    with pytest.raises(OwnerRoleNotConfiguredError):
        await _service(uow, owner_system_role_name="role_that_was_never_seeded").register_organization_with_owner(
            **registration
        )

    assert await uow.organizations.get_by_slug(registration["slug"]) is None
