"""Application-layer DTOs for the Discord Integration context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SetupTokenDTO:
    raw_code: str
    invite_url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class GuildLinkDTO:
    id: UUID
    org_id: UUID
    discord_guild_id: str
    discord_guild_name: str
    status: str
    linked_by_user_id: UUID
    linked_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class GuildLinkStatusDTO:
    linked: bool
    org_name: str | None = None
    discord_guild_name: str | None = None
    linked_at: datetime | None = None
