"""ORM row <-> domain entity mapping for the Ticket System context."""

from __future__ import annotations

from app.ticket_system.domain.audit import TicketAuditEventCategory, TicketAuditLogRecord
from app.ticket_system.domain.entities import Ticket, TicketCategory, TicketStatus
from app.ticket_system.infrastructure.orm_models import (
    TicketAuditLogOrmModel,
    TicketCategoryOrmModel,
    TicketOrmModel,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def ticket_to_domain(row: TicketOrmModel) -> Ticket:
    return Ticket(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        discord_guild_id=row.discord_guild_id,
        ticket_number=row.ticket_number,
        discord_channel_id=row.discord_channel_id,
        title=row.title,
        status=TicketStatus(row.status),
        opener_discord_user_id=row.opener_discord_user_id,
        opener_user_id=UserId(row.opener_user_id) if row.opener_user_id else None,
        claimed_by_discord_user_id=row.claimed_by_discord_user_id,
        claimed_by_user_id=UserId(row.claimed_by_user_id) if row.claimed_by_user_id else None,
        closed_at=row.closed_at,
        closed_by_discord_user_id=row.closed_by_discord_user_id,
        closed_by_user_id=UserId(row.closed_by_user_id) if row.closed_by_user_id else None,
        created_at=row.created_at,
        version=row.version,
    )


def ticket_to_orm(entity: Ticket, row: TicketOrmModel | None = None) -> TicketOrmModel:
    row = row or TicketOrmModel(id=entity.id)
    row.org_id = entity.org_id
    row.discord_guild_id = entity.discord_guild_id
    row.ticket_number = entity.ticket_number
    row.discord_channel_id = entity.discord_channel_id
    row.title = entity.title
    row.status = entity.status.value
    row.opener_discord_user_id = entity.opener_discord_user_id
    row.opener_user_id = entity.opener_user_id
    row.claimed_by_discord_user_id = entity.claimed_by_discord_user_id
    row.claimed_by_user_id = entity.claimed_by_user_id
    row.closed_at = entity.closed_at
    row.closed_by_discord_user_id = entity.closed_by_discord_user_id
    row.closed_by_user_id = entity.closed_by_user_id
    row.created_at = entity.created_at
    return row


def ticket_category_to_domain(row: TicketCategoryOrmModel) -> TicketCategory:
    return TicketCategory(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        discord_guild_id=row.discord_guild_id,
        name=row.name,
        discord_category_channel_id=row.discord_category_channel_id,
        staff_discord_role_ids=list(row.staff_discord_role_ids),
        is_active=row.is_active,
        version=row.version,
    )


def ticket_category_to_orm(
    entity: TicketCategory, row: TicketCategoryOrmModel | None = None
) -> TicketCategoryOrmModel:
    row = row or TicketCategoryOrmModel(id=entity.id)
    row.org_id = entity.org_id
    row.discord_guild_id = entity.discord_guild_id
    row.name = entity.name
    row.discord_category_channel_id = entity.discord_category_channel_id
    row.staff_discord_role_ids = list(entity.staff_discord_role_ids)
    row.is_active = entity.is_active
    return row


def audit_log_to_domain(row: TicketAuditLogOrmModel) -> TicketAuditLogRecord:
    return TicketAuditLogRecord(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        category=TicketAuditEventCategory(row.category),
        action=row.action,
        actor_user_id=UserId(row.actor_user_id) if row.actor_user_id else None,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        metadata=row.metadata_,
        occurred_at=row.occurred_at,
    )


def audit_log_to_orm(entity: TicketAuditLogRecord) -> TicketAuditLogOrmModel:
    return TicketAuditLogOrmModel(
        id=entity.id,
        org_id=entity.org_id,
        category=entity.category.value,
        action=entity.action,
        actor_user_id=entity.actor_user_id,
        resource_type=entity.resource_type,
        resource_id=entity.resource_id,
        metadata_=entity.metadata,
        occurred_at=entity.occurred_at,
    )
