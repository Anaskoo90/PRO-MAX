import pytest

from app.ticket_system.domain.entities import Ticket
from app.ticket_system.domain.value_objects import TicketActor
from app.platform_core.api.sorting import SortField
from app.platform_core.errors.domain_exceptions import ConcurrencyConflictError
from app.platform_core.shared_kernel.types import OrgId
from app.platform_core.shared_kernel.utils import new_uuid7

pytestmark = pytest.mark.asyncio


def _guild_id() -> str:
    return f"guild-{new_uuid7().hex[:8]}"


def _channel_id() -> str:
    return f"channel-{new_uuid7().hex[:8]}"


async def test_add_then_get_by_id_round_trips(uow) -> None:
    org_id = OrgId(new_uuid7())
    ticket = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Help", opener=TicketActor(discord_user_id="333"),
    )
    await uow.tickets.add(ticket)
    await uow.session.flush()

    fetched = await uow.tickets.get_by_id(ticket.id)

    assert fetched is not None
    assert fetched.title == "Help"
    assert fetched.status.value == "open"


async def test_get_by_number_finds_the_ticket(uow) -> None:
    org_id = OrgId(new_uuid7())
    ticket = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=7, discord_channel_id=_channel_id(),
        title="Help", opener=TicketActor(discord_user_id="333"),
    )
    await uow.tickets.add(ticket)
    await uow.session.flush()

    fetched = await uow.tickets.get_by_number(org_id, 7)

    assert fetched is not None
    assert fetched.id == ticket.id


async def test_get_by_discord_channel_id_finds_the_ticket(uow) -> None:
    channel_id = _channel_id()
    ticket = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=channel_id,
        title="Help", opener=TicketActor(discord_user_id="333"),
    )
    await uow.tickets.add(ticket)
    await uow.session.flush()

    fetched = await uow.tickets.get_by_discord_channel_id(channel_id)

    assert fetched is not None
    assert fetched.id == ticket.id


async def test_update_persists_close_and_bumps_version(uow) -> None:
    ticket = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Help", opener=TicketActor(discord_user_id="333"),
    )
    await uow.tickets.add(ticket)
    await uow.session.flush()

    ticket.close(actor=TicketActor(discord_user_id="999"))
    await uow.tickets.update(ticket)
    await uow.session.flush()

    fetched = await uow.tickets.get_by_id(ticket.id)
    assert fetched.status.value == "closed"
    assert fetched.version == 2


async def test_update_rejects_a_stale_version(uow) -> None:
    """Two in-memory copies of the same row, both loaded before either is
    saved — the second update() call must detect its version is stale
    rather than silently overwriting the first writer's change."""
    ticket = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Help", opener=TicketActor(discord_user_id="333"),
    )
    await uow.tickets.add(ticket)
    await uow.session.flush()

    first_writer = await uow.tickets.get_by_id(ticket.id)
    second_writer = await uow.tickets.get_by_id(ticket.id)

    first_writer.close(actor=TicketActor(discord_user_id="111"))
    await uow.tickets.update(first_writer)
    await uow.session.flush()

    second_writer.close(actor=TicketActor(discord_user_id="222"))
    with pytest.raises(ConcurrencyConflictError):
        await uow.tickets.update(second_writer)


async def test_next_ticket_number_increments_per_org(uow) -> None:
    org_id = OrgId(new_uuid7())

    first = await uow.tickets.next_ticket_number(org_id)
    second = await uow.tickets.next_ticket_number(org_id)
    third = await uow.tickets.next_ticket_number(org_id)

    assert (first, second, third) == (1, 2, 3)


async def test_next_ticket_number_is_independent_per_org(uow) -> None:
    org_a = OrgId(new_uuid7())
    org_b = OrgId(new_uuid7())

    assert await uow.tickets.next_ticket_number(org_a) == 1
    assert await uow.tickets.next_ticket_number(org_b) == 1
    assert await uow.tickets.next_ticket_number(org_a) == 2


async def test_only_one_active_ticket_per_discord_channel(uow) -> None:
    """The partial-unique index (uq_tickets_discord_channel_id_active) is
    the actual business rule this test guards — a second OPEN ticket for
    the same channel must be rejected at the database level."""
    channel_id = _channel_id()
    first = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=channel_id,
        title="First", opener=TicketActor(discord_user_id="1"),
    )
    await uow.tickets.add(first)
    await uow.session.flush()

    second = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=channel_id,
        title="Second", opener=TicketActor(discord_user_id="2"),
    )
    await uow.tickets.add(second)
    with pytest.raises(Exception):
        await uow.session.flush()


async def test_a_claimed_ticket_also_blocks_a_second_active_ticket_for_the_channel(uow) -> None:
    """CLAIMED is just as "active" as OPEN for this constraint's purposes
    (see migration 0009) — this is the case that would have silently
    passed if the index had stayed scoped to 'open' only."""
    channel_id = _channel_id()
    claimed = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=channel_id,
        title="First", opener=TicketActor(discord_user_id="1"),
    )
    claimed.claim(claimant=TicketActor(discord_user_id="777"))
    await uow.tickets.add(claimed)
    await uow.session.flush()

    second = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=channel_id,
        title="Second", opener=TicketActor(discord_user_id="2"),
    )
    await uow.tickets.add(second)
    with pytest.raises(Exception):
        await uow.session.flush()


async def test_a_closed_tickets_channel_can_be_reused(uow) -> None:
    channel_id = _channel_id()
    closed = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=channel_id,
        title="First", opener=TicketActor(discord_user_id="1"),
    )
    closed.close(actor=TicketActor(discord_user_id="999"))
    await uow.tickets.add(closed)
    await uow.session.flush()

    second = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=channel_id,
        title="Second", opener=TicketActor(discord_user_id="2"),
    )
    await uow.tickets.add(second)
    await uow.session.flush()  # must not raise despite two rows now sharing discord_channel_id

    fetched = await uow.tickets.get_by_discord_channel_id(channel_id)
    assert fetched.id == second.id  # the newest (currently active) one, not the closed one


async def test_list_for_org_returns_only_that_orgs_tickets(uow) -> None:
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    ours = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Ours", opener=TicketActor(discord_user_id="1"),
    )
    theirs = Ticket.create(
        org_id=other_org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Theirs", opener=TicketActor(discord_user_id="2"),
    )
    await uow.tickets.add(ours)
    await uow.tickets.add(theirs)
    await uow.session.flush()

    listed = await uow.tickets.list_for_org(org_id)

    assert [t.id for t in listed] == [ours.id]


async def test_search_returns_only_that_orgs_tickets_with_a_total_count(uow) -> None:
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    ours = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Ours", opener=TicketActor(discord_user_id="1"),
    )
    theirs = Ticket.create(
        org_id=other_org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Theirs", opener=TicketActor(discord_user_id="2"),
    )
    await uow.tickets.add(ours)
    await uow.tickets.add(theirs)
    await uow.session.flush()

    tickets, total = await uow.tickets.search(org_id)

    assert total == 1
    assert [t.id for t in tickets] == [ours.id]


async def test_search_filters_by_status(uow) -> None:
    org_id = OrgId(new_uuid7())
    open_ticket = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Open", opener=TicketActor(discord_user_id="1"),
    )
    closed_ticket = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=2, discord_channel_id=_channel_id(),
        title="Closed", opener=TicketActor(discord_user_id="2"),
    )
    closed_ticket.close(actor=TicketActor(discord_user_id="999"))
    await uow.tickets.add(open_ticket)
    await uow.tickets.add(closed_ticket)
    await uow.session.flush()

    tickets, total = await uow.tickets.search(org_id, status="open")

    assert total == 1
    assert tickets[0].id == open_ticket.id


async def test_search_filters_by_claimed_by_discord_user_id(uow) -> None:
    org_id = OrgId(new_uuid7())
    unclaimed = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Unclaimed", opener=TicketActor(discord_user_id="1"),
    )
    claimed = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=2, discord_channel_id=_channel_id(),
        title="Claimed", opener=TicketActor(discord_user_id="2"),
    )
    claimed.claim(claimant=TicketActor(discord_user_id="777"))
    await uow.tickets.add(unclaimed)
    await uow.tickets.add(claimed)
    await uow.session.flush()

    tickets, total = await uow.tickets.search(org_id, claimed_by_discord_user_id="777")

    assert total == 1
    assert tickets[0].id == claimed.id


async def test_search_sorts_by_the_requested_field(uow) -> None:
    org_id = OrgId(new_uuid7())
    first = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="First", opener=TicketActor(discord_user_id="1"),
    )
    second = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=2, discord_channel_id=_channel_id(),
        title="Second", opener=TicketActor(discord_user_id="2"),
    )
    await uow.tickets.add(first)
    await uow.tickets.add(second)
    await uow.session.flush()

    ascending, _ = await uow.tickets.search(org_id, sort=[SortField(field="ticket_number", descending=False)])
    descending, _ = await uow.tickets.search(org_id, sort=[SortField(field="ticket_number", descending=True)])

    assert [t.ticket_number for t in ascending] == [1, 2]
    assert [t.ticket_number for t in descending] == [2, 1]


async def test_search_defaults_to_newest_first_when_no_sort_given(uow) -> None:
    org_id = OrgId(new_uuid7())
    first = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="First", opener=TicketActor(discord_user_id="1"),
    )
    await uow.tickets.add(first)
    await uow.session.flush()
    second = Ticket.create(
        org_id=org_id, discord_guild_id=_guild_id(), ticket_number=2, discord_channel_id=_channel_id(),
        title="Second", opener=TicketActor(discord_user_id="2"),
    )
    await uow.tickets.add(second)
    await uow.session.flush()

    tickets, _ = await uow.tickets.search(org_id)

    assert [t.id for t in tickets] == [second.id, first.id]


async def test_search_paginates_with_offset_and_limit(uow) -> None:
    org_id = OrgId(new_uuid7())
    for i in range(1, 6):
        ticket = Ticket.create(
            org_id=org_id, discord_guild_id=_guild_id(), ticket_number=i, discord_channel_id=_channel_id(),
            title=f"Ticket {i}", opener=TicketActor(discord_user_id=str(i)),
        )
        await uow.tickets.add(ticket)
    await uow.session.flush()

    page, total = await uow.tickets.search(
        org_id, sort=[SortField(field="ticket_number", descending=False)], offset=2, limit=2,
    )

    assert total == 5
    assert [t.ticket_number for t in page] == [3, 4]


async def test_update_persists_claim_and_transfer(uow) -> None:
    ticket = Ticket.create(
        org_id=OrgId(new_uuid7()), discord_guild_id=_guild_id(), ticket_number=1, discord_channel_id=_channel_id(),
        title="Help", opener=TicketActor(discord_user_id="333"),
    )
    await uow.tickets.add(ticket)
    await uow.session.flush()

    ticket.claim(claimant=TicketActor(discord_user_id="777"))
    await uow.tickets.update(ticket)
    await uow.session.flush()

    fetched = await uow.tickets.get_by_id(ticket.id)
    assert fetched.status.value == "claimed"
    assert fetched.claimed_by_discord_user_id == "777"

    fetched.transfer(new_claimant=TicketActor(discord_user_id="888"))
    await uow.tickets.update(fetched)
    await uow.session.flush()

    refetched = await uow.tickets.get_by_id(ticket.id)
    assert refetched.claimed_by_discord_user_id == "888"
