from __future__ import annotations

import pytest
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.ticket_system.domain.entities import Ticket, TicketAttachment
from app.ticket_system.domain.value_objects import TicketActor

pytestmark = pytest.mark.asyncio


async def test_attachment_metadata_is_persisted_and_tenant_scoped(uow) -> None:
    org_id = OrgId(new_uuid7())
    other_org_id = OrgId(new_uuid7())
    ticket = Ticket.create(
        org_id=org_id,
        discord_guild_id=str(new_uuid7()),
        ticket_number=3,
        discord_channel_id=str(new_uuid7()),
        title="Attachment repository",
        opener=TicketActor(discord_user_id="opener"),
    )
    await uow.tickets.add(ticket)
    await uow.commit()
    attachment = TicketAttachment(
        id=EntityId(new_uuid7()),
        org_id=org_id,
        ticket_id=ticket.id,
        storage_key=f"ticket-attachments/{org_id}/{ticket.id}/proof.txt",
        filename="proof.txt",
        content_type="text/plain",
        size_bytes=5,
        sha256="0" * 64,
        uploaded_by_user_id=UserId(new_uuid7()),
    )
    await uow.ticket_attachments.add(attachment)
    await uow.commit()

    fetched = await uow.ticket_attachments.get_by_id(attachment.id)
    ours = await uow.ticket_attachments.list_for_ticket(
        org_id=org_id, ticket_id=ticket.id
    )
    foreign = await uow.ticket_attachments.list_for_ticket(
        org_id=other_org_id, ticket_id=ticket.id
    )

    assert fetched is not None
    assert fetched.filename == "proof.txt"
    assert [item.id for item in ours] == [attachment.id]
    assert foreign == []

    await uow.ticket_attachments.delete(attachment.id)
    await uow.commit()
    assert await uow.ticket_attachments.get_by_id(attachment.id) is None
