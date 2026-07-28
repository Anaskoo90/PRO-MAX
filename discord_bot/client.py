"""
The bot's Client subclass — owns the shared ApiClient instance and the
cog/command-tree lifecycle. Slash-command-only: `command_prefix` is set to
`commands.when_mentioned` purely because `commands.Bot` requires one; no
text-prefix commands are defined anywhere in this project.
"""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from discord_bot.config import DiscordBotSettings
from discord_bot.services.api_client import ApiClient

_logger = logging.getLogger("discord_bot.client")

# One cog per line, loaded in setup_hook — tickets/orders/wallet exist only
# as architectural placeholders for now (see their module docstrings) and
# are deliberately left out of this list until they're actually implemented.
_ENABLED_EXTENSIONS: tuple[str, ...] = ("discord_bot.cogs.ping",)


class GuildDeskBot(commands.Bot):
    def __init__(self, settings: DiscordBotSettings) -> None:
        intents = discord.Intents.default()
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            application_id=settings.discord_application_id,
        )
        self._settings = settings
        self.api_client = ApiClient(base_url=settings.api_url)

    async def setup_hook(self) -> None:
        for extension in _ENABLED_EXTENSIONS:
            await self.load_extension(extension)

        if self._settings.discord_guild_id:
            # Per-guild sync propagates near-instantly — the standard
            # choice for development. A global sync (the else branch) can
            # take up to an hour for Discord to roll out to every guild.
            guild = discord.Object(id=self._settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            _logger.info("synced_guild_commands", extra={"guild_id": self._settings.discord_guild_id, "count": len(synced)})
        else:
            synced = await self.tree.sync()
            _logger.info("synced_global_commands", extra={"count": len(synced)})

    async def close(self) -> None:
        await self.api_client.aclose()
        await super().close()
