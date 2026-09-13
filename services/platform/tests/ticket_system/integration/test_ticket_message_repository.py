from __future__ import annotations

import pytest
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.ticket_system.domain.entities import Ticket, TicketMessage
from app.ticket_system.domain.value_objects import TicketActor

pytestmark = pytest.mark.asyncio


async def test_messages_are_persisted_ordered_and_tenant_scoped(uow) -> None:
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    ticket = Ticket.create(
        org_id=org_id,
        discord_guild_id=str(new_uuid7()),
        ticket_number=1,
        discord_channel_id=str(new_uuid7()),
        title="Message persistence",
        opener=TicketActor(user_id=UserId(new_uuid7())),
    )
    await uow.tickets.add(ticket)
    await uow.commit()

    public = TicketMessage.create(
        org_id=org_id,
        ticket_id=ticket.id,
        body="Public",
        author=TicketActor(user_id=UserId(new_uuid7())),
    )
    internal = TicketMessage.create(
        org_id=org_id,
        ticket_id=ticket.id,
        body="Internal",
        author=TicketActor(discord_user_id="staff"),
        discord_message_id=str(new_uuid7()),
        is_internal=True,
    )
    await uow.ticket_messages.add(public)
    await uow.ticket_messages.add(internal)
    await uow.commit()

    visible, visible_total = await uow.ticket_messages.list_for_ticket(
        org_id=org_id,
        ticket_id=ticket.id,
        include_internal=False,
    )
    all_messages, all_total = await uow.ticket_messages.list_for_ticket(
        org_id=org_id,
        ticket_id=ticket.id,
        include_internal=True,
    )
    foreign, foreign_total = await uow.ticket_messages.list_for_ticket(
        org_id=other_org_id,
        ticket_id=ticket.id,
        include_internal=True,
    )
    by_discord_id = await uow.ticket_messages.get_by_discord_message_id(
        internal.discord_message_id
    )

    assert [message.id for message in visible] == [public.id]
    assert visible_total == 1
    expected_ids = [
        message.id
        for message in sorted(
            (public, internal), key=lambda message: (message.created_at, message.id)
        )
    ]
    assert [message.id for message in all_messages] == expected_ids
    assert all_total == 2
    assert foreign == []
    assert foreign_total == 0
    assert by_discord_id is not None
    assert by_discord_id.id == internal.id


async def test_discord_message_insert_is_idempotent_in_postgres(uow) -> None:
    org_id = OrgId(new_uuid7())
    ticket = Ticket.create(
        org_id=org_id,
        discord_guild_id=str(new_uuid7()),
        ticket_number=2,
        discord_channel_id=str(new_uuid7()),
        title="Idempotent message",
        opener=TicketActor(discord_user_id="opener"),
    )
    await uow.tickets.add(ticket)
    await uow.commit()
    message = TicketMessage.create(
        org_id=org_id,
        ticket_id=ticket.id,
        body="Only once",
        author=TicketActor(discord_user_id="author"),
        discord_message_id=str(new_uuid7()),
    )

    first, first_inserted = await uow.ticket_messages.add_idempotent(message)
    await uow.commit()
    replay = TicketMessage.create(
        org_id=org_id,
        ticket_id=ticket.id,
        body="Only once",
        author=TicketActor(discord_user_id="author"),
        discord_message_id=message.discord_message_id,
    )
    second, second_inserted = await uow.ticket_messages.add_idempotent(replay)

    assert first_inserted is True
    assert second_inserted is False
    assert second.id == first.id
