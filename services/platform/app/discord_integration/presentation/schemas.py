"""Request/response schemas for the Discord Integration API. Kept separate
from application-layer DTOs so the wire contract can evolve independently
of the internal DTO shape."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SetupTokenResponse(BaseModel):
    raw_code: str
    invite_url: str
    expires_at: datetime


class GuildLinkResponse(BaseModel):
    id: UUID
    org_id: UUID
    discord_guild_id: str
    discord_guild_name: str
    status: str
    linked_by_user_id: UUID
    linked_at: datetime
    revoked_at: datetime | None


# --- Bot-facing ---------------------------------------------------------


class CompleteSetupRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    discord_guild_id: str = Field(min_length=1, max_length=64)
    discord_guild_name: str = Field(min_length=1, max_length=200)
    discord_user_id: str = Field(min_length=1, max_length=64)


class UnlinkGuildRequest(BaseModel):
    discord_user_id: str = Field(min_length=1, max_length=64)


class GuildStatusResponse(BaseModel):
    linked: bool
    org_name: str | None = None
    discord_guild_name: str | None = None
    linked_at: datetime | None = None
