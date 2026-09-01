import pytest

from app.ticket_system.domain.entities import TicketCategory
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


def _guild_id() -> str:
    return f"guild-{new_uuid7().hex[:8]}"


async def test_add_then_get_by_id_round_trips(uow) -> None:
    category = TicketCategory.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), name="Billing",
        discord_category_channel_id="222", staff_discord_role_ids=["role-1", "role-2"],
    )
    await uow.ticket_categories.add(category)
    await uow.session.flush()

    fetched = await uow.ticket_categories.get_by_id(category.id)

    assert fetched is not None
    assert fetched.name == "Billing"
    assert fetched.staff_discord_role_ids == ["role-1", "role-2"]
    assert fetched.is_active is True


async def test_list_for_guild_returns_only_that_guilds_categories(uow) -> None:
    guild_id = _guild_id()
    ours = TicketCategory.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=guild_id, name="Ours", discord_category_channel_id="222",
        staff_discord_role_ids=[],
    )
    theirs = TicketCategory.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), name="Theirs", discord_category_channel_id="333",
        staff_discord_role_ids=[],
    )
    await uow.ticket_categories.add(ours)
    await uow.ticket_categories.add(theirs)
    await uow.session.flush()

    listed = await uow.ticket_categories.list_for_guild(guild_id)

    assert [c.id for c in listed] == [ours.id]


async def test_list_for_guild_active_only_excludes_inactive_categories(uow) -> None:
    guild_id = _guild_id()
    active = TicketCategory.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=guild_id, name="Active", discord_category_channel_id="222",
        staff_discord_role_ids=[],
    )
    inactive = TicketCategory.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=guild_id, name="Inactive", discord_category_channel_id="333",
        staff_discord_role_ids=[],
    )
    inactive.is_active = False
    await uow.ticket_categories.add(active)
    await uow.ticket_categories.add(inactive)
    await uow.session.flush()

    listed = await uow.ticket_categories.list_for_guild(guild_id, active_only=True)
    assert [c.id for c in listed] == [active.id]

    listed_all = await uow.ticket_categories.list_for_guild(guild_id, active_only=False)
    assert {c.id for c in listed_all} == {active.id, inactive.id}


async def test_update_rejects_a_stale_version(uow) -> None:
    category = TicketCategory.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), name="Billing",
        discord_category_channel_id="222", staff_discord_role_ids=[],
    )
    await uow.ticket_categories.add(category)
    await uow.session.flush()

    first_writer = await uow.ticket_categories.get_by_id(category.id)
    second_writer = await uow.ticket_categories.get_by_id(category.id)

    first_writer.is_active = False
    await uow.ticket_categories.update(first_writer)
    await uow.session.flush()

    second_writer.name = "Renamed"
    with pytest.raises(ConcurrencyConflictError):
        await uow.ticket_categories.update(second_writer)
