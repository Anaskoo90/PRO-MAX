from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.platform_core.shared_kernel.types import OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.platform_core.storage.interfaces import StoredFileRef
from app.ticket_system.application.ticket_attachments import TicketAttachmentService
from app.ticket_system.domain.entities import Ticket
from app.ticket_system.domain.exceptions import (
    InvalidTicketAttachmentError,
    TicketAttachmentNotFoundError,
    TicketNotFoundError,
)
from app.ticket_system.domain.value_objects import TicketActor

from tests.ticket_system.unit.fakes import (
    AllowAllPermissionChecker,
    FakeGuildResolver,
    FakeTicketUnitOfWork,
)

pytestmark = pytest.mark.asyncio

_PNG = b"\x89PNG\r\n\x1a\ncontrolled-ticket-attachment"


class _Storage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(
        self, *, key: str, content: bytes, content_type: str
    ) -> StoredFileRef:
        self.objects[key] = (content, content_type)
        return StoredFileRef(
            storage_key=key, size_bytes=len(content), content_type=content_type
        )

    async def get(self, *, key: str) -> AsyncIterator[bytes]:
        yield self.objects[key][0]

    async def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)

    async def exists(self, *, key: str) -> bool:
        return key in self.objects

    async def generate_presigned_url(self, *, key: str, ttl_seconds: int) -> str:
        return f"https://storage.test/{key}?ttl={ttl_seconds}"


def _context():
    uow = FakeTicketUnitOfWork()
    org_id = OrgId(new_uuid7())
    ticket = Ticket.create(
        org_id=org_id,
        discord_guild_id="guild",
        ticket_number=1,
        discord_channel_id="channel",
        title="Attachments",
        opener=TicketActor(discord_user_id="opener"),
    )
    uow.tickets.tickets[ticket.id] = ticket
    storage = _Storage()
    service = TicketAttachmentService(
        uow_factory=lambda: uow,
        permission_checker=AllowAllPermissionChecker(),
        guild_resolver=FakeGuildResolver(org_ids_by_guild={"guild": org_id}),
        file_storage=storage,
    )
    return uow, storage, service, org_id, ticket


async def test_same_tenant_upload_list_download_and_delete() -> None:
    uow, storage, service, org_id, ticket = _context()
    actor_id = UserId(new_uuid7())

    created = await service.upload(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        filename="C:\\fakepath\\proof.png",
        content_type="image/png",
        content=_PNG,
    )
    listed = await service.list_for_ticket(
        org_id=org_id, actor_user_id=actor_id, ticket_id=ticket.id
    )
    downloaded = await service.get_content(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        attachment_id=created.id,
    )

    assert created.filename == "proof.png"
    assert created.uploaded_by_user_id == actor_id
    assert listed == [created]
    assert b"".join([chunk async for chunk in downloaded.chunks]) == _PNG
    assert len(storage.objects) == 1

    await service.delete(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        attachment_id=created.id,
    )
    assert storage.objects == {}
    assert uow.ticket_attachments.attachments == {}


async def test_cross_tenant_ticket_and_attachment_ids_are_hidden() -> None:
    _uow, _storage, service, org_id, ticket = _context()
    actor_id = UserId(new_uuid7())
    created = await service.upload(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        filename="proof.png",
        content_type="image/png",
        content=_PNG,
    )
    other_org_id = OrgId(new_uuid7())

    with pytest.raises(TicketNotFoundError):
        await service.list_for_ticket(
            org_id=other_org_id,
            actor_user_id=actor_id,
            ticket_id=ticket.id,
        )
    with pytest.raises(TicketNotFoundError):
        await service.get_content(
            org_id=other_org_id,
            actor_user_id=actor_id,
            ticket_id=ticket.id,
            attachment_id=created.id,
        )


async def test_attachment_from_another_ticket_is_hidden() -> None:
    uow, _storage, service, org_id, ticket = _context()
    actor_id = UserId(new_uuid7())
    created = await service.upload(
        org_id=org_id,
        actor_user_id=actor_id,
        ticket_id=ticket.id,
        filename="proof.png",
        content_type="image/png",
        content=_PNG,
    )
    other_ticket = Ticket.create(
        org_id=org_id,
        discord_guild_id="guild",
        ticket_number=2,
        discord_channel_id="other-channel",
        title="Other",
        opener=TicketActor(discord_user_id="opener"),
    )
    await uow.tickets.add(other_ticket)

    with pytest.raises(TicketAttachmentNotFoundError):
        await service.get_content(
            org_id=org_id,
            actor_user_id=actor_id,
            ticket_id=other_ticket.id,
            attachment_id=created.id,
        )


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("empty.txt", "text/plain", b""),
        ("script.exe", "application/octet-stream", b"MZ"),
        ("fake.png", "image/png", b"not-a-png"),
        ("bad.json", "application/json", b"not-json"),
    ],
)
async def test_unsafe_uploads_are_rejected_before_storage(
    filename: str, content_type: str, content: bytes
) -> None:
    _uow, storage, service, org_id, ticket = _context()

    with pytest.raises(InvalidTicketAttachmentError):
        await service.upload(
            org_id=org_id,
            actor_user_id=UserId(new_uuid7()),
            ticket_id=ticket.id,
            filename=filename,
            content_type=content_type,
            content=content,
        )

    assert storage.objects == {}


async def test_bot_attachment_replay_returns_the_existing_record() -> None:
    uow, storage, service, _org_id, ticket = _context()

    first = await service.upload_from_bot(
        discord_channel_id=ticket.discord_channel_id,
        filename="proof.png",
        content_type="image/png",
        content=_PNG,
        uploaded_by_discord_user_id="author",
        discord_attachment_id="attachment-1",
    )
    replay = await service.upload_from_bot(
        discord_channel_id=ticket.discord_channel_id,
        filename="proof.png",
        content_type="image/png",
        content=_PNG,
        uploaded_by_discord_user_id="author",
        discord_attachment_id="attachment-1",
    )

    assert replay.id == first.id
    assert len(storage.objects) == 1
    assert len(uow.ticket_attachments.attachments) == 1

    with pytest.raises(InvalidTicketAttachmentError):
        await service.upload_from_bot(
            discord_channel_id=ticket.discord_channel_id,
            filename="proof.png",
            content_type="image/png",
            content=b"\x89PNG\r\n\x1a\ndifferent-content",
            uploaded_by_discord_user_id="author",
            discord_attachment_id="attachment-1",
        )
