"""
Discord Integration domain entities.

GuildSetupToken is a plain entity (no events of its own), same shape as
Identity's EmailVerificationToken/PasswordResetToken: expiry/consumption
state is exposed via is_expired()/is_consumed(), but checked by the
application layer before acting on it, not enforced here.

GuildLink is the aggregate root (EventRecordingMixin) — the durable record
of "this Discord guild belongs to this organization". A guild can only be
ACTIVE under one organization at a time (enforced by the repository's
partial-unique index, mirrored by the application layer's own check before
calling create()/relink()); relink() reclaims a previously REVOKED row
instead of creating a new one, preserving history under one id.

Plain Python classes, not pydantic/SQLAlchemy models — same dependency
rule as every other context (ADR-005..009): domain depends only on
shared_kernel/events.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.discord_integration.domain.events import GuildLinked, GuildRelinked, GuildUnlinked
from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow


class GuildSetupToken:
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        requested_by_user_id: UserId,
        token_hash: str,
        created_at: datetime,
        expires_at: datetime,
        consumed_at: datetime | None = None,
        consumed_by_discord_guild_id: str | None = None,
    ) -> None:
        self.id = id
        self.org_id = org_id
        self.requested_by_user_id = requested_by_user_id
        self.token_hash = token_hash
        self.created_at = created_at
        self.expires_at = expires_at
        self.consumed_at = consumed_at
        self.consumed_by_discord_guild_id = consumed_by_discord_guild_id

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        requested_by_user_id: UserId,
        token_hash: str,
        ttl: timedelta = timedelta(minutes=15),
    ) -> "GuildSetupToken":
        now = utcnow()
        return cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            requested_by_user_id=requested_by_user_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=now + ttl,
        )

    def is_expired(self) -> bool:
        return utcnow() > self.expires_at

    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def consume(self, *, discord_guild_id: str) -> None:
        self.consumed_at = utcnow()
        self.consumed_by_discord_guild_id = discord_guild_id


class GuildLinkStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class GuildLink(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        discord_guild_id: str,
        discord_guild_name: str,
        status: GuildLinkStatus,
        linked_by_user_id: UserId,
        linked_at: datetime,
        revoked_at: datetime | None = None,
        revoked_by_user_id: UserId | None = None,
        settings: dict[str, Any] | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.discord_guild_id = discord_guild_id
        self.discord_guild_name = discord_guild_name
        self.status = status
        self.linked_by_user_id = linked_by_user_id
        self.linked_at = linked_at
        self.revoked_at = revoked_at
        self.revoked_by_user_id = revoked_by_user_id
        self.settings = settings or {}
        self.version = version

    @classmethod
    def create(
        cls, *, org_id: OrgId, discord_guild_id: str, discord_guild_name: str, linked_by_user_id: UserId
    ) -> "GuildLink":
        link = cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            discord_guild_id=discord_guild_id,
            discord_guild_name=discord_guild_name,
            status=GuildLinkStatus.ACTIVE,
            linked_by_user_id=linked_by_user_id,
            linked_at=utcnow(),
        )
        link.record_event(
            GuildLinked(aggregate_id=link.id, org_id=org_id, discord_guild_id=discord_guild_id)
        )
        return link

    def is_active(self) -> bool:
        return self.status == GuildLinkStatus.ACTIVE

    def relink(self, *, org_id: OrgId, discord_guild_name: str, linked_by_user_id: UserId) -> None:
        """Reclaims a REVOKED row for a (possibly different) organization,
        preserving the row's id/history rather than inserting a new one."""
        self.org_id = org_id
        self.discord_guild_name = discord_guild_name
        self.status = GuildLinkStatus.ACTIVE
        self.linked_by_user_id = linked_by_user_id
        self.linked_at = utcnow()
        self.revoked_at = None
        self.revoked_by_user_id = None
        self.record_event(
            GuildRelinked(aggregate_id=self.id, org_id=org_id, discord_guild_id=self.discord_guild_id)
        )

    def revoke(self, *, revoked_by_user_id: UserId | None) -> None:
        self.status = GuildLinkStatus.REVOKED
        self.revoked_at = utcnow()
        self.revoked_by_user_id = revoked_by_user_id
        self.record_event(
            GuildUnlinked(aggregate_id=self.id, org_id=self.org_id, discord_guild_id=self.discord_guild_id)
        )
