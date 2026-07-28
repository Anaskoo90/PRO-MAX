"""
Placeholder — order-related slash commands are not implemented yet.

This module exists so the cog/extension structure is in place ahead of
time; it defines no commands and is deliberately left out of client.py's
_ENABLED_EXTENSIONS, so loading it has no visible effect until real
commands are added here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from discord_bot.client import GuildDeskBot


class OrdersCog(commands.Cog):
    def __init__(self, bot: "GuildDeskBot") -> None:
        self.bot = bot


async def setup(bot: "GuildDeskBot") -> None:
    await bot.add_cog(OrdersCog(bot))
