"""
/ticket-panel-post, /ticket-category-create — the Ticket System's bot-side
setup commands. Claim/Unclaim/Transfer/Close themselves are not separate
slash commands: TicketControlView (views/ticket_views.py) is their one
interface, posted automatically into every ticket channel at creation
time.

Authorization here is Discord's own "Manage Server" permission (same gate
discord_bot/cogs/setup.py already uses) — category configuration is an
admin action, not a staff-role-gated one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.utils.embeds import build_error_embed, build_status_embed
from discord_bot.utils.permissions import has_manage_guild_permission
from discord_bot.views.ticket_views import TicketPanelView

if TYPE_CHECKING:
    from discord_bot.client import GuildDeskBot

_PERMISSION_REQUIRED_MESSAGE = "You need the 'Manage Server' permission in this server to use this command."


class TicketsCog(commands.Cog):
    def __init__(self, bot: "GuildDeskBot") -> None:
        self.bot = bot

    @app_commands.command(
        name="ticket-category-create", description="Create a ticket category for this server's support panel"
    )
    @app_commands.describe(
        name="Category name shown on the panel button",
        category_channel="The Discord channel category new ticket channels should be created under",
        staff_role="Discord role allowed to claim/manage tickets opened in this category",
    )
    async def ticket_category_create(
        self, interaction: discord.Interaction, name: str, category_channel: discord.CategoryChannel,
        staff_role: discord.Role,
    ) -> None:
        if not has_manage_guild_permission(interaction):
            await interaction.response.send_message(
                embed=build_error_embed(title="Permission required", description=_PERMISSION_REQUIRED_MESSAGE),
                ephemeral=True,
            )
            return

        result = await self.bot.api_client.create_ticket_category(
            discord_guild_id=str(interaction.guild.id), name=name,
            discord_category_channel_id=str(category_channel.id), staff_discord_role_ids=[str(staff_role.id)],
        )
        if not result.ok:
            await interaction.response.send_message(
                embed=build_error_embed(title="Could not create category", description=result.error_message or "Unknown error"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=build_status_embed(
                title="Category created", healthy=True,
                description=f"**{name}** tickets will be created under {category_channel.mention}.",
            ),
            ephemeral=True,
        )

    @app_commands.command(name="ticket-panel-post", description="Post the ticket panel for this server in this channel")
    async def ticket_panel_post(self, interaction: discord.Interaction) -> None:
        if not has_manage_guild_permission(interaction):
            await interaction.response.send_message(
                embed=build_error_embed(title="Permission required", description=_PERMISSION_REQUIRED_MESSAGE),
                ephemeral=True,
            )
            return

        result = await self.bot.api_client.list_ticket_categories(discord_guild_id=str(interaction.guild.id))
        if not result.ok:
            await interaction.response.send_message(
                embed=build_error_embed(title="Could not load categories", description=result.error_message or "Unknown error"),
                ephemeral=True,
            )
            return
        if not result.categories:
            await interaction.response.send_message(
                embed=build_error_embed(
                    title="No ticket categories configured",
                    description="Run `/ticket-category-create` first to add at least one category.",
                ),
                ephemeral=True,
            )
            return

        embed = build_status_embed(
            title="Need help?", healthy=True, description="Click a button below to open a ticket.",
        )
        await interaction.channel.send(embed=embed, view=TicketPanelView(bot=self.bot, categories=result.categories))
        await interaction.response.send_message("Panel posted.", ephemeral=True)


async def setup(bot: "GuildDeskBot") -> None:
    await bot.add_cog(TicketsCog(bot))
