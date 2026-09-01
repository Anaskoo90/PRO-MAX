import pytest

from app.identity.application.organization_management import OrganizationManagementService
from app.identity.domain.entities import User, UserStatus
from app.identity.domain.exceptions import OrganizationNotFoundError, OrganizationSlugTakenError, UserNotFoundError
from app.identity.domain.organization import Organization
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
