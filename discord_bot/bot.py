"""
Entrypoint. Run with:

    uv run python -m discord_bot.bot

Reads configuration from discord_bot/.env (see config.py) — the bot never
falls back to hardcoded credentials.
"""

from __future__ import annotations

import asyncio
import logging

from discord_bot.client import GuildDeskBot
from discord_bot.config import get_settings

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger("discord_bot.bot")


async def main() -> None:
    settings = get_settings()
    bot = GuildDeskBot(settings)
    async with bot:
        await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _logger.info("shutdown_requested")
