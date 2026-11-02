import pytest
from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.entities import User, UserStatus
from app.identity.domain.exceptions import (
    InvalidOwnershipTransferTargetError,
    NotOrganizationOwnerError,
    OrganizationNotFoundError,
    OrganizationSlugTakenError,
    OwnerRoleNotConfiguredError,
    UserNotFoundError,
)
from app.identity.domain.organization import Organization
from app.identity.domain.rbac import Role, UserRoleAssignment
from app.identity.domain.value_objects import Email
from app.platform_core.api.sorting import SortField
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.security.hashing import PasswordHashingService
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

from tests.identity.unit.fakes import FakeUnitOfWork

pytestmark = pytest.mark.asyncio


def _make_service(uow) -> OrganizationManagementService:
    return OrganizationManagementService(
        uow_factory=lambda: uow, password_hasher=PasswordHashingService(), dispatcher=EventDispatcher(),
    )


def _make_org(**overrides) -> Organization:
    defaults = dict(name="Acme", slug="acme", owner_user_id=UserId(new_uuid7()))
    defaults.update(overrides)
    return Organization.create(**defaults)


def _make_member(org_id: OrgId, *, email: str, display_name: str, status: UserStatus = UserStatus.ACTIVE) -> User:
    user = User.register(org_id=org_id, email=Email(email), password_hash="hash", display_name=display_name)
    user.status = status
    return user


async def test_update_renames_the_organization() -> None:
    uow = FakeUnitOfWork()
    org = _make_org()
    await uow.organizations.add(org)
    service = _make_service(uow)

    updated = await service.update(org_id=org.id, name="Acme Corp", actor_user_id=new_uuid7())

    assert updated.name == "Acme Corp"


async def test_update_raises_for_an_unknown_org() -> None:
    uow = FakeUnitOfWork()
    service = _make_service(uow)

    with pytest.raises(OrganizationNotFoundError):
        await service.update(org_id=EntityId(new_uuid7()), name="New Name", actor_user_id=new_uuid7())


async def test_update_changes_the_slug_when_available() -> None:
    uow = FakeUnitOfWork()
    org = _make_org()
    await uow.organizations.add(org)
    service = _make_service(uow)

    updated = await service.update(org_id=org.id, name=None, actor_user_id=new_uuid7(), slug="acme-corp")

    assert updated.slug == "acme-corp"


async def test_update_rejects_a_slug_already_used_by_another_org() -> None:
    uow = FakeUnitOfWork()
    org = _make_org(slug="acme")
    other = _make_org(name="Widgets", slug="widgets")
    await uow.organizations.add(org)
    await uow.organizations.add(other)
    service = _make_service(uow)

    with pytest.raises(OrganizationSlugTakenError):
        await service.update(org_id=org.id, name=None, actor_user_id=new_uuid7(), slug="widgets")


async def test_update_allows_setting_the_slug_to_its_own_current_value() -> None:
    uow = FakeUnitOfWork()
    org = _make_org(slug="acme")
    await uow.organizations.add(org)
    service = _make_service(uow)

    updated = await service.update(org_id=org.id, name=None, actor_user_id=new_uuid7(), slug="acme")

    assert updated.slug == "acme"


async def test_update_sets_description_and_logo_url() -> None:
    uow = FakeUnitOfWork()
    org = _make_org()
    await uow.organizations.add(org)
    service = _make_service(uow)

    updated = await service.update(
        org_id=org.id, name=None, actor_user_id=new_uuid7(),
        description="A widget company", logo_url="https://cdn.example.com/logo.png",
    )

    assert updated.description == "A widget company"
    assert updated.logo_url == "https://cdn.example.com/logo.png"


async def test_update_leaves_fields_unset_when_not_provided() -> None:
    uow = FakeUnitOfWork()
    org = _make_org()
    org.update_description("Existing description")
    await uow.organizations.add(org)
    service = _make_service(uow)

    updated = await service.update(org_id=org.id, name="Renamed", actor_user_id=new_uuid7())

    assert updated.name == "Renamed"
    assert updated.description == "Existing description"


async def test_search_members_returns_only_the_orgs_own_members_with_a_total_count() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    await uow.users.add(_make_member(org_id, email="alice@example.com", display_name="Alice"))
    await uow.users.add(_make_member(other_org_id, email="bob@example.com", display_name="Bob"))
    service = _make_service(uow)

    result = await service.search_members(org_id=org_id)

    assert result.total == 1
    assert result.items[0].email == "alice@example.com"


async def test_search_members_filters_by_status() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    await uow.users.add(_make_member(org_id, email="active@example.com", display_name="Active", status=UserStatus.ACTIVE))
    await uow.users.add(
        _make_member(org_id, email="suspended@example.com", display_name="Suspended", status=UserStatus.SUSPENDED)
    )
    service = _make_service(uow)

    result = await service.search_members(org_id=org_id, status="suspended")

    assert result.total == 1
    assert result.items[0].email == "suspended@example.com"


async def test_search_members_searches_by_display_name_or_email() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    await uow.users.add(_make_member(org_id, email="alice@example.com", display_name="Alice Anderson"))
    await uow.users.add(_make_member(org_id, email="bob@example.com", display_name="Bob Brown"))
    service = _make_service(uow)

    by_name = await service.search_members(org_id=org_id, query="anderson")
    by_email = await service.search_members(org_id=org_id, query="bob@example.com")

    assert [m.display_name for m in by_name.items] == ["Alice Anderson"]
    assert [m.display_name for m in by_email.items] == ["Bob Brown"]


async def test_search_members_sorts_and_paginates() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    for name in ("Charlie", "Alice", "Bob"):
        await uow.users.add(_make_member(org_id, email=f"{name.lower()}@example.com", display_name=name))
    service = _make_service(uow)

    result = await service.search_members(
        org_id=org_id, sort=[SortField(field="display_name", descending=False)], page=1, page_size=2,
    )

    assert result.total == 3
    assert result.total_pages == 2
    assert [m.display_name for m in result.items] == ["Alice", "Bob"]


async def test_get_member_returns_a_member_of_the_org() -> None:
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    member = _make_member(org_id, email="alice@example.com", display_name="Alice")
    await uow.users.add(member)
    service = _make_service(uow)

    result = await service.get_member(org_id=org_id, user_id=member.id)

    assert result.email == "alice@example.com"


async def test_get_member_raises_not_found_for_a_member_of_another_org() -> None:
    """A member id that resolves to a different org must be indistinguishable
    from an unknown id — this must never confirm another org's user exists."""
    uow = FakeUnitOfWork()
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    member = _make_member(other_org_id, email="alice@example.com", display_name="Alice")
    await uow.users.add(member)
    service = _make_service(uow)

    with pytest.raises(UserNotFoundError):
        await service.get_member(org_id=org_id, user_id=member.id)


async def test_get_member_raises_not_found_for_an_unknown_user() -> None:
    uow = FakeUnitOfWork()
    service = _make_service(uow)

    with pytest.raises(UserNotFoundError):
        await service.get_member(org_id=OrgId(new_uuid7()), user_id=EntityId(new_uuid7()))


async def test_transfer_ownership_rejects_a_user_from_another_org() -> None:
    uow = FakeUnitOfWork()
    org = _make_org()
    foreign_user = _make_member(
        OrgId(new_uuid7()),
        email="foreign-owner@example.com",
        display_name="Foreign Owner",
    )
    await uow.organizations.add(org)
    await uow.users.add(foreign_user)
    original_owner_user_id = org.owner_user_id
    service = _make_service(uow)

    with pytest.raises(UserNotFoundError):
        await service.transfer_ownership(
            org_id=org.id,
            new_owner_user_id=foreign_user.id,
            actor_user_id=org.owner_user_id,
        )

    assert org.owner_user_id == original_owner_user_id
    assert uow.audit_logs.records == []


async def _seed_owner_role(uow: FakeUnitOfWork) -> Role:
    owner_role = Role.create_system_role(name="org_owner", description="Owner")
    await uow.roles.add(owner_role)
    return owner_role


async def _org_with_owner_holding_role(uow: FakeUnitOfWork) -> tuple[Organization, Role]:
    org = _make_org()
    owner_role = await _seed_owner_role(uow)
    await uow.organizations.add(org)
    await uow.user_role_assignments.add(
        UserRoleAssignment.create(user_id=org.owner_user_id, role_id=owner_role.id, org_id=OrgId(org.id))
    )
    return org, owner_role


async def test_transfer_ownership_allows_a_same_org_member() -> None:
    uow = FakeUnitOfWork()
    org, owner_role = await _org_with_owner_holding_role(uow)
    member = _make_member(
        OrgId(org.id),
        email="new-owner@example.com",
        display_name="New Owner",
    )
    await uow.users.add(member)
    service = _make_service(uow)

    result = await service.transfer_ownership(
        org_id=org.id,
        new_owner_user_id=member.id,
        actor_user_id=org.owner_user_id,
    )

    assert result.owner_user_id == member.id
    assert uow.audit_logs.records[-1].action == "ownership_transferred"
    assert await uow.user_role_assignments.get(member.id, owner_role.id) is not None


# --- ownership transfer hardening (R3) -------------------------------------


async def test_transfer_revokes_the_previous_owners_owner_role_but_keeps_their_other_roles() -> None:
    uow = FakeUnitOfWork()
    org, owner_role = await _org_with_owner_holding_role(uow)
    previous_owner_id = org.owner_user_id
    other_role = Role.create_custom_role(org_id=OrgId(org.id), name="support")
    await uow.roles.add(other_role)
    await uow.user_role_assignments.add(
        UserRoleAssignment.create(user_id=previous_owner_id, role_id=other_role.id, org_id=OrgId(org.id))
    )
    successor = _make_member(OrgId(org.id), email="successor@example.com", display_name="Successor")
    await uow.users.add(successor)

    await _make_service(uow).transfer_ownership(
        org_id=org.id, new_owner_user_id=successor.id, actor_user_id=previous_owner_id
    )

    assert await uow.user_role_assignments.get(previous_owner_id, owner_role.id) is None
    assert await uow.user_role_assignments.get(previous_owner_id, other_role.id) is not None  # untouched
    assert await uow.user_role_assignments.get(successor.id, owner_role.id) is not None


async def test_previous_owner_cannot_transfer_ownership_back() -> None:
    uow = FakeUnitOfWork()
    org, _owner_role = await _org_with_owner_holding_role(uow)
    previous_owner_id = org.owner_user_id
    successor = _make_member(OrgId(org.id), email="successor@example.com", display_name="Successor")
    previous_owner = _make_member(OrgId(org.id), email="former@example.com", display_name="Former")
    previous_owner.id = previous_owner_id
    await uow.users.add(successor)
    await uow.users.add(previous_owner)
    service = _make_service(uow)
    await service.transfer_ownership(org_id=org.id, new_owner_user_id=successor.id, actor_user_id=previous_owner_id)

    with pytest.raises(NotOrganizationOwnerError):
        await service.transfer_ownership(
            org_id=org.id, new_owner_user_id=previous_owner_id, actor_user_id=previous_owner_id
        )

    assert org.owner_user_id == successor.id


async def test_a_co_owner_who_is_not_the_designated_owner_cannot_transfer_ownership() -> None:
    uow = FakeUnitOfWork()
    org, owner_role = await _org_with_owner_holding_role(uow)
    co_owner = _make_member(OrgId(org.id), email="co@example.com", display_name="Co-owner")
    await uow.users.add(co_owner)
    await uow.user_role_assignments.add(
        UserRoleAssignment.create(user_id=co_owner.id, role_id=owner_role.id, org_id=OrgId(org.id))
    )
    original_owner = org.owner_user_id

    with pytest.raises(NotOrganizationOwnerError):
        await _make_service(uow).transfer_ownership(
            org_id=org.id, new_owner_user_id=co_owner.id, actor_user_id=co_owner.id
        )

    assert org.owner_user_id == original_owner
    assert await uow.user_role_assignments.get(original_owner, owner_role.id) is not None
    assert uow.audit_logs.records == []


@pytest.mark.parametrize(
    "status", [UserStatus.SUSPENDED, UserStatus.DEACTIVATED, UserStatus.PENDING_VERIFICATION]
)
async def test_transfer_rejects_a_target_that_is_not_active(status: UserStatus) -> None:
    uow = FakeUnitOfWork()
    org, owner_role = await _org_with_owner_holding_role(uow)
    target = _make_member(OrgId(org.id), email="target@example.com", display_name="Target", status=status)
    await uow.users.add(target)
    original_owner = org.owner_user_id

    with pytest.raises(InvalidOwnershipTransferTargetError):
        await _make_service(uow).transfer_ownership(
            org_id=org.id, new_owner_user_id=target.id, actor_user_id=original_owner
        )

    assert org.owner_user_id == original_owner
    assert await uow.user_role_assignments.get(target.id, owner_role.id) is None
    assert await uow.user_role_assignments.get(original_owner, owner_role.id) is not None


async def test_transfer_to_the_current_owner_is_rejected() -> None:
    uow = FakeUnitOfWork()
    org, _owner_role = await _org_with_owner_holding_role(uow)
    owner = _make_member(OrgId(org.id), email="owner@example.com", display_name="Owner")
    owner.id = org.owner_user_id
    await uow.users.add(owner)

    with pytest.raises(InvalidOwnershipTransferTargetError):
        await _make_service(uow).transfer_ownership(
            org_id=org.id, new_owner_user_id=owner.id, actor_user_id=owner.id
        )


async def test_transfer_fails_closed_when_the_owner_role_is_not_seeded() -> None:
    uow = FakeUnitOfWork()
    org = _make_org()
    await uow.organizations.add(org)  # note: no owner role in the fake role repository
    target = _make_member(OrgId(org.id), email="target@example.com", display_name="Target")
    await uow.users.add(target)
    original_owner = org.owner_user_id

    with pytest.raises(OwnerRoleNotConfiguredError):
        await _make_service(uow).transfer_ownership(
            org_id=org.id, new_owner_user_id=target.id, actor_user_id=original_owner
        )

    assert org.owner_user_id == original_owner
