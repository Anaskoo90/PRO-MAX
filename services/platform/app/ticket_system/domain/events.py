"""Ticket System domain events — in-process only, mirroring the shape/
conventions of every prior context's domain events exactly. Names match
the Domain Events Catalog stub (docs/.../Domain-Events-Catalog.md) exactly
for TicketOpened/TicketClosed; later phases extend this set the same way
every other context's event set grew beyond its own docs-pack stub."""

from __future__ import annotations

from uuid import UUID

from app.platform_core.events.contracts import DomainEvent


class TicketOpened(DomainEvent):
    event_type = "ticket_system.ticket_opened"
    org_id: UUID
    discord_guild_id: str
    ticket_number: int


class TicketClosed(DomainEvent):
    event_type = "ticket_system.ticket_closed"
    org_id: UUID


class TicketClaimed(DomainEvent):
    event_type = "ticket_system.ticket_claimed"
    org_id: UUID
    claimed_by_discord_user_id: str | None


class TicketUnclaimed(DomainEvent):
    event_type = "ticket_system.ticket_unclaimed"
    org_id: UUID


class TicketTransferred(DomainEvent):
    event_type = "ticket_system.ticket_transferred"
    org_id: UUID
    claimed_by_discord_user_id: str | None
