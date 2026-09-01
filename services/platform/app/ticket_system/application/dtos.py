"""Application-layer DTOs for the Ticket System context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TicketDTO:
    id: UUID
    org_id: UUID
    discord_guild_id: str
    ticket_number: int
    discord_channel_id: str
    title: str
    status: str
    opener_discord_user_id: str | None
    opener_user_id: UUID | None
    claimed_by_discord_user_id: str | None
    claimed_by_user_id: UUID | None
    closed_at: datetime | None
    closed_by_discord_user_id: str | None
    closed_by_user_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TicketCategoryDTO:
    id: UUID
    org_id: UUID
    discord_guild_id: str
    name: str
    discord_category_channel_id: str
    staff_discord_role_ids: list[str]
    is_active: bool
