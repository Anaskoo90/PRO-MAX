"""
Ticket System domain entities.

Ticket is the aggregate root (EventRecordingMixin). Phase 1A shipped a
narrow OPEN/CLOSED vocabulary; Phase 1B adds CLAIMED plus claim/unclaim/
transfer as new methods on this same class — the same "grow the entity as
the feature grows" discipline continues (see Alembic migration 0009's
docstring for the matching schema change).

TicketCategory is a separate, much simpler aggregate: the Discord "panel
button" configuration for one category of ticket within one guild. It has
no events of its own (nothing yet reacts to category changes) — same
convention as EmailVerificationToken/PasswordResetToken, a plain entity
with lifecycle managed entirely by its own application service.

Plain Python classes, not pydantic/SQLAlchemy models — same dependency
rule as every other context (ADR-005..009): domain depends only on
shared_kernel/events.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from app.platform_core.events.domain_event import EventRecordingMixin
from app.platform_core.shared_kernel.types import EntityId, OrgId, UserId
from app.platform_core.shared_kernel.utils import new_uuid7, utcnow
from app.ticket_system.domain.events import (
    TicketClaimed,
    TicketClosed,
    TicketOpened,
    TicketTransferred,
    TicketUnclaimed,
)
from app.ticket_system.domain.exceptions import InvalidTicketTransitionError
from app.ticket_system.domain.value_objects import TicketActor


class TicketStatus(StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"
    CLOSED = "closed"


class Ticket(EventRecordingMixin):
    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        discord_guild_id: str,
        ticket_number: int,
        discord_channel_id: str,
        title: str,
        status: TicketStatus,
        opener_discord_user_id: str | None = None,
        opener_user_id: UserId | None = None,
        claimed_by_discord_user_id: str | None = None,
        claimed_by_user_id: UserId | None = None,
        closed_at: datetime | None = None,
        closed_by_discord_user_id: str | None = None,
        closed_by_user_id: UserId | None = None,
        created_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.discord_guild_id = discord_guild_id
        self.ticket_number = ticket_number
        self.discord_channel_id = discord_channel_id
        self.title = title
        self.status = status
        self.opener_discord_user_id = opener_discord_user_id
        self.opener_user_id = opener_user_id
        self.claimed_by_discord_user_id = claimed_by_discord_user_id
        self.claimed_by_user_id = claimed_by_user_id
        self.closed_at = closed_at
        self.closed_by_discord_user_id = closed_by_discord_user_id
        self.closed_by_user_id = closed_by_user_id
        # Phase 2A: needed for the dashboard's sort-by/display-creation-date
        # requirement — not generic bookkeeping, an actual, present need
        # (same reasoning GuildLink.linked_at / Session.created_at already
        # set this kind of timestamp explicitly in create() rather than
        # relying solely on the ORM's server_default).
        self.created_at = created_at or utcnow()
        self.version = version

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        discord_guild_id: str,
        ticket_number: int,
        discord_channel_id: str,
        title: str,
        opener: TicketActor,
    ) -> "Ticket":
        # No "at least one identity set" check here: TicketActor's own
        # __post_init__ already guarantees that for every instance that
        # exists, so a second check here would be unreachable.
        ticket = cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            discord_guild_id=discord_guild_id,
            ticket_number=ticket_number,
            discord_channel_id=discord_channel_id,
            title=title,
            status=TicketStatus.OPEN,
            opener_discord_user_id=opener.discord_user_id,
            opener_user_id=opener.user_id,
        )
        ticket.record_event(
            TicketOpened(
                aggregate_id=ticket.id, org_id=org_id, discord_guild_id=discord_guild_id,
                ticket_number=ticket_number,
            )
        )
        return ticket

    def is_open(self) -> bool:
        return self.status == TicketStatus.OPEN

    def is_claimed(self) -> bool:
        return self.status == TicketStatus.CLAIMED

    def claim(self, *, claimant: TicketActor) -> None:
        if self.status != TicketStatus.OPEN:
            raise InvalidTicketTransitionError(self.status.value, TicketStatus.CLAIMED.value)

        self.status = TicketStatus.CLAIMED
        self.claimed_by_discord_user_id = claimant.discord_user_id
        self.claimed_by_user_id = claimant.user_id
        self.record_event(
            TicketClaimed(aggregate_id=self.id, org_id=self.org_id, claimed_by_discord_user_id=claimant.discord_user_id)
        )

    def unclaim(self) -> None:
        if self.status != TicketStatus.CLAIMED:
            raise InvalidTicketTransitionError(self.status.value, TicketStatus.OPEN.value)

        self.status = TicketStatus.OPEN
        self.claimed_by_discord_user_id = None
        self.claimed_by_user_id = None
        self.record_event(TicketUnclaimed(aggregate_id=self.id, org_id=self.org_id))

    def transfer(self, *, new_claimant: TicketActor) -> None:
        """Reassigns an already-claimed ticket to someone else. An
        unclaimed ticket has no one to transfer *from* — use claim()
        instead, same reasoning as Discord Integration's relink() only
        being reachable from a revoked (not never-linked) GuildLink."""
        if self.status != TicketStatus.CLAIMED:
            raise InvalidTicketTransitionError(self.status.value, TicketStatus.CLAIMED.value)

        self.claimed_by_discord_user_id = new_claimant.discord_user_id
        self.claimed_by_user_id = new_claimant.user_id
        self.record_event(
            TicketTransferred(
                aggregate_id=self.id, org_id=self.org_id, claimed_by_discord_user_id=new_claimant.discord_user_id,
            )
        )

    def close(self, *, actor: TicketActor) -> None:
        if self.status == TicketStatus.CLOSED:
            raise InvalidTicketTransitionError(self.status.value, TicketStatus.CLOSED.value)

        self.status = TicketStatus.CLOSED
        self.closed_at = utcnow()
        self.closed_by_discord_user_id = actor.discord_user_id
        self.closed_by_user_id = actor.user_id
        self.record_event(TicketClosed(aggregate_id=self.id, org_id=self.org_id))


class TicketCategory(EventRecordingMixin):
    """The Discord "panel button" configuration for one category of ticket
    within one guild — deliberately minimal for Phase 1B: no per-category
    form (TicketTemplate) or SLA/module settings yet, those are later-
    phase additions once something actually reads them."""

    def __init__(
        self,
        *,
        id: EntityId,
        org_id: OrgId,
        discord_guild_id: str,
        name: str,
        discord_category_channel_id: str,
        staff_discord_role_ids: list[str],
        is_active: bool = True,
        version: int = 1,
    ) -> None:
        super().__init__()
        self.id = id
        self.org_id = org_id
        self.discord_guild_id = discord_guild_id
        self.name = name
        self.discord_category_channel_id = discord_category_channel_id
        self.staff_discord_role_ids = staff_discord_role_ids
        self.is_active = is_active
        self.version = version

    @classmethod
    def create(
        cls,
        *,
        org_id: OrgId,
        discord_guild_id: str,
        name: str,
        discord_category_channel_id: str,
        staff_discord_role_ids: list[str],
    ) -> "TicketCategory":
        return cls(
            id=EntityId(new_uuid7()),
            org_id=org_id,
            discord_guild_id=discord_guild_id,
            name=name,
            discord_category_channel_id=discord_category_channel_id,
            staff_discord_role_ids=staff_discord_role_ids,
        )
