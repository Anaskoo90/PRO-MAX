"""
Ticket Lifecycle submodule. Phase 1A shipped create/close for authenticated
web-app callers only. Phase 1B adds claim/unclaim/transfer plus the
bot-facing call path this module's own docstring previously deferred:
methods suffixed `_from_bot` perform no GuildDesk permission check at all —
their trust boundary is the caller (presentation/bot_authentication.py's
shared-secret dependency, reused as-is from Discord Integration) plus,
before the bot ever calls them, a Discord "staff role" check on the
category's configured staff_discord_role_ids. See the Discord Setup
Wizard's Permission Model decision, carried forward here unchanged.

Web-app-facing methods are unchanged in shape from Phase 1A: always
`actor_user_id`, always a GuildDesk RBAC check, always org-scoped.
"""

from __future__ import annotations

from app.platform_core.api.sorting import SortField
from app.platform_core.events.dispatcher import EventDispatcher
from app.platform_core.shared_kernel.dtos import PagedResult
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.ticket_system.application.authorization_helpers import TicketAuthorization
from app.ticket_system.application.dtos import TicketDTO
from app.ticket_system.application.ports import GuildResolverPort, OrgPermissionCheckerPort
from app.ticket_system.domain.audit import TicketAuditEventCategory, TicketAuditLogRecord
from app.ticket_system.domain.entities import Ticket
from app.ticket_system.domain.exceptions import GuildNotLinkedForTicketsError, TicketNotFoundError
from app.ticket_system.domain.value_objects import TicketActor


def _to_dto(ticket: Ticket) -> TicketDTO:
    return TicketDTO(
        id=ticket.id, org_id=ticket.org_id, discord_guild_id=ticket.discord_guild_id,
        ticket_number=ticket.ticket_number, discord_channel_id=ticket.discord_channel_id, title=ticket.title,
        status=ticket.status.value, opener_discord_user_id=ticket.opener_discord_user_id,
        opener_user_id=ticket.opener_user_id, claimed_by_discord_user_id=ticket.claimed_by_discord_user_id,
        claimed_by_user_id=ticket.claimed_by_user_id, closed_at=ticket.closed_at,
        closed_by_discord_user_id=ticket.closed_by_discord_user_id, closed_by_user_id=ticket.closed_by_user_id,
        created_at=ticket.created_at,
    )


class TicketLifecycleService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        guild_resolver: GuildResolverPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TicketAuthorization(permission_checker=permission_checker)
        self._guild_resolver = guild_resolver

    # --- Web-app-facing (JWT + GuildDesk RBAC) -----------------------------

    async def create_ticket(
        self, *, org_id: OrgId, actor_user_id: UserId, discord_guild_id: str, discord_channel_id: str, title: str,
        opener: TicketActor,
    ) -> TicketDTO:
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="create")
        return await self._create(
            org_id=org_id, discord_guild_id=discord_guild_id, discord_channel_id=discord_channel_id, title=title,
            opener=opener, actor_user_id=actor_user_id,
        )

    async def close_ticket(
        self, *, org_id: OrgId, actor_user_id: UserId, ticket_id: EntityId, actor: TicketActor,
    ) -> TicketDTO:
        # Same permission as claim/unclaim/transfer (not the member-baseline
        # ticket:update) — closing a ticket is a staff action, not something
        # every org member should be able to do to any other member's ticket.
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="claim")
        return await self._close(ticket_id=ticket_id, org_id=org_id, actor=actor, actor_user_id=actor_user_id)

    async def claim_ticket(
        self, *, org_id: OrgId, actor_user_id: UserId, ticket_id: EntityId, claimant: TicketActor,
    ) -> TicketDTO:
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="claim")
        return await self._claim(ticket_id=ticket_id, org_id=org_id, claimant=claimant, actor_user_id=actor_user_id)

    async def unclaim_ticket(self, *, org_id: OrgId, actor_user_id: UserId, ticket_id: EntityId) -> TicketDTO:
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="claim")
        return await self._unclaim(ticket_id=ticket_id, org_id=org_id, actor_user_id=actor_user_id)

    async def transfer_ticket(
        self, *, org_id: OrgId, actor_user_id: UserId, ticket_id: EntityId, new_claimant: TicketActor,
    ) -> TicketDTO:
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="claim")
        return await self._transfer(
            ticket_id=ticket_id, org_id=org_id, new_claimant=new_claimant, actor_user_id=actor_user_id,
        )

    async def get(self, *, org_id: OrgId, actor_user_id: UserId, ticket_id: EntityId) -> TicketDTO:
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="read")

        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_id(ticket_id)
            if ticket is None or ticket.org_id != org_id:
                raise TicketNotFoundError(ticket_id)
            return _to_dto(ticket)

    async def list_for_org(
        self, *, org_id: OrgId, actor_user_id: UserId, offset: int = 0, limit: int = 50
    ) -> list[TicketDTO]:
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="read")

        async with self._uow_factory() as uow:
            tickets = await uow.tickets.list_for_org(org_id, offset=offset, limit=limit)
            return [_to_dto(t) for t in tickets]

    async def search_for_org(
        self,
        *,
        org_id: OrgId,
        actor_user_id: UserId,
        status: str | None = None,
        claimed_by_discord_user_id: str | None = None,
        sort: list[SortField] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PagedResult[TicketDTO]:
        """The dashboard's ticket-listing endpoint — same ticket:read
        permission as list_for_org, plus filtering/sorting/a real total
        count for pagination UI (list_for_org has neither; kept as-is
        rather than folded into this, since it's a simpler primitive other
        callers may still want)."""
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="read")

        async with self._uow_factory() as uow:
            tickets, total = await uow.tickets.search(
                org_id, status=status, claimed_by_discord_user_id=claimed_by_discord_user_id, sort=sort,
                offset=(page - 1) * page_size, limit=page_size,
            )
            return PagedResult(items=[_to_dto(t) for t in tickets], total=total, page=page, page_size=page_size)

    # --- Bot-facing (shared secret + Discord-side staff-role gate) --------

    async def get_by_discord_channel_id(self, *, discord_channel_id: str) -> TicketDTO:
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_discord_channel_id(discord_channel_id)
            if ticket is None:
                raise TicketNotFoundError(discord_channel_id)
            return _to_dto(ticket)

    async def create_ticket_from_bot(
        self, *, discord_guild_id: str, discord_channel_id: str, title: str, opener: TicketActor,
    ) -> TicketDTO:
        org_id = await self._guild_resolver.resolve_org_id(discord_guild_id=discord_guild_id)
        if org_id is None:
            raise GuildNotLinkedForTicketsError(discord_guild_id)
        return await self._create(
            org_id=OrgId(org_id), discord_guild_id=discord_guild_id, discord_channel_id=discord_channel_id,
            title=title, opener=opener, actor_user_id=None,
        )

    async def claim_ticket_from_bot(self, *, ticket_id: EntityId, claimant: TicketActor) -> TicketDTO:
        return await self._claim(ticket_id=ticket_id, org_id=None, claimant=claimant, actor_user_id=None)

    async def unclaim_ticket_from_bot(self, *, ticket_id: EntityId) -> TicketDTO:
        return await self._unclaim(ticket_id=ticket_id, org_id=None, actor_user_id=None)

    async def transfer_ticket_from_bot(self, *, ticket_id: EntityId, new_claimant: TicketActor) -> TicketDTO:
        return await self._transfer(ticket_id=ticket_id, org_id=None, new_claimant=new_claimant, actor_user_id=None)

    async def close_ticket_from_bot(self, *, ticket_id: EntityId, actor: TicketActor) -> TicketDTO:
        return await self._close(ticket_id=ticket_id, org_id=None, actor=actor, actor_user_id=None)

    # --- Shared implementation ---------------------------------------------

    async def _create(
        self, *, org_id: OrgId, discord_guild_id: str, discord_channel_id: str, title: str, opener: TicketActor,
        actor_user_id: UserId | None,
    ) -> TicketDTO:
        async with self._uow_factory() as uow:
            ticket_number = await uow.tickets.next_ticket_number(org_id)
            ticket = Ticket.create(
                org_id=org_id, discord_guild_id=discord_guild_id, ticket_number=ticket_number,
                discord_channel_id=discord_channel_id, title=title, opener=opener,
            )
            await uow.tickets.add(ticket)
            events = ticket.pull_domain_events()
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=org_id, category=TicketAuditEventCategory.TICKET_CHANGE, action="ticket_created",
                    actor_user_id=actor_user_id, resource_type="ticket", resource_id=str(ticket.id),
                    metadata={
                        "discord_channel_id": discord_channel_id, "ticket_number": ticket_number,
                        "opener_discord_user_id": opener.discord_user_id,
                        "opener_user_id": str(opener.user_id) if opener.user_id else None,
                    },
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(ticket)

    async def _claim(
        self, *, ticket_id: EntityId, org_id: OrgId | None, claimant: TicketActor, actor_user_id: UserId | None,
    ) -> TicketDTO:
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_id(ticket_id)
            if ticket is None or (org_id is not None and ticket.org_id != org_id):
                raise TicketNotFoundError(ticket_id)

            ticket.claim(claimant=claimant)
            await uow.tickets.update(ticket)
            events = ticket.pull_domain_events()
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=ticket.org_id, category=TicketAuditEventCategory.TICKET_CHANGE, action="ticket_claimed",
                    actor_user_id=actor_user_id, resource_type="ticket", resource_id=str(ticket.id),
                    metadata={"claimed_by_discord_user_id": claimant.discord_user_id},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(ticket)

    async def _unclaim(
        self, *, ticket_id: EntityId, org_id: OrgId | None, actor_user_id: UserId | None,
    ) -> TicketDTO:
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_id(ticket_id)
            if ticket is None or (org_id is not None and ticket.org_id != org_id):
                raise TicketNotFoundError(ticket_id)

            ticket.unclaim()
            await uow.tickets.update(ticket)
            events = ticket.pull_domain_events()
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=ticket.org_id, category=TicketAuditEventCategory.TICKET_CHANGE, action="ticket_unclaimed",
                    actor_user_id=actor_user_id, resource_type="ticket", resource_id=str(ticket.id),
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(ticket)

    async def _transfer(
        self, *, ticket_id: EntityId, org_id: OrgId | None, new_claimant: TicketActor, actor_user_id: UserId | None,
    ) -> TicketDTO:
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_id(ticket_id)
            if ticket is None or (org_id is not None and ticket.org_id != org_id):
                raise TicketNotFoundError(ticket_id)

            ticket.transfer(new_claimant=new_claimant)
            await uow.tickets.update(ticket)
            events = ticket.pull_domain_events()
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=ticket.org_id, category=TicketAuditEventCategory.TICKET_CHANGE,
                    action="ticket_transferred", actor_user_id=actor_user_id, resource_type="ticket",
                    resource_id=str(ticket.id), metadata={"claimed_by_discord_user_id": new_claimant.discord_user_id},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(ticket)

    async def _close(
        self, *, ticket_id: EntityId, org_id: OrgId | None, actor: TicketActor, actor_user_id: UserId | None,
    ) -> TicketDTO:
        """org_id is None only for the bot-facing path, where there is no
        separately-known org_id to cross-check against — the ticket_id
        itself (resolved from a Discord channel the bot is a member of) is
        the only scoping available."""
        async with self._uow_factory() as uow:
            ticket = await uow.tickets.get_by_id(ticket_id)
            if ticket is None or (org_id is not None and ticket.org_id != org_id):
                raise TicketNotFoundError(ticket_id)

            ticket.close(actor=actor)
            await uow.tickets.update(ticket)
            events = ticket.pull_domain_events()
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=ticket.org_id, category=TicketAuditEventCategory.TICKET_CHANGE, action="ticket_closed",
                    actor_user_id=actor_user_id, resource_type="ticket", resource_id=str(ticket.id),
                    metadata={"closed_by_discord_user_id": actor.discord_user_id},
                )
            )
            await uow.commit()
            await self._dispatcher.dispatch_all(events)
            return _to_dto(ticket)
