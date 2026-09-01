"""
Ticket Category submodule. Deliberately minimal — create/list/get only, no
update/delete yet, since nothing in Phase 1B's scope needs to edit or
retire a category once created; add those when a real caller needs them,
same discipline as everywhere else in this context.

create_category is web-app-facing (JWT + ticket:manage_categories).
create_category_from_bot mirrors ticket_lifecycle.py's bot-facing methods
exactly: no GuildDesk permission check, org_id resolved from
discord_guild_id via the same GuildResolverPort — the bot's
/ticket-category-create command has no JWT-authenticated caller to check
GuildDesk RBAC against, only Discord's own "Manage Server" gate (checked
bot-side before this is ever called).

list_for_guild/get enforce organization ownership exactly like
TicketLifecycleService's equivalent read paths — required after a
confirmed cross-organization data leak in the pre-hardening version of
this file (a category fetched/listed with no org check at all). This
matters even under the bot's full-trust model: a Discord guild can be
unlinked and relinked to a *different* org (Discord Integration's
relink()), which would otherwise leave a stale, wrong-org category
visible under the same discord_guild_id. list_for_guild_from_bot mirrors
create_category_from_bot's org resolution for exactly this reason.
"""

from __future__ import annotations

from app.platform_core.events.dispatcher import EventDispatcher
from app.ticket_system.application.authorization_helpers import TicketAuthorization
from app.ticket_system.application.dtos import TicketCategoryDTO
from app.ticket_system.application.ports import GuildResolverPort, OrgPermissionCheckerPort
from app.ticket_system.domain.audit import TicketAuditEventCategory, TicketAuditLogRecord
from app.ticket_system.domain.entities import TicketCategory
from app.ticket_system.domain.exceptions import GuildNotLinkedForTicketsError, TicketCategoryNotFoundError
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def _to_dto(category: TicketCategory) -> TicketCategoryDTO:
    return TicketCategoryDTO(
        id=category.id, org_id=category.org_id, discord_guild_id=category.discord_guild_id, name=category.name,
        discord_category_channel_id=category.discord_category_channel_id,
        staff_discord_role_ids=list(category.staff_discord_role_ids), is_active=category.is_active,
    )


class TicketCategoryService:
    def __init__(
        self, *, uow_factory, dispatcher: EventDispatcher, permission_checker: OrgPermissionCheckerPort,
        guild_resolver: GuildResolverPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        self._authorization = TicketAuthorization(permission_checker=permission_checker)
        self._guild_resolver = guild_resolver

    async def create_category(
        self, *, org_id: OrgId, actor_user_id: UserId, discord_guild_id: str, name: str,
        discord_category_channel_id: str, staff_discord_role_ids: list[str],
    ) -> TicketCategoryDTO:
        await self._authorization.assert_permission(org_id=org_id, user_id=actor_user_id, action="manage_categories")
        return await self._create(
            org_id=org_id, discord_guild_id=discord_guild_id, name=name,
            discord_category_channel_id=discord_category_channel_id, staff_discord_role_ids=staff_discord_role_ids,
            actor_user_id=actor_user_id,
        )

    async def create_category_from_bot(
        self, *, discord_guild_id: str, name: str, discord_category_channel_id: str,
        staff_discord_role_ids: list[str],
    ) -> TicketCategoryDTO:
        org_id = await self._guild_resolver.resolve_org_id(discord_guild_id=discord_guild_id)
        if org_id is None:
            raise GuildNotLinkedForTicketsError(discord_guild_id)
        return await self._create(
            org_id=OrgId(org_id), discord_guild_id=discord_guild_id, name=name,
            discord_category_channel_id=discord_category_channel_id, staff_discord_role_ids=staff_discord_role_ids,
            actor_user_id=None,
        )

    async def list_for_guild(
        self, *, org_id: OrgId, discord_guild_id: str, active_only: bool = True
    ) -> list[TicketCategoryDTO]:
        async with self._uow_factory() as uow:
            categories = await uow.ticket_categories.list_for_guild(discord_guild_id, active_only=active_only)
            return [_to_dto(c) for c in categories if c.org_id == org_id]

    async def list_for_guild_from_bot(
        self, *, discord_guild_id: str, active_only: bool = True
    ) -> list[TicketCategoryDTO]:
        org_id = await self._guild_resolver.resolve_org_id(discord_guild_id=discord_guild_id)
        if org_id is None:
            raise GuildNotLinkedForTicketsError(discord_guild_id)
        return await self.list_for_guild(org_id=OrgId(org_id), discord_guild_id=discord_guild_id, active_only=active_only)

    async def get(self, *, org_id: OrgId, category_id: EntityId) -> TicketCategoryDTO:
        async with self._uow_factory() as uow:
            category = await uow.ticket_categories.get_by_id(category_id)
            if category is None or category.org_id != org_id:
                raise TicketCategoryNotFoundError(category_id)
            return _to_dto(category)

    async def _create(
        self, *, org_id: OrgId, discord_guild_id: str, name: str, discord_category_channel_id: str,
        staff_discord_role_ids: list[str], actor_user_id: UserId | None,
    ) -> TicketCategoryDTO:
        async with self._uow_factory() as uow:
            category = TicketCategory.create(
                org_id=org_id, discord_guild_id=discord_guild_id, name=name,
                discord_category_channel_id=discord_category_channel_id,
                staff_discord_role_ids=staff_discord_role_ids,
            )
            await uow.ticket_categories.add(category)
            await uow.audit_logs.add(
                TicketAuditLogRecord.create(
                    org_id=org_id, category=TicketAuditEventCategory.TICKET_CHANGE,
                    action="ticket_category_created", actor_user_id=actor_user_id, resource_type="ticket_category",
                    resource_id=str(category.id), metadata={"name": name},
                )
            )
            await uow.commit()
            return _to_dto(category)
