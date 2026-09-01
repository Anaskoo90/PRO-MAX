"""
Interactive views for the Ticket System: the panel posted in a support
channel (one button per category), the modal collected when a member
opens a ticket, and the persistent per-ticket control view posted in the
resulting channel.

Every control-view callback resolves *which* ticket it's acting on via
GET /discord/tickets/by-channel/{channel_id} rather than embedding a
ticket id in each custom_id — this is what lets TicketControlView be a
single, stateless, globally-shared view (registered once at startup via
bot.add_view, per the design doc's persistence note) instead of one view
instance per ticket.

Staff-only actions (claim/unclaim/transfer/close) are gated by
has_staff_role_permission — deliberately unioned across every category
configured for the guild rather than looked up per-category, since a
Ticket doesn't record which category created it yet (a Phase 1B
simplification, not an oversight: adding that link is a small, isolated
addition for whenever a real caller needs true per-category staff
restriction).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_bot.services.api_client import TicketCategoryData
from discord_bot.utils.embeds import build_error_embed, build_status_embed
from discord_bot.utils.permissions import has_staff_role_permission

if TYPE_CHECKING:
    from discord_bot.client import GuildDeskBot

_logger = logging.getLogger("discord_bot.views.ticket_views")

# Discord's own limits: 5 buttons per row, 5 rows per view. A panel with
# more categories than this falls back to a Select — not implemented in
# Phase 1B (categories beyond the first 5 are simply not shown yet), same
# "grow it when a real guild needs it" discipline as everywhere else.
_MAX_PANEL_BUTTONS = 5

_PERMISSION_REQUIRED_MESSAGE = "You need a configured staff role (or 'Manage Server') to do that."


async def _guild_staff_role_ids(bot: "GuildDeskBot", discord_guild_id: str) -> list[str]:
    result = await bot.api_client.list_ticket_categories(discord_guild_id=discord_guild_id)
    if not result.ok:
        return []
    role_ids: set[str] = set()
    for category in result.categories:
        role_ids.update(category.staff_discord_role_ids)
    return list(role_ids)


class TicketFormModal(discord.ui.Modal):
    """One fixed field for Phase 1B — a per-category custom form
    (TicketTemplate) is a later-phase addition."""

    description = discord.ui.TextInput(
        label="What do you need help with?", style=discord.TextStyle.paragraph, max_length=1000,
    )

    def __init__(self, *, bot: "GuildDeskBot", category: TicketCategoryData) -> None:
        super().__init__(title=f"New {category.name} Ticket"[:45])
        self._bot = bot
        self._category = category

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        category_channel = guild.get_channel(int(self._category.discord_category_channel_id))
        try:
            channel = await guild.create_text_channel(
                name=f"{self._category.name}-{interaction.user.name}"[:100], category=category_channel,
                overwrites=overwrites,
            )
        except discord.HTTPException:
            await interaction.followup.send(
                embed=build_error_embed(
                    title="Could not open ticket",
                    description="Discord wouldn't let me create a channel for this ticket. Please tell a staff member.",
                )
            )
            _logger.warning("ticket_channel_creation_failed", exc_info=True)
            return

        result = await self._bot.api_client.create_ticket(
            discord_guild_id=str(guild.id), discord_channel_id=str(channel.id),
            title=f"{self._category.name}: {self.description.value}"[:200],
            opener_discord_user_id=str(interaction.user.id),
        )
        if not result.ok:
            await channel.delete(reason="Ticket creation failed on the backend")
            await interaction.followup.send(
                embed=build_error_embed(title="Could not open ticket", description=result.error_message or "Unknown error")
            )
            return

        embed = build_status_embed(
            title=f"Ticket #{result.ticket.ticket_number}", healthy=True, description=self.description.value,
        )
        await channel.send(embed=embed, view=TicketControlView(bot=self._bot))
        await interaction.followup.send(f"Your ticket has been created: {channel.mention}")


class _CategoryButton(discord.ui.Button):
    def __init__(self, *, bot: "GuildDeskBot", category: TicketCategoryData) -> None:
        super().__init__(label=category.name[:80], style=discord.ButtonStyle.primary)
        self._bot = bot
        self._category = category

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TicketFormModal(bot=self._bot, category=self._category))


class TicketPanelView(discord.ui.View):
    """Not deeply restart-persistent by design for Phase 1B: rebuilding
    this view exactly (one guild's current category set) requires
    re-fetching categories, so /ticket-panel-post is meant to be re-run
    after a restart rather than the bot re-registering every guild's
    panel automatically — a rare admin action, unlike ticket control
    views, which must keep working forever once posted."""

    def __init__(self, *, bot: "GuildDeskBot", categories: list[TicketCategoryData]) -> None:
        super().__init__(timeout=None)
        for category in categories[:_MAX_PANEL_BUTTONS]:
            self.add_item(_CategoryButton(bot=bot, category=category))


class TicketTransferSelectView(discord.ui.View):
    """Ephemeral, short-lived view shown after pressing "Transfer" —
    Discord buttons can't take arbitrary parameters, so picking the new
    claimant needs its own small interaction step."""

    def __init__(self, *, bot: "GuildDeskBot", ticket_id: str, timeout: float | None = 60.0) -> None:
        super().__init__(timeout=timeout)
        self._bot = bot
        self._ticket_id = ticket_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select the new claimant")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
        new_claimant = select.values[0]
        result = await self._bot.api_client.transfer_ticket(
            ticket_id=self._ticket_id, new_claimant_discord_user_id=str(new_claimant.id),
        )
        for item in self.children:
            item.disabled = True
        if not result.ok:
            await interaction.response.edit_message(
                content=None, embed=build_error_embed(title="Transfer failed", description=result.error_message or "Unknown error"),
                view=self,
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=build_status_embed(title="Ticket transferred", healthy=True, description=f"Now claimed by {new_claimant.mention}."),
            view=self,
        )


class TicketControlView(discord.ui.View):
    """Persistent — registered once at bot startup (client.py's
    setup_hook calls bot.add_view(TicketControlView(bot))) and sent fresh
    into every new ticket channel; both instances handle interactions for
    every ticket channel identically since no per-ticket state is held
    here."""

    def __init__(self, *, bot: "GuildDeskBot") -> None:
        super().__init__(timeout=None)
        self._bot = bot

    async def _resolve_ticket(self, interaction: discord.Interaction):
        result = await self._bot.api_client.get_ticket_by_channel(discord_channel_id=str(interaction.channel_id))
        if not result.ok:
            await interaction.response.send_message(
                embed=build_error_embed(title="Ticket not found", description=result.error_message or "Unknown error"),
                ephemeral=True,
            )
            return None
        return result.ticket

    async def _assert_staff(self, interaction: discord.Interaction) -> bool:
        staff_role_ids = await _guild_staff_role_ids(self._bot, str(interaction.guild.id))
        if has_staff_role_permission(interaction, staff_role_ids):
            return True
        await interaction.response.send_message(
            embed=build_error_embed(title="Permission required", description=_PERMISSION_REQUIRED_MESSAGE),
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="ticket_control:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._assert_staff(interaction):
            return
        ticket = await self._resolve_ticket(interaction)
        if ticket is None:
            return
        result = await self._bot.api_client.claim_ticket(
            ticket_id=ticket.id, claimant_discord_user_id=str(interaction.user.id)
        )
        if not result.ok:
            await interaction.response.send_message(
                embed=build_error_embed(title="Claim failed", description=result.error_message or "Unknown error"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(f"🎫 Claimed by {interaction.user.mention}.")

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, custom_id="ticket_control:unclaim")
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._assert_staff(interaction):
            return
        ticket = await self._resolve_ticket(interaction)
        if ticket is None:
            return
        result = await self._bot.api_client.unclaim_ticket(ticket_id=ticket.id)
        if not result.ok:
            await interaction.response.send_message(
                embed=build_error_embed(title="Unclaim failed", description=result.error_message or "Unknown error"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message("🔓 Ticket unclaimed.")

    @discord.ui.button(label="Transfer", style=discord.ButtonStyle.primary, custom_id="ticket_control:transfer")
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._assert_staff(interaction):
            return
        ticket = await self._resolve_ticket(interaction)
        if ticket is None:
            return
        await interaction.response.send_message(
            "Select the new claimant:", view=TicketTransferSelectView(bot=self._bot, ticket_id=ticket.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket_control:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._assert_staff(interaction):
            return
        ticket = await self._resolve_ticket(interaction)
        if ticket is None:
            return
        result = await self._bot.api_client.close_ticket(
            ticket_id=ticket.id, closed_by_discord_user_id=str(interaction.user.id)
        )
        if not result.ok:
            await interaction.response.send_message(
                embed=build_error_embed(title="Close failed", description=result.error_message or "Unknown error"),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=build_status_embed(title="Ticket closed", healthy=True, description="This ticket has been closed.")
        )
