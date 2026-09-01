"""Ticket System value objects.

TicketActor isn't a "value object" in the strict DDD sense of carrying a
validated business rule the way Identity's Email does — it's a small,
immutable, reused shape for "who did this", present on every ticket action.
It exists because there is no Discord-account-to-GuildDesk-user link yet
(a deliberately deferred feature — see the Discord Setup Wizard's Permission
Model decision, carried forward for Ticket System): an actor is *at least
one* of a Discord user id or a GuildDesk UserId, never assumed to be both.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.platform_core.shared_kernel.types import UserId


@dataclass(frozen=True, slots=True)
class TicketActor:
    discord_user_id: str | None = None
    user_id: UserId | None = None

    def __post_init__(self) -> None:
        if self.discord_user_id is None and self.user_id is None:
            raise ValueError("TicketActor requires at least one of discord_user_id/user_id")
