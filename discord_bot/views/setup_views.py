"""Interactive views for the Discord Setup Wizard. UnlinkConfirmView adds
one explicit confirmation step before a destructive unlink call reaches the
backend — the same pattern ticket_views.py's docstring earmarked this
views/ package for, now with a real implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from discord_bot.utils.embeds import build_error_embed, build_status_embed

if TYPE_CHECKING:
    from discord_bot.services.api_client import ApiClient


class UnlinkConfirmView(discord.ui.View):
    def __init__(
        self, *, api_client: "ApiClient", discord_guild_id: str, discord_user_id: str, timeout: float | None = 60.0
    ) -> None:
        super().__init__(timeout=timeout)
        self._api_client = api_client
        self._discord_guild_id = discord_guild_id
        self._discord_user_id = discord_user_id
        # Recorded for tests / callers that want to inspect the outcome
        # rather than only observing the edited message.
        self.confirmed: bool | None = None

    def _disable_all_items(self) -> None:
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Unlink", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        result = await self._api_client.unlink_guild(
            discord_guild_id=self._discord_guild_id, discord_user_id=self._discord_user_id
        )
        self._disable_all_items()
        if result.ok:
            embed = build_status_embed(
                title="Unlinked", healthy=True, description="This server is no longer linked to GuildDesk."
            )
        else:
            embed = build_error_embed(title="Unlink failed", description=result.error_message or "Unknown error")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = False
        self._disable_all_items()
        await interaction.response.edit_message(content="Cancelled — this server remains linked.", embed=None, view=self)
