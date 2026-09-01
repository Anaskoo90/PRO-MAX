"""
Bot service authentication: a single static shared secret between the one
trusted GuildDeskBot process and this backend — deliberately not JWT
(there is no human user on this call path) and not a per-guild credential
(the bot has nowhere durable to persist one; see the Discord Setup Wizard
design doc's Permission Model section for the full rationale). Proves only
"this HTTP call came from our bot process" — nothing about which guild or
which Discord user, which is why complete_setup/unlink_guild_by_discord_id
still layer their own checks (a one-time setup code; the bot's own Discord
"Manage Server" gate) on top of this.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header

from app.discord_integration.presentation import deps
from app.platform_core.errors.api_exceptions import UnauthorizedError


def require_bot_service_secret(
    x_guilddesk_bot_secret: str | None = Header(default=None),
    expected: str = Depends(deps.get_bot_service_secret),
) -> None:
    if not x_guilddesk_bot_secret or not hmac.compare_digest(x_guilddesk_bot_secret, expected):
        raise UnauthorizedError("Missing or invalid bot service secret")
