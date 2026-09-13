"""Ticket conversation commands and queries for web and Discord callers."""

from __future__ import annotations

from app.platform_core.shared_kernel.dtos import PagedResult
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.ticket_system.application.authorization_helpers import TicketAuthorization
from app.ticket_system.application.dtos import TicketMessageDTO
from app.ticket_system.application.ports import GuildResolverPort, OrgPermissionCheckerPort
from app.ticket_system.domain.audit import (
    TicketAuditEventCategory,
    TicketAuditLogRecord,
)
from app.ticket_system.domain.entities import Ticket, TicketMessage, TicketStatus
from app.ticket_system.domain.exceptions import (
    ClosedTicketMessageError,
    DiscordMessageConflictError,
    GuildNotLinkedForTicketsError,
    TicketNotFoundError,
)
from app.ticket_system.domain.value_objects import TicketActor


def _to_dto(message: TicketMessage) -> TicketMessageDTO:
    return TicketMessageDTO(
        id=message.id,
        org_id=message.org_id,
        ticket_id=message.ticket_id,
        body=message.body,
        author_discord_user_id=message.author_discord_user_id,
        author_user_id=message.author_user_id,
        discord_message_id=message.discord_message_id,
        is_internal=message.is_internal,
        created_at=message.created_at,
    )


class TicketMessageService:
    def __init__(
        self,
        *,
        uow_factory,
        permission_checker: OrgPermissionCheckerPort,
        guild_resolver: GuildResolverPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._authorization = TicketAuthorization(permission_checker=permission_checker)
        self._guild_resolver = guild_resolver

    async def add_message(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        ticket_id: EntityId,
        body: str,
        is_internal: bool = False,
    ) -> TicketMessageDTO:
        await self._authorization.assert_permission(
            org_id=org_id, user_id=actor_user_id, action="update"
        )
        if is_internal:
            await self._authorization.assert_permission(
                org_id=org_id, user_id=actor_user_id, action="claim"
            )
        return await self._add(
            org_id=org_id,
            ticket_id=ticket_id,
            body=body,
            author=TicketActor(user_id=actor_user_id),
            actor_user_id=actor_user_id,
            is_internal=is_internal,
        )

    async def list_messages(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        ticket_id: EntityId,
        include_internal: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> PagedResult[TicketMessageDTO]:
        await self._authorization.assert_permission(
            org_id=org_id, user_id=actor_user_id, action="read"
        )
        if include_internal:
            await self._authorization.assert_permission(
                org_id=org_id, user_id=actor_user_id, action="claim"
            )
        async with self._uow_factory() as uow:
            await self._get_web_ticket(uow, ticket_id=ticket_id, org_id=org_id)
            messages, total = await uow.ticket_messages.list_for_ticket(
                org_id=org_id,
                ticket_id=ticket_id,
                include_internal=include_internal,
                offset=(page - 1) * page_size,
                limit=page_size,
            )
            return PagedResult(
                items=[_to_dto(message) for message in messages],
                total=total,
                page=page,
                page_size=page_size,
            )

    async def add_message_from_bot(
        self,
        *,
        ticket_id: EntityId,
        body: str,
        author_discord_user_id: str,
        discord_message_id: str,
        is_internal: bool = False,
    ) -> TicketMessageDTO:
        async with self._uow_factory() as uow:
            ticket = await self._get_bot_ticket(uow, ticket_id=ticket_id)
        return await self._add(
            org_id=ticket.org_id,
            ticket_id=ticket_id,
            body=body,
            author=TicketActor(discord_user_id=author_discord_user_id),
            actor_user_id=None,
            discord_message_id=discord_message_id,
            is_internal=is_internal,
            verify_bot_access=True,
        )

    async def add_message_by_channel_from_bot(
        self,
        *,
        discord_channel_id: str,
        body: str,
        author_discord_user_id: str,
        discord_message_id: str,
        is_internal: bool = False,
    ) -> TicketMessageDTO:
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_discord_channel_id(discord_channel_id)
            if ticket is None:
                raise TicketNotFoundError(discord_channel_id)
            await self._assert_bot_guild_access(ticket)
        return await self._add(
            org_id=ticket.org_id,
            ticket_id=ticket.id,
            body=body,
            author=TicketActor(discord_user_id=author_discord_user_id),
            actor_user_id=None,
            discord_message_id=discord_message_id,
            is_internal=is_internal,
            verify_bot_access=True,
        )

    async def list_messages_from_bot(
        self,
        *,
        ticket_id: EntityId,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[TicketMessageDTO], int]:
        async with self._uow_factory() as uow:
            ticket = await self._get_bot_ticket(uow, ticket_id=ticket_id)
            messages, total = await uow.ticket_messages.list_for_ticket(
                org_id=ticket.org_id,
                ticket_id=ticket.id,
                include_internal=True,
                offset=offset,
                limit=limit,
            )
            return [_to_dto(message) for message in messages], total

    async def _add(
        self,
        *,
        org_id: OrgId,
        ticket_id: EntityId,
        body: str,
        author: TicketActor,
        actor_user_id: UserId | None,
        discord_message_id: str | None = None,
        is_internal: bool = False,
        verify_bot_access: bool = False,
    ) -> TicketMessageDTO:
        async with self._uow_factory() as uow:
            ticket = (
                await self._get_bot_ticket(uow, ticket_id=ticket_id)
                if verify_bot_access
                else await self._get_web_ticket(
                    uow, ticket_id=ticket_id, org_id=org_id
                )
            )
            if ticket.status == TicketStatus.CLOSED:
                raise ClosedTicketMessageError()

            if discord_message_id is not None:
                existing = await uow.ticket_messages.get_by_discord_message_id(
                    discord_message_id
                )
                if existing is not None:
                    if (
                        existing.org_id == ticket.org_id
                        and existing.ticket_id == ticket.id
                        and existing.body == body.strip()
                        and existing.author_discord_user_id == author.discord_user_id
                        and existing.is_internal == is_internal
                    ):
                        return _to_dto(existing)
                    raise DiscordMessageConflictError(discord_message_id)

            message = TicketMessage.create(
                org_id=ticket.org_id,
                ticket_id=ticket.id,
                body=body,
                author=author,
                discord_message_id=discord_message_id,
                is_internal=is_internal,
            )
            if discord_message_id is None:
                await uow.ticket_messages.add(message)
                inserted = True
            else:
                persisted, inserted = await uow.ticket_messages.add_idempotent(
                    message
                )
                if not inserted:
                    if (
                        persisted.org_id == ticket.org_id
                        and persisted.ticket_id == ticket.id
                        and persisted.body == message.body
                        and persisted.author_discord_user_id
                        == message.author_discord_user_id
                        and persisted.is_internal == message.is_internal
                    ):
                        return _to_dto(persisted)
                    raise DiscordMessageConflictError(discord_message_id)
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=ticket.org_id,
                    category=TicketAuditEventCategory.TICKET_CHANGE,
                    action="ticket_message_added",
                    actor_user_id=actor_user_id,
                    resource_type="ticket_message",
                    resource_id=str(message.id),
                    metadata={
                        "ticket_id": str(ticket.id),
                        "is_internal": is_internal,
                        "author_discord_user_id": author.discord_user_id,
                        "discord_message_id": discord_message_id,
                    },
                )
            )
            await uow.commit()
            return _to_dto(message)

    async def _get_web_ticket(
        self, uow, *, ticket_id: EntityId, org_id: OrgId
    ) -> Ticket:
        ticket = await uow.tickets.get_by_id(ticket_id)
        if ticket is None or ticket.org_id != org_id:
            raise TicketNotFoundError(ticket_id)
        return ticket

    async def _get_bot_ticket(self, uow, *, ticket_id: EntityId) -> Ticket:
        ticket = await uow.tickets.get_by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        await self._assert_bot_guild_access(ticket)
        return ticket

    async def _assert_bot_guild_access(self, ticket: Ticket) -> None:
        resolved_org_id = await self._guild_resolver.resolve_org_id(
            discord_guild_id=ticket.discord_guild_id
        )
        if resolved_org_id is None or OrgId(resolved_org_id) != ticket.org_id:
            raise GuildNotLinkedForTicketsError(ticket.discord_guild_id)
