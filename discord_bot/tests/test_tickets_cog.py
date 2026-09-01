from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from discord_bot.cogs.tickets import TicketsCog
from discord_bot.services.api_client import (
    TicketCategoriesResult,
    TicketCategoryData,
    TicketCategoryResult,
)


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.api_client = MagicMock()
    bot.api_client.create_ticket_category = AsyncMock()
    bot.api_client.list_ticket_categories = AsyncMock()
    return bot


def _interaction(*, guild_id: int = 111) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.user = MagicMock(spec=discord.Member)
    interaction.response = AsyncMock()
    interaction.channel = MagicMock()
    interaction.channel.send = AsyncMock()
    return interaction


async def test_category_create_rejects_a_user_without_manage_guild() -> None:
    cog = TicketsCog(_bot())
    interaction = _interaction()
    category_channel = MagicMock(spec=discord.CategoryChannel)
    staff_role = MagicMock(spec=discord.Role)

    with patch("discord_bot.cogs.tickets.has_manage_guild_permission", return_value=False):
        await cog.ticket_category_create.callback(cog, interaction, "Billing", category_channel, staff_role)

    interaction.response.send_message.assert_awaited_once()
    cog.bot.api_client.create_ticket_category.assert_not_awaited()


async def test_category_create_succeeds_when_permitted() -> None:
    bot = _bot()
    bot.api_client.create_ticket_category.return_value = TicketCategoryResult(
        ok=True, category=TicketCategoryData(id="1", name="Billing", discord_category_channel_id="10")
    )
    cog = TicketsCog(bot)
    interaction = _interaction()
    category_channel = MagicMock(spec=discord.CategoryChannel)
    category_channel.id = 10
    category_channel.mention = "#billing-category"
    staff_role = MagicMock(spec=discord.Role)
    staff_role.id = 555

    with patch("discord_bot.cogs.tickets.has_manage_guild_permission", return_value=True):
        await cog.ticket_category_create.callback(cog, interaction, "Billing", category_channel, staff_role)

    bot.api_client.create_ticket_category.assert_awaited_once_with(
        discord_guild_id="111", name="Billing", discord_category_channel_id="10", staff_discord_role_ids=["555"],
    )
    interaction.response.send_message.assert_awaited_once()


async def test_panel_post_rejects_a_user_without_manage_guild() -> None:
    cog = TicketsCog(_bot())
    interaction = _interaction()

    with patch("discord_bot.cogs.tickets.has_manage_guild_permission", return_value=False):
        await cog.ticket_panel_post.callback(cog, interaction)

    cog.bot.api_client.list_ticket_categories.assert_not_awaited()


async def test_panel_post_rejects_when_no_categories_exist() -> None:
    bot = _bot()
    bot.api_client.list_ticket_categories.return_value = TicketCategoriesResult(ok=True, categories=[])
    cog = TicketsCog(bot)
    interaction = _interaction()

    with patch("discord_bot.cogs.tickets.has_manage_guild_permission", return_value=True):
        await cog.ticket_panel_post.callback(cog, interaction)

    interaction.channel.send.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once()


async def test_panel_post_sends_the_panel_when_categories_exist() -> None:
    bot = _bot()
    bot.api_client.list_ticket_categories.return_value = TicketCategoriesResult(
        ok=True, categories=[TicketCategoryData(id="1", name="Billing", discord_category_channel_id="10")]
    )
    cog = TicketsCog(bot)
    interaction = _interaction()

    with patch("discord_bot.cogs.tickets.has_manage_guild_permission", return_value=True):
        await cog.ticket_panel_post.callback(cog, interaction)

    interaction.channel.send.assert_awaited_once()
    interaction.response.send_message.assert_awaited_once()
