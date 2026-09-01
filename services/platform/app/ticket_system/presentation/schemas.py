"""Request/response schemas for the Ticket System API. Kept separate from
application-layer DTOs so the wire contract can evolve independently of
the internal DTO shape."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateTicketRequest(BaseModel):
    discord_guild_id: str = Field(min_length=1, max_length=64)
    discord_channel_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    # If omitted, the authenticated caller becomes the ticket's opener —
    # set this when a staff member is opening a ticket on behalf of a
    # Discord user who isn't the one calling this endpoint.
    opener_discord_user_id: str | None = None


class CloseTicketRequest(BaseModel):
    # If omitted, the authenticated caller is recorded as having closed it.
    closed_by_discord_user_id: str | None = None


class ClaimTicketRequest(BaseModel):
    # If omitted, the authenticated caller becomes the claimant.
    claimed_by_discord_user_id: str | None = None


class TransferTicketRequest(BaseModel):
    new_claimant_discord_user_id: str = Field(min_length=1, max_length=64)


class TicketResponse(BaseModel):
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


# --- Dashboard (Phase 2A) ---------------------------------------------------
#
# Deliberately lighter than TicketResponse: a dashboard table row has no use
# for internal GuildDesk user-id cross-references (opener_user_id/
# closed_by_user_id) or fields already implied by dashboard context
# (org_id/discord_guild_id — the caller is already scoped to one org). The
# single-ticket detail endpoint keeps returning the fuller TicketResponse;
# this is the list endpoint's own shape, not a replacement.


class TicketListItemResponse(BaseModel):
    id: UUID
    ticket_number: int
    title: str
    status: str
    discord_channel_id: str
    opener_discord_user_id: str | None
    claimed_by_discord_user_id: str | None
    created_at: datetime
    closed_at: datetime | None


# --- Bot-facing -----------------------------------------------------------


class CreateTicketViaBotRequest(BaseModel):
    discord_guild_id: str = Field(min_length=1, max_length=64)
    discord_channel_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    opener_discord_user_id: str = Field(min_length=1, max_length=64)


class ClaimTicketViaBotRequest(BaseModel):
    claimant_discord_user_id: str = Field(min_length=1, max_length=64)


class TransferTicketViaBotRequest(BaseModel):
    new_claimant_discord_user_id: str = Field(min_length=1, max_length=64)


class CloseTicketViaBotRequest(BaseModel):
    closed_by_discord_user_id: str = Field(min_length=1, max_length=64)


# --- Ticket Categories ------------------------------------------------------


class CreateTicketCategoryRequest(BaseModel):
    discord_guild_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    discord_category_channel_id: str = Field(min_length=1, max_length=64)
    staff_discord_role_ids: list[str] = Field(default_factory=list)


class TicketCategoryResponse(BaseModel):
    id: UUID
    org_id: UUID
    discord_guild_id: str
    name: str
    discord_category_channel_id: str
    staff_discord_role_ids: list[str]
    is_active: bool
