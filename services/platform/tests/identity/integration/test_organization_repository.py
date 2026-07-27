import pytest

from app.identity.domain.organization import Organization
from app.platform_core.shared_kernel.types import UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_add_then_get_by_id_round_trips(uow) -> None:
    org = Organization.create(name="Acme", slug=f"acme-{new_uuid7().hex[:8]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_id(org.id)

    assert fetched is not None
    assert fetched.slug == org.slug
    assert fetched.name == "Acme"


async def test_get_by_slug_finds_the_organization(uow) -> None:
    slug = f"acme-{new_uuid7().hex[:8]}"
    org = Organization.create(name="Acme", slug=slug, owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_slug(slug)

    assert fetched is not None
    assert fetched.id == org.id


async def test_update_persists_settings_change(uow) -> None:
    org = Organization.create(name="Acme", slug=f"acme-{new_uuid7().hex[:8]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    org.update_settings({"ip_allowlist": ["10.0.0.0/8"]})
    await uow.organizations.update(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_id(org.id)
    assert fetched.settings["ip_allowlist"] == ["10.0.0.0/8"]
