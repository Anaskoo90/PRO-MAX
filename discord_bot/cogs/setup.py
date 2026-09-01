"""
/guilddesk-setup, /guilddesk-status, /guilddesk-unlink — the Discord Setup
Wizard's bot-side commands. Binds this Discord guild to a GuildDesk
organization via a one-time setup code generated in the GuildDesk web app
(POST /organizations/{org_id}/discord/setup-token on the backend).

Authorization here is Discord's own "Manage Server" permission
(utils/permissions.py) plus the backend's bot shared secret (sent by every
ApiClient call) — not GuildDesk RBAC, since there's no Discord-account-to-
GuildDesk-user link yet. See the Discord Setup Wizard design doc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_bot.utils.embeds import build_error_embed, build_status_embed
from discord_bot.utils.permissions import has_manage_guild_permission
from discord_bot.views.setup_views import UnlinkConfirmView

if TYPE_CHECKING:
    from discord_bot.client import GuildDeskBot

_PERMISSION_REQUIRED_MESSAGE = "You need the 'Manage Server' permission in this server to use this command."


class SetupCog(commands.Cog):
    def __init__(self, bot: "GuildDeskBot") -> None:
        self.bot = bot

    @app_commands.command(name="guilddesk-setup", description="Link this Discord server to a GuildDesk organization")
    @app_commands.describe(code="The setup code shown in your GuildDesk organization's Discord settings")
    async def guilddesk_setup(self, interaction: discord.Interaction, code: str) -> None:
        if not has_manage_guild_permission(interaction):
            await interaction.response.send_message(
                embed=build_error_embed(title="Permission required", description=_PERMISSION_REQUIRED_MESSAGE),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        guild = interaction.guild
        result = await self.bot.api_client.complete_discord_setup(
            code=code, discord_guild_id=str(guild.id), discord_guild_name=guild.name,
            discord_user_id=str(interaction.user.id),
        )
        if not result.ok:
            await interaction.followup.send(
                embed=build_error_embed(title="Setup failed", description=result.error_message or "Unknown error")
            )
            return

        status = await self.bot.api_client.get_guild_status(discord_guild_id=str(guild.id))
        org_label = status.org_name if status.ok and status.org_name else "your GuildDesk organization"
        await interaction.followup.send(
            embed=build_status_embed(
                title="Server linked", healthy=True, description=f"This server is now linked to **{org_label}**."
            )
        )

    @app_commands.command(
        name="guilddesk-status", description="Show whether this server is linked to a GuildDesk organization"
    )
    async def guilddesk_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        result = await self.bot.api_client.get_guild_status(discord_guild_id=str(interaction.guild.id))
        if not result.ok:
            await interaction.response.send_message(
                embed=build_error_embed(title="Status unavailable", description=result.error_message or "Unknown error")
            )
            return

        if result.linked:
            embed = build_status_embed(
                title="Linked", healthy=True,
                description=f"This server is linked to **{result.org_name or 'a GuildDesk organization'}**.",
            )
        else:
            embed = build_status_embed(
                title="Not linked", healthy=False,
                description="This server is not linked to a GuildDesk organization yet. Run `/guilddesk-setup` to link it.",
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="guilddesk-unlink", description="Unlink this Discord server from its GuildDesk organization"
    )
    async def guilddesk_unlink(self, interaction: discord.Interaction) -> None:
        if not has_manage_guild_permission(interaction):
            await interaction.response.send_message(
                embed=build_error_embed(title="Permission required", description=_PERMISSION_REQUIRED_MESSAGE),
                ephemeral=True,
            )
            return

        view = UnlinkConfirmView(
            api_client=self.bot.api_client, discord_guild_id=str(interaction.guild.id),
            discord_user_id=str(interaction.user.id),
        )
        await interaction.response.send_message(
            "Are you sure you want to unlink this server from GuildDesk?", view=view, ephemeral=True
        )


async def setup(bot: "GuildDeskBot") -> None:
    await bot.add_cog(SetupCog(bot))
