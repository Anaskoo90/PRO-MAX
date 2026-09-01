"""ORM row <-> domain entity mapping for the Discord Integration context."""

from __future__ import annotations

from app.discord_integration.domain.audit import DiscordAuditEventCategory, DiscordAuditLogRecord
from app.discord_integration.domain.entities import GuildLink, GuildLinkStatus, GuildSetupToken
from app.discord_integration.infrastructure.orm_models import (
    DiscordAuditLogOrmModel,
    GuildLinkOrmModel,
    GuildSetupTokenOrmModel,
)
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId


def guild_setup_token_to_domain(row: GuildSetupTokenOrmModel) -> GuildSetupToken:
    return GuildSetupToken(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        requested_by_user_id=UserId(row.requested_by_user_id),
        token_hash=row.token_hash,
        created_at=row.created_at,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        consumed_by_discord_guild_id=row.consumed_by_discord_guild_id,
    )


def guild_setup_token_to_orm(
    entity: GuildSetupToken, row: GuildSetupTokenOrmModel | None = None
) -> GuildSetupTokenOrmModel:
    row = row or GuildSetupTokenOrmModel(id=entity.id)
    row.org_id = entity.org_id
    row.requested_by_user_id = entity.requested_by_user_id
    row.token_hash = entity.token_hash
    row.created_at = entity.created_at
    row.expires_at = entity.expires_at
    row.consumed_at = entity.consumed_at
    row.consumed_by_discord_guild_id = entity.consumed_by_discord_guild_id
    return row


def guild_link_to_domain(row: GuildLinkOrmModel) -> GuildLink:
    return GuildLink(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        discord_guild_id=row.discord_guild_id,
        discord_guild_name=row.discord_guild_name,
        status=GuildLinkStatus(row.status),
        linked_by_user_id=UserId(row.linked_by_user_id),
        linked_at=row.linked_at,
        revoked_at=row.revoked_at,
        revoked_by_user_id=UserId(row.revoked_by_user_id) if row.revoked_by_user_id else None,
        settings=row.settings,
        version=row.version,
    )


def guild_link_to_orm(entity: GuildLink, row: GuildLinkOrmModel | None = None) -> GuildLinkOrmModel:
    row = row or GuildLinkOrmModel(id=entity.id)
    row.org_id = entity.org_id
    row.discord_guild_id = entity.discord_guild_id
    row.discord_guild_name = entity.discord_guild_name
    row.status = entity.status.value
    row.linked_by_user_id = entity.linked_by_user_id
    row.linked_at = entity.linked_at
    row.revoked_at = entity.revoked_at
    row.revoked_by_user_id = entity.revoked_by_user_id
    row.settings = entity.settings
    return row


def audit_log_to_domain(row: DiscordAuditLogOrmModel) -> DiscordAuditLogRecord:
    return DiscordAuditLogRecord(
        id=EntityId(row.id),
        org_id=OrgId(row.org_id),
        category=DiscordAuditEventCategory(row.category),
        action=row.action,
        actor_user_id=UserId(row.actor_user_id) if row.actor_user_id else None,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        metadata=row.metadata_,
        occurred_at=row.occurred_at,
    )


def audit_log_to_orm(entity: DiscordAuditLogRecord) -> DiscordAuditLogOrmModel:
    return DiscordAuditLogOrmModel(
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
