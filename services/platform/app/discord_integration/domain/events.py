"""Discord Integration domain events — in-process only, mirroring the
shape/conventions of every prior context's domain events exactly."""

from __future__ import annotations

from uuid import UUID

from app.platform_core.events.contracts import DomainEvent


class GuildLinked(DomainEvent):
    event_type = "discord_integration.guild_linked"
    org_id: UUID
    discord_guild_id: str


class GuildRelinked(DomainEvent):
    event_type = "discord_integration.guild_relinked"
    org_id: UUID
    discord_guild_id: str


class GuildUnlinked(DomainEvent):
    event_type = "discord_integration.guild_unlinked"
    org_id: UUID
    discord_guild_id: str
