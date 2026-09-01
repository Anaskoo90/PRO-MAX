import pytest

from app.ticket_system.application.ticket_lifecycle import TicketLifecycleService
from app.ticket_system.domain.exceptions import (
    GuildNotLinkedForTicketsError,
    InsufficientTicketPermissionError,
    InvalidTicketTransitionError,
    TicketNotFoundError,
)
from app.ticket_system.domain.value_objects import TicketActor
from app.platform_core.api.sorting import SortField
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from tests.ticket_system.unit.fakes import (
    AllowAllPermissionChecker,
    AllowOnlyActionsPermissionChecker,
    DenyAllPermissionChecker,
    FakeGuildResolver,
    FakeTicketUnitOfWork,
)

pytestmark = pytest.mark.asyncio


def _make_service(uow, permission_checker=None, guild_resolver=None) -> TicketLifecycleService:
    return TicketLifecycleService(
        uow_factory=lambda: uow, dispatcher=EventDispatcher(),
        permission_checker=permission_checker or AllowAllPermissionChecker(),
        guild_resolver=guild_resolver or FakeGuildResolver(),
    )


@pytest.fixture
def context():
    return FakeTicketUnitOfWork(), OrgId(new_uuid7()), UserId(new_uuid7())


async def test_create_ticket_succeeds_for_a_permitted_user(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)

    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    assert ticket.status == "open"
    assert ticket.ticket_number == 1
    assert ticket.opener_discord_user_id == "333"


async def test_create_ticket_rejects_a_user_without_permission(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientTicketPermissionError):
        await service.create_ticket(
            org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
            title="Need help", opener=TicketActor(discord_user_id="333"),
        )


async def test_create_ticket_allocates_sequential_numbers_per_org(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)

    first = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="First", opener=TicketActor(discord_user_id="1"),
    )
    second = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="333",
        title="Second", opener=TicketActor(discord_user_id="2"),
    )

    assert first.ticket_number == 1
    assert second.ticket_number == 2


async def test_create_ticket_writes_an_audit_log_entry(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)

    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    assert len(uow.audit_logs.records) == 1
    record = uow.audit_logs.records[0]
    assert record.action == "ticket_created"
    assert record.actor_user_id == actor_id
    assert record.resource_id == str(ticket.id)


async def test_close_ticket_transitions_status_and_writes_audit_log(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    closed = await service.close_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, actor=TicketActor(discord_user_id="999"),
    )

    assert closed.status == "closed"
    assert closed.closed_by_discord_user_id == "999"
    assert any(r.action == "ticket_closed" for r in uow.audit_logs.records)


async def test_close_ticket_requires_ticket_claim_not_ticket_update(context) -> None:
    """Regression test: close_ticket used to be gated by the member-
    baseline ticket:update permission (any org member could close any
    ticket). It must now require the same ticket:claim permission as
    claim/unclaim/transfer, a staff-only grant."""
    uow, org_id, actor_id = context
    creator_service = _make_service(uow)
    ticket = await creator_service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    # Holding ticket:update but NOT ticket:claim must no longer be enough.
    update_only_service = _make_service(
        uow, permission_checker=AllowOnlyActionsPermissionChecker(allowed_actions={"update"})
    )
    with pytest.raises(InsufficientTicketPermissionError):
        await update_only_service.close_ticket(
            org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, actor=TicketActor(discord_user_id="999"),
        )

    # Holding ticket:claim (without ticket:update) must be sufficient.
    claim_only_service = _make_service(
        uow, permission_checker=AllowOnlyActionsPermissionChecker(allowed_actions={"claim"})
    )
    closed = await claim_only_service.close_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, actor=TicketActor(discord_user_id="999"),
    )
    assert closed.status == "closed"


async def test_close_ticket_rejects_a_user_without_permission(context) -> None:
    uow, org_id, actor_id = context
    creator_service = _make_service(uow)
    ticket = await creator_service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )
    denying_service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientTicketPermissionError):
        await denying_service.close_ticket(
            org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, actor=TicketActor(discord_user_id="999"),
        )


async def test_close_ticket_rejects_a_ticket_from_another_org(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    other_org_id = OrgId(new_uuid7())
    with pytest.raises(TicketNotFoundError):
        await service.close_ticket(
            org_id=other_org_id, actor_user_id=actor_id, ticket_id=ticket.id, actor=TicketActor(discord_user_id="999"),
        )


async def test_get_raises_not_found_for_an_unknown_ticket(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)

    with pytest.raises(TicketNotFoundError):
        await service.get(org_id=org_id, actor_user_id=actor_id, ticket_id=new_uuid7())


async def test_get_rejects_a_user_without_read_permission(context) -> None:
    uow, org_id, actor_id = context
    creator_service = _make_service(uow)
    ticket = await creator_service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )
    denying_service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientTicketPermissionError):
        await denying_service.get(org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id)


async def test_list_for_org_returns_only_the_orgs_own_tickets(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Ours", opener=TicketActor(discord_user_id="1"),
    )

    other_org_id = OrgId(new_uuid7())
    other_actor_id = UserId(new_uuid7())
    await service.create_ticket(
        org_id=other_org_id, actor_user_id=other_actor_id, discord_guild_id="444", discord_channel_id="555",
        title="Theirs", opener=TicketActor(discord_user_id="2"),
    )

    tickets = await service.list_for_org(org_id=org_id, actor_user_id=actor_id)

    assert len(tickets) == 1
    assert tickets[0].title == "Ours"


async def test_list_for_org_rejects_a_user_without_read_permission(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientTicketPermissionError):
        await service.list_for_org(org_id=org_id, actor_user_id=actor_id)


# --- search_for_org (dashboard) ----------------------------------------------


async def test_search_for_org_returns_only_the_orgs_own_tickets_with_a_total_count(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Ours", opener=TicketActor(discord_user_id="1"),
    )

    other_org_id = OrgId(new_uuid7())
    other_actor_id = UserId(new_uuid7())
    await service.create_ticket(
        org_id=other_org_id, actor_user_id=other_actor_id, discord_guild_id="444", discord_channel_id="555",
        title="Theirs", opener=TicketActor(discord_user_id="2"),
    )

    result = await service.search_for_org(org_id=org_id, actor_user_id=actor_id)

    assert result.total == 1
    assert result.page == 1
    assert len(result.items) == 1
    assert result.items[0].title == "Ours"


async def test_search_for_org_rejects_a_user_without_read_permission(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientTicketPermissionError):
        await service.search_for_org(org_id=org_id, actor_user_id=actor_id)


async def test_search_for_org_filters_by_status(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    open_ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Open one", opener=TicketActor(discord_user_id="1"),
    )
    closed_ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="333",
        title="Closed one", opener=TicketActor(discord_user_id="2"),
    )
    await service.close_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=closed_ticket.id, actor=TicketActor(discord_user_id="999"),
    )

    result = await service.search_for_org(org_id=org_id, actor_user_id=actor_id, status="open")

    assert result.total == 1
    assert result.items[0].id == open_ticket.id


async def test_search_for_org_filters_by_claimed_by_discord_user_id(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Unclaimed", opener=TicketActor(discord_user_id="1"),
    )
    claimed_ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="333",
        title="Claimed", opener=TicketActor(discord_user_id="2"),
    )
    await service.claim_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=claimed_ticket.id,
        claimant=TicketActor(discord_user_id="777"),
    )

    result = await service.search_for_org(org_id=org_id, actor_user_id=actor_id, claimed_by_discord_user_id="777")

    assert result.total == 1
    assert result.items[0].id == claimed_ticket.id


async def test_search_for_org_sorts_by_the_requested_field(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="First", opener=TicketActor(discord_user_id="1"),
    )
    await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="333",
        title="Second", opener=TicketActor(discord_user_id="2"),
    )

    ascending = await service.search_for_org(
        org_id=org_id, actor_user_id=actor_id, sort=[SortField(field="ticket_number", descending=False)],
    )
    descending = await service.search_for_org(
        org_id=org_id, actor_user_id=actor_id, sort=[SortField(field="ticket_number", descending=True)],
    )

    assert [t.ticket_number for t in ascending.items] == [1, 2]
    assert [t.ticket_number for t in descending.items] == [2, 1]


async def test_search_for_org_paginates_using_page_and_page_size(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    for i in range(5):
        await service.create_ticket(
            org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id=f"chan-{i}",
            title=f"Ticket {i}", opener=TicketActor(discord_user_id=str(i)),
        )

    first_page = await service.search_for_org(
        org_id=org_id, actor_user_id=actor_id, sort=[SortField(field="ticket_number", descending=False)],
        page=1, page_size=2,
    )
    second_page = await service.search_for_org(
        org_id=org_id, actor_user_id=actor_id, sort=[SortField(field="ticket_number", descending=False)],
        page=2, page_size=2,
    )

    assert first_page.total == 5
    assert first_page.total_pages == 3
    assert [t.ticket_number for t in first_page.items] == [1, 2]
    assert [t.ticket_number for t in second_page.items] == [3, 4]


# --- claim / unclaim / transfer (web-app) -----------------------------------


async def test_claim_ticket_succeeds_for_a_permitted_user(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    claimed = await service.claim_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, claimant=TicketActor(discord_user_id="777"),
    )

    assert claimed.status == "claimed"
    assert claimed.claimed_by_discord_user_id == "777"
    assert any(r.action == "ticket_claimed" for r in uow.audit_logs.records)


async def test_claim_ticket_rejects_a_user_without_permission(context) -> None:
    uow, org_id, actor_id = context
    creator_service = _make_service(uow)
    ticket = await creator_service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )
    denying_service = _make_service(uow, permission_checker=DenyAllPermissionChecker())

    with pytest.raises(InsufficientTicketPermissionError):
        await denying_service.claim_ticket(
            org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, claimant=TicketActor(discord_user_id="777"),
        )


async def test_claim_ticket_rejects_an_already_claimed_ticket(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )
    await service.claim_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, claimant=TicketActor(discord_user_id="777"),
    )

    with pytest.raises(InvalidTicketTransitionError):
        await service.claim_ticket(
            org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, claimant=TicketActor(discord_user_id="888"),
        )


async def test_unclaim_ticket_returns_it_to_open(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )
    await service.claim_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, claimant=TicketActor(discord_user_id="777"),
    )

    unclaimed = await service.unclaim_ticket(org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id)

    assert unclaimed.status == "open"
    assert unclaimed.claimed_by_discord_user_id is None


async def test_transfer_ticket_reassigns_the_claimant(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )
    await service.claim_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id, claimant=TicketActor(discord_user_id="777"),
    )

    transferred = await service.transfer_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id,
        new_claimant=TicketActor(discord_user_id="888"),
    )

    assert transferred.status == "claimed"
    assert transferred.claimed_by_discord_user_id == "888"


async def test_transfer_ticket_rejects_an_unclaimed_ticket(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    ticket = await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    with pytest.raises(InvalidTicketTransitionError):
        await service.transfer_ticket(
            org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id,
            new_claimant=TicketActor(discord_user_id="888"),
        )


# --- bot-facing paths --------------------------------------------------------


async def test_create_ticket_from_bot_resolves_org_via_guild_resolver(context) -> None:
    uow, org_id, _actor_id = context
    service = _make_service(uow, guild_resolver=FakeGuildResolver(org_ids_by_guild={"111": org_id}))

    ticket = await service.create_ticket_from_bot(
        discord_guild_id="111", discord_channel_id="222", title="Need help",
        opener=TicketActor(discord_user_id="333"),
    )

    assert ticket.org_id == org_id
    assert ticket.status == "open"
    # No actor_user_id on a bot-initiated action's audit entry.
    assert uow.audit_logs.records[0].actor_user_id is None


async def test_create_ticket_from_bot_rejects_an_unlinked_guild(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow, guild_resolver=FakeGuildResolver())

    with pytest.raises(GuildNotLinkedForTicketsError):
        await service.create_ticket_from_bot(
            discord_guild_id="does-not-exist", discord_channel_id="222", title="Need help",
            opener=TicketActor(discord_user_id="333"),
        )


async def test_bot_facing_methods_require_no_guilddesk_permission(context) -> None:
    """The bot path's trust boundary is Discord's own staff-role gate plus
    the bot shared secret (see ticket_bot_router.py) — not GuildDesk RBAC —
    so every _from_bot method must succeed even against a
    DenyAllPermissionChecker."""
    uow, org_id, _actor_id = context
    denying_service = _make_service(
        uow, permission_checker=DenyAllPermissionChecker(),
        guild_resolver=FakeGuildResolver(org_ids_by_guild={"111": org_id}),
    )

    created = await denying_service.create_ticket_from_bot(
        discord_guild_id="111", discord_channel_id="222", title="Need help",
        opener=TicketActor(discord_user_id="333"),
    )
    claimed = await denying_service.claim_ticket_from_bot(
        ticket_id=created.id, claimant=TicketActor(discord_user_id="777"),
    )
    assert claimed.status == "claimed"

    transferred = await denying_service.transfer_ticket_from_bot(
        ticket_id=created.id, new_claimant=TicketActor(discord_user_id="888"),
    )
    assert transferred.claimed_by_discord_user_id == "888"

    unclaimed = await denying_service.unclaim_ticket_from_bot(ticket_id=created.id)
    assert unclaimed.status == "open"

    closed = await denying_service.close_ticket_from_bot(
        ticket_id=created.id, actor=TicketActor(discord_user_id="999"),
    )
    assert closed.status == "closed"


async def test_get_by_discord_channel_id_finds_the_ticket(context) -> None:
    uow, org_id, actor_id = context
    service = _make_service(uow)
    await service.create_ticket(
        org_id=org_id, actor_user_id=actor_id, discord_guild_id="111", discord_channel_id="222",
        title="Need help", opener=TicketActor(discord_user_id="333"),
    )

    found = await service.get_by_discord_channel_id(discord_channel_id="222")

    assert found.discord_channel_id == "222"


async def test_get_by_discord_channel_id_raises_for_an_unknown_channel(context) -> None:
    uow, _org_id, _actor_id = context
    service = _make_service(uow)

    with pytest.raises(TicketNotFoundError):
        await service.get_by_discord_channel_id(discord_channel_id="does-not-exist")
