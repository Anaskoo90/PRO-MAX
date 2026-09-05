import uuid

import pytest

from app.identity.domain.organization import Organization
from app.platform_core.shared_kernel.types import UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def test_add_then_get_by_id_round_trips(uow) -> None:
    org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_id(org.id)

    assert fetched is not None
    assert fetched.slug == org.slug
    assert fetched.name == "Acme"


async def test_get_by_slug_finds_the_organization(uow) -> None:
    slug = f"acme-{uuid.uuid4().hex[:12]}"
    org = Organization.create(name="Acme", slug=slug, owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_slug(slug)

    assert fetched is not None
    assert fetched.id == org.id


async def test_update_persists_settings_change(uow) -> None:
    org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    org.update_settings({"ip_allowlist": ["10.0.0.0/8"]})
    await uow.organizations.update(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_id(org.id)
    assert fetched.settings["ip_allowlist"] == ["10.0.0.0/8"]


async def test_update_persists_slug_description_and_logo_url(uow) -> None:
    org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    new_slug = f"acme-corp-{uuid.uuid4().hex[:12]}"
    org.change_slug(new_slug)
    org.update_description("A widget company")
    org.update_logo_url("https://cdn.example.com/logo.png")
    await uow.organizations.update(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_id(org.id)
    assert fetched.slug == new_slug
    assert fetched.description == "A widget company"
    assert fetched.logo_url == "https://cdn.example.com/logo.png"


async def test_a_new_organization_has_no_description_or_logo_by_default(uow) -> None:
    org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()

    fetched = await uow.organizations.get_by_id(org.id)
    assert fetched.description is None
    assert fetched.logo_url is None
