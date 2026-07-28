"""/ping — checks whether the GuildDesk API is reachable and healthy."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.utils.embeds import build_status_embed

if TYPE_CHECKING:
    from discord_bot.client import GuildDeskBot


class PingCog(commands.Cog):
    def __init__(self, bot: "GuildDeskBot") -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check whether the GuildDesk API is online")
    async def ping(self, interaction: discord.Interaction) -> None:
        healthy = await self.bot.api_client.check_health()
        title = "✅ GuildDesk API Online" if healthy else "❌ GuildDesk API Offline"
        await interaction.response.send_message(embed=build_status_embed(title=title, healthy=healthy))


async def setup(bot: "GuildDeskBot") -> None:
    await bot.add_cog(PingCog(bot))
