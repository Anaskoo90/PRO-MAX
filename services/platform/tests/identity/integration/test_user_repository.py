import uuid

import pytest

from app.identity.domain.entities import User
from app.identity.domain.organization import Organization
from app.identity.domain.value_objects import Email
from app.platform_core.api.sorting import SortField
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


async def _seed_org(uow) -> OrgId:
    # users.org_id is a real, non-deferrable foreign key to organizations.id
    # (see alembic/versions/0001_identity_initial_schema.py) — a bare
    # OrgId(new_uuid7()) with no matching row will always violate it.
    org = Organization.create(name="Acme", slug=f"acme-{uuid.uuid4().hex[:12]}", owner_user_id=UserId(new_uuid7()))
    await uow.organizations.add(org)
    await uow.session.flush()
    return OrgId(org.id)


def _member(org_id: OrgId, *, email: str, display_name: str) -> User:
    return User.register(org_id=org_id, email=Email(email), password_hash="hash", display_name=display_name)


async def test_search_returns_only_that_orgs_members_with_a_total_count(uow) -> None:
    org_id = await _seed_org(uow)
    other_org_id = await _seed_org(uow)
    ours = _member(org_id, email=f"ours-{uuid.uuid4().hex[:12]}@example.com", display_name="Ours")
    theirs = _member(other_org_id, email=f"theirs-{uuid.uuid4().hex[:12]}@example.com", display_name="Theirs")
    await uow.users.add(ours)
    await uow.users.add(theirs)
    await uow.session.flush()

    users, total = await uow.users.search(org_id)

    assert total == 1
    assert [u.id for u in users] == [ours.id]


async def test_search_filters_by_status(uow) -> None:
    org_id = await _seed_org(uow)
    active = _member(org_id, email=f"active-{uuid.uuid4().hex[:12]}@example.com", display_name="Active")
    suspended = _member(org_id, email=f"suspended-{uuid.uuid4().hex[:12]}@example.com", display_name="Suspended")
    suspended.suspend(reason="test")
    await uow.users.add(active)
    await uow.users.add(suspended)
    await uow.session.flush()

    users, total = await uow.users.search(org_id, status="suspended")

    assert total == 1
    assert users[0].id == suspended.id


async def test_search_matches_query_against_display_name_or_email(uow) -> None:
    org_id = await _seed_org(uow)
    unique = uuid.uuid4().hex[:12]
    alice = _member(org_id, email=f"alice-{unique}@example.com", display_name=f"Alice-{unique}")
    bob = _member(org_id, email=f"bob-{unique}@example.com", display_name=f"Bob-{unique}")
    await uow.users.add(alice)
    await uow.users.add(bob)
    await uow.session.flush()

    by_name, _ = await uow.users.search(org_id, query=f"Alice-{unique}")
    by_email, _ = await uow.users.search(org_id, query=f"bob-{unique}@example.com")

    assert [u.id for u in by_name] == [alice.id]
    assert [u.id for u in by_email] == [bob.id]


async def test_search_sorts_by_the_requested_field(uow) -> None:
    org_id = await _seed_org(uow)
    unique = uuid.uuid4().hex[:12]
    charlie = _member(org_id, email=f"c-{unique}@example.com", display_name=f"Charlie-{unique}")
    alice = _member(org_id, email=f"a-{unique}@example.com", display_name=f"Alice-{unique}")
    await uow.users.add(charlie)
    await uow.users.add(alice)
    await uow.session.flush()

    ascending, _ = await uow.users.search(org_id, sort=[SortField(field="display_name", descending=False)])

    names = [u.display_name for u in ascending]
    assert names.index(f"Alice-{unique}") < names.index(f"Charlie-{unique}")


async def test_search_paginates_with_offset_and_limit(uow) -> None:
    org_id = await _seed_org(uow)
    unique = uuid.uuid4().hex[:12]
    for i in range(5):
        await uow.users.add(_member(org_id, email=f"user{i}-{unique}@example.com", display_name=f"User{i}-{unique}"))
    await uow.session.flush()

    page, total = await uow.users.search(
        org_id, sort=[SortField(field="display_name", descending=False)], offset=2, limit=2,
    )

    assert total == 5
    assert len(page) == 2
