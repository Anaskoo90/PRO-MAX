from __future__ import annotations

import pytest
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.ticket_system.application.ticket_messages import TicketMessageService
from app.ticket_system.domain.entities import Ticket
from app.ticket_system.domain.exceptions import (
    ClosedTicketMessageError,
    DiscordMessageConflictError,
    GuildNotLinkedForTicketsError,
    InsufficientTicketPermissionError,
    TicketNotFoundError,
)
from app.ticket_system.domain.value_objects import TicketActor

from tests.ticket_system.unit.fakes import (
    AllowAllPermissionChecker,
    AllowOnlyActionsPermissionChecker,
    FakeGuildResolver,
    FakeTicketUnitOfWork,
)

pytestmark = pytest.mark.asyncio


def _ticket(*, org_id: OrgId, guild_id: str = "guild") -> Ticket:
    return Ticket.create(
        org_id=org_id,
        discord_guild_id=guild_id,
        ticket_number=1,
        discord_channel_id=str(new_uuid7()),
        title="Help",
        opener=TicketActor(discord_user_id="opener"),
    )


def _service(
    uow: FakeTicketUnitOfWork,
    *,
    org_id: OrgId,
    allowed_actions: set[str] | None = None,
    linked_org_id: OrgId | None = None,
) -> TicketMessageService:
    permission_checker = (
        AllowAllPermissionChecker()
        if allowed_actions is None
        else AllowOnlyActionsPermissionChecker(allowed_actions=allowed_actions)
    )
    return TicketMessageService(
        uow_factory=lambda: uow,
        permission_checker=permission_checker,
        guild_resolver=FakeGuildResolver(
            org_ids_by_guild={"guild": linked_org_id or org_id}
        ),
    )


async def test_same_tenant_user_can_add_and_list_public_messages() -> None:
    uow = FakeTicketUnitOfWork()
    org_id = OrgId(new_uuid7())
    actor_id = UserId(new_uuid7())
    ticket = _ticket(org_id=org_id)
    await uow.tickets.add(ticket)
    service = _service(uow, org_id=org_id, allowed_actions={"read", "update"})

    created = await service.add_message(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        body="  I need help  ",
    )
    page = await service.list_messages(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
    )

    assert created.body == "I need help"
    assert created.author_user_id == actor_id
    assert page.total == 1
    assert page.items == [created]
    assert uow.audit_logs.records[-1].metadata.get("body") is None


async def test_cross_tenant_ticket_id_is_not_visible_for_add_or_list() -> None:
    uow = FakeTicketUnitOfWork()
    actual_org_id = OrgId(new_uuid7())
    caller_org_id = OrgId(new_uuid7())
    ticket = _ticket(org_id=actual_org_id)
    await uow.tickets.add(ticket)
    service = _service(uow, org_id=caller_org_id)

    with pytest.raises(TicketNotFoundError):
        await service.add_message(
            org_id=caller_org_id,
            actor_user_id=UserId(new_uuid7()),
            ticket_id=ticket.id,
            body="Cross tenant",
        )
    with pytest.raises(TicketNotFoundError):
        await service.list_messages(
            org_id=caller_org_id,
            actor_user_id=UserId(new_uuid7()),
            ticket_id=ticket.id,
        )

    assert uow.ticket_messages.messages == {}


async def test_internal_messages_require_staff_permission_and_are_hidden_by_default() -> None:
    uow = FakeTicketUnitOfWork()
    org_id = OrgId(new_uuid7())
    actor_id = UserId(new_uuid7())
    ticket = _ticket(org_id=org_id)
    await uow.tickets.add(ticket)
    member_service = _service(
        uow, org_id=org_id, allowed_actions={"read", "update"}
    )

    with pytest.raises(InsufficientTicketPermissionError):
        await member_service.add_message(
            org_id=org_id,
            actor_user_id=actor_id,
            ticket_id=ticket.id,
            body="Staff note",
            is_internal=True,
        )

    staff_service = _service(
        uow, org_id=org_id, allowed_actions={"read", "update", "claim"}
    )
    await staff_service.add_message(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        body="Staff note",
        is_internal=True,
    )
    member_page = await member_service.list_messages(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id
    )
    staff_page = await staff_service.list_messages(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        include_internal=True,
    )

    assert member_page.total == 0
    assert staff_page.total == 1
    assert staff_page.items[0].is_internal is True


async def test_closed_ticket_rejects_new_messages() -> None:
    uow = FakeTicketUnitOfWork()
    org_id = OrgId(new_uuid7())
    ticket = _ticket(org_id=org_id)
    ticket.close(actor=TicketActor(discord_user_id="staff"))
    await uow.tickets.add(ticket)

    with pytest.raises(ClosedTicketMessageError):
        await _service(uow, org_id=org_id).add_message(
            org_id=org_id,
            actor_user_id=UserId(new_uuid7()),
            ticket_id=ticket.id,
            body="Too late",
        )


async def test_bot_message_ingestion_is_idempotent() -> None:
    uow = FakeTicketUnitOfWork()
    org_id = OrgId(new_uuid7())
    ticket = _ticket(org_id=org_id)
    await uow.tickets.add(ticket)
    service = _service(uow, org_id=org_id)

    first = await service.add_message_from_bot(
        ticket_id=ticket.id,
        body="Discord message",
        author_discord_user_id="author",
        discord_message_id="message-1",
    )
    retried = await service.add_message_from_bot(
        ticket_id=ticket.id,
        body="Discord message",
        author_discord_user_id="author",
        discord_message_id="message-1",
    )

    assert retried.id == first.id
    assert len(uow.ticket_messages.messages) == 1


async def test_bot_can_ingest_a_message_directly_by_channel_id() -> None:
    uow = FakeTicketUnitOfWork()
    org_id = OrgId(new_uuid7())
    ticket = _ticket(org_id=org_id)
    await uow.tickets.add(ticket)
    service = _service(uow, org_id=org_id)

    created = await service.add_message_by_channel_from_bot(
        discord_channel_id=ticket.discord_channel_id,
        body="Captured directly",
        author_discord_user_id="author",
        discord_message_id="message-channel-1",
    )

    assert created.ticket_id == ticket.id
    assert created.org_id == org_id


async def test_bot_rejects_conflicting_or_stale_guild_messages() -> None:
    uow = FakeTicketUnitOfWork()
    org_id = OrgId(new_uuid7())
    ticket = _ticket(org_id=org_id)
    await uow.tickets.add(ticket)
    service = _service(uow, org_id=org_id)
    await service.add_message_from_bot(
        ticket_id=ticket.id,
        body="Original",
        author_discord_user_id="author",
        discord_message_id="message-1",
    )

    with pytest.raises(DiscordMessageConflictError):
        await service.add_message_from_bot(
            ticket_id=ticket.id,
            body="Changed replay",
            author_discord_user_id="author",
            discord_message_id="message-1",
        )

    stale_service = _service(
        uow,
        org_id=org_id,
        linked_org_id=OrgId(new_uuid7()),
    )
    with pytest.raises(GuildNotLinkedForTicketsError):
        await stale_service.list_messages_from_bot(ticket_id=ticket.id)
