"""Private ticket attachment storage with tenant-aware authorization."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from hashlib import sha256

from pydantic import ValidationError

from app.platform_core.logging.logger import get_logger
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7
from app.platform_core.storage.interfaces import FileStorageProvider
from app.platform_core.storage.upload_contracts import (
    UploadRequest,
    content_matches_declared_type,
)
from app.ticket_system.application.authorization_helpers import TicketAuthorization
from app.ticket_system.application.dtos import TicketAttachmentDTO
from app.ticket_system.application.ports import GuildResolverPort, OrgPermissionCheckerPort
from app.ticket_system.domain.audit import (
    TicketAuditEventCategory,
    TicketAuditLogRecord,
)
from app.ticket_system.domain.entities import (
    Ticket,
    TicketAttachment,
    TicketStatus,
)
from app.ticket_system.domain.exceptions import (
    ClosedTicketAttachmentError,
    GuildNotLinkedForTicketsError,
    InvalidTicketAttachmentError,
    TicketAttachmentNotFoundError,
    TicketNotFoundError,
)
from app.ticket_system.domain.value_objects import TicketActor

_logger = get_logger("ticket_system.attachments")

_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/json": "json",
}


@dataclass(frozen=True, slots=True)
class TicketAttachmentContent:
    filename: str
    content_type: str
    size_bytes: int
    chunks: AsyncIterator[bytes]


def _to_dto(attachment: TicketAttachment) -> TicketAttachmentDTO:
    return TicketAttachmentDTO(
        id=attachment.id,
        org_id=attachment.org_id,
        ticket_id=attachment.ticket_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        uploaded_by_user_id=attachment.uploaded_by_user_id,
        uploaded_by_discord_user_id=attachment.uploaded_by_discord_user_id,
        discord_attachment_id=attachment.discord_attachment_id,
        created_at=attachment.created_at,
    )


class TicketAttachmentService:
    def __init__(
        self,
        *,
        uow_factory,
        permission_checker: OrgPermissionCheckerPort,
        guild_resolver: GuildResolverPort,
        file_storage: FileStorageProvider,
    ) -> None:
        self._uow_factory = uow_factory
        self._authorization = TicketAuthorization(permission_checker=permission_checker)
        self._guild_resolver = guild_resolver
        self._file_storage = file_storage

    async def upload(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        ticket_id: EntityId,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> TicketAttachmentDTO:
        await self._authorization.assert_permission(
            org_id=org_id, user_id=actor_user_id, action="update"
        )
        return await self._upload(
            org_id=org_id,
            ticket_id=ticket_id,
            filename=filename,
            content_type=content_type,
            content=content,
            uploader=TicketActor(user_id=actor_user_id),
            actor_user_id=actor_user_id,
        )

    async def upload_from_bot(
        self,
        *,
        discord_channel_id: str,
        filename: str,
        content_type: str,
        content: bytes,
        uploaded_by_discord_user_id: str,
        discord_attachment_id: str,
    ) -> TicketAttachmentDTO:
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_discord_channel_id(discord_channel_id)
            if ticket is None:
                raise TicketNotFoundError(discord_channel_id)
            await self._assert_bot_guild_access(ticket)
        return await self._upload(
            org_id=ticket.org_id,
            ticket_id=ticket.id,
            filename=filename,
            content_type=content_type,
            content=content,
            uploader=TicketActor(discord_user_id=uploaded_by_discord_user_id),
            actor_user_id=None,
            discord_attachment_id=discord_attachment_id,
            verify_bot_access=True,
        )

    async def list_for_ticket(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        ticket_id: EntityId,
    ) -> list[TicketAttachmentDTO]:
        await self._authorization.assert_permission(
            org_id=org_id, user_id=actor_user_id, action="read"
        )
        async with self._uow_factory() as uow:
            await self._get_web_ticket(uow, ticket_id=ticket_id, org_id=org_id)
            attachments = await uow.ticket_attachments.list_for_ticket(
                org_id=org_id, ticket_id=ticket_id
            )
            return [_to_dto(attachment) for attachment in attachments]

    async def get_content(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        ticket_id: EntityId,
        attachment_id: EntityId,
    ) -> TicketAttachmentContent:
        await self._authorization.assert_permission(
            org_id=org_id, user_id=actor_user_id, action="read"
        )
        async with self._uow_factory() as uow:
            await self._get_web_ticket(uow, ticket_id=ticket_id, org_id=org_id)
            attachment = await uow.ticket_attachments.get_by_id(attachment_id)
            if (
                attachment is None
                or attachment.org_id != org_id
                or attachment.ticket_id != ticket_id
            ):
                raise TicketAttachmentNotFoundError(attachment_id)
        return TicketAttachmentContent(
            filename=attachment.filename,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            chunks=self._file_storage.get(key=attachment.storage_key),
        )

    async def delete(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        ticket_id: EntityId,
        attachment_id: EntityId,
    ) -> None:
        await self._authorization.assert_permission(
            org_id=org_id, user_id=actor_user_id, action="update"
        )
        async with self._uow_factory() as uow:
            await self._get_web_ticket(uow, ticket_id=ticket_id, org_id=org_id)
            attachment = await uow.ticket_attachments.get_by_id(attachment_id)
            if (
                attachment is None
                or attachment.org_id != org_id
                or attachment.ticket_id != ticket_id
            ):
                raise TicketAttachmentNotFoundError(attachment_id)
            await uow.ticket_attachments.delete(attachment.id)
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=attachment.org_id,
                    category=TicketAuditEventCategory.TICKET_CHANGE,
                    action="ticket_attachment_deleted",
                    actor_user_id=actor_user_id,
                    resource_type="ticket_attachment",
                    resource_id=str(attachment.id),
                    metadata={"ticket_id": str(ticket_id)},
                )
            )
            await uow.commit()
        try:
            await self._file_storage.delete(key=attachment.storage_key)
        except Exception:
            # Access is already revoked in the database. The private orphan
            # can be removed by storage lifecycle cleanup without exposing it.
            await _logger.aerror(
                "ticket_attachment_storage_cleanup_failed",
                storage_key=attachment.storage_key,
                exc_info=True,
            )

    async def _upload(
        self,
        *,
        org_id: OrgId,
        ticket_id: EntityId,
        filename: str,
        content_type: str,
        content: bytes,
        uploader: TicketActor,
        actor_user_id: UserId | None,
        discord_attachment_id: str | None = None,
        verify_bot_access: bool = False,
    ) -> TicketAttachmentDTO:
        try:
            upload = UploadRequest(
                filename=filename,
                content_type=content_type,
                size_bytes=len(content),
            )
        except ValidationError as exc:
            raise InvalidTicketAttachmentError(exc.errors()[0]["msg"]) from exc
        if not content_matches_declared_type(content, upload.content_type):
            raise InvalidTicketAttachmentError(
                "File content does not match its declared content type"
            )
        content_sha256 = sha256(content).hexdigest()

        async with self._uow_factory() as uow:
            ticket = await self._get_web_ticket(
                uow, ticket_id=ticket_id, org_id=org_id
            )
            if verify_bot_access:
                await self._assert_bot_guild_access(ticket)
            if ticket.status == TicketStatus.CLOSED:
                raise ClosedTicketAttachmentError()
            if discord_attachment_id is not None:
                existing = (
                    await uow.ticket_attachments.get_by_discord_attachment_id(
                        discord_attachment_id
                    )
                )
                if existing is not None:
                    if (
                        existing.org_id == org_id
                        and existing.ticket_id == ticket_id
                        and existing.filename == upload.filename
                        and existing.content_type == upload.content_type
                        and existing.size_bytes == upload.size_bytes
                        and existing.sha256 == content_sha256
                        and existing.uploaded_by_discord_user_id
                        == uploader.discord_user_id
                    ):
                        return _to_dto(existing)
                    raise InvalidTicketAttachmentError(
                        "Discord attachment is already linked to another ticket"
                    )

            attachment_id = EntityId(new_uuid7())
            extension = _EXTENSIONS[upload.content_type]
            storage_key = (
                f"ticket-attachments/{ticket.org_id}/{ticket.id}/"
                f"{attachment_id}.{extension}"
            )
            attachment = TicketAttachment(
                id=attachment_id,
                org_id=ticket.org_id,
                ticket_id=ticket.id,
                storage_key=storage_key,
                filename=upload.filename,
                content_type=upload.content_type,
                size_bytes=upload.size_bytes,
                sha256=content_sha256,
                uploaded_by_user_id=uploader.user_id,
                uploaded_by_discord_user_id=uploader.discord_user_id,
                discord_attachment_id=discord_attachment_id,
            )
            await self._file_storage.put(
                key=storage_key,
                content=content,
                content_type=upload.content_type,
            )
            try:
                await uow.ticket_attachments.add(attachment)
                await uow.audit_logs.add(
                    TicketAuditLogRecord.create(
                        org_id=ticket.org_id,
                        category=TicketAuditEventCategory.TICKET_CHANGE,
                        action="ticket_attachment_uploaded",
                        actor_user_id=actor_user_id,
                        resource_type="ticket_attachment",
                        resource_id=str(attachment.id),
                        metadata={
                            "ticket_id": str(ticket.id),
                            "content_type": attachment.content_type,
                            "size_bytes": attachment.size_bytes,
                            "discord_attachment_id": discord_attachment_id,
                        },
                    )
                )
                await uow.commit()
            except Exception:
                try:
                    await self._file_storage.delete(key=storage_key)
                except Exception:
                    await _logger.aerror(
                        "ticket_attachment_rollback_cleanup_failed",
                        storage_key=storage_key,
                        exc_info=True,
                    )
                raise
            return _to_dto(attachment)

    async def _get_web_ticket(
        self, uow, *, ticket_id: EntityId, org_id: OrgId
    ) -> Ticket:
        ticket = await uow.tickets.get_by_id(ticket_id)
        if ticket is None or ticket.org_id != org_id:
            raise TicketNotFoundError(ticket_id)
        return ticket

    async def _assert_bot_guild_access(self, ticket: Ticket) -> None:
        resolved_org_id = await self._guild_resolver.resolve_org_id(
            discord_guild_id=ticket.discord_guild_id
        )
        if resolved_org_id is None or OrgId(resolved_org_id) != ticket.org_id:
            raise GuildNotLinkedForTicketsError(ticket.discord_guild_id)
