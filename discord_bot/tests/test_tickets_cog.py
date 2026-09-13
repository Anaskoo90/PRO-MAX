from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from discord_bot.cogs.tickets import TicketsCog
from discord_bot.services.api_client import (
    TicketAttachmentResult,
    TicketCategoriesResult,
    TicketCategoryData,
    TicketCategoryResult,
    TicketData,
    TicketMessageResult,
    TicketResult,
)


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.api_client = MagicMock()
    bot.api_client.create_ticket_category = AsyncMock()
    bot.api_client.list_ticket_categories = AsyncMock()
    bot.api_client.add_ticket_message_by_channel = AsyncMock()
    bot.api_client.upload_ticket_attachment_by_channel = AsyncMock()
    bot.api_client.get_ticket_by_channel = AsyncMock(
        return_value=TicketResult(
            ok=True,
            ticket=TicketData(
                id="ticket",
                ticket_number=1,
                discord_channel_id="222",
                title="Help",
                status="open",
                claimed_by_discord_user_id=None,
            ),
        )
    )
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


async def test_human_ticket_channel_message_is_archived() -> None:
    bot = _bot()
    bot.api_client.add_ticket_message_by_channel.return_value = TicketMessageResult(
        ok=True
    )
    message = MagicMock(spec=discord.Message)
    message.guild = MagicMock(spec=discord.Guild)
    message.author = MagicMock(spec=discord.Member)
    message.author.bot = False
    message.author.id = 333
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 222
    message.id = 444
    message.content = "Need help"
    message.attachments = []

    await TicketsCog(bot).on_message(message)

    bot.api_client.add_ticket_message_by_channel.assert_awaited_once_with(
        discord_channel_id="222",
        body="Need help",
        author_discord_user_id="333",
        discord_message_id="444",
    )


async def test_bot_and_empty_messages_are_not_archived() -> None:
    bot = _bot()
    cog = TicketsCog(bot)
    message = MagicMock(spec=discord.Message)
    message.guild = MagicMock(spec=discord.Guild)
    message.author = MagicMock(spec=discord.Member)
    message.author.bot = True
    message.content = "Bot output"
    message.attachments = []

    await cog.on_message(message)
    message.author.bot = False
    message.content = "   "
    await cog.on_message(message)

    bot.api_client.add_ticket_message_by_channel.assert_not_awaited()


async def test_attachment_only_ticket_message_is_archived() -> None:
    bot = _bot()
    bot.api_client.upload_ticket_attachment_by_channel.return_value = (
        TicketAttachmentResult(ok=True)
    )
    message = MagicMock(spec=discord.Message)
    message.guild = MagicMock(spec=discord.Guild)
    message.author = MagicMock(spec=discord.Member)
    message.author.bot = False
    message.author.id = 333
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 222
    message.id = 444
    message.content = ""
    attachment = MagicMock(spec=discord.Attachment)
    attachment.id = 555
    attachment.size = 5
    attachment.filename = "proof.txt"
    attachment.content_type = "text/plain"
    attachment.read = AsyncMock(return_value=b"proof")
    message.attachments = [attachment]

    await TicketsCog(bot).on_message(message)

    bot.api_client.get_ticket_by_channel.assert_awaited_once_with(
        discord_channel_id="222"
    )
    bot.api_client.upload_ticket_attachment_by_channel.assert_awaited_once_with(
        discord_channel_id="222",
        filename="proof.txt",
        content_type="text/plain",
        content=b"proof",
        uploaded_by_discord_user_id="333",
        discord_attachment_id="555",
    )


async def test_non_ticket_attachment_is_not_downloaded() -> None:
    bot = _bot()
    bot.api_client.get_ticket_by_channel.return_value = TicketResult(
        ok=False, error_message="Ticket was not found"
    )
    message = MagicMock(spec=discord.Message)
    message.guild = MagicMock(spec=discord.Guild)
    message.author = MagicMock(spec=discord.Member)
    message.author.bot = False
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 222
    message.content = ""
    attachment = MagicMock(spec=discord.Attachment)
    attachment.read = AsyncMock()
    message.attachments = [attachment]

    await TicketsCog(bot).on_message(message)

    attachment.read.assert_not_awaited()
    bot.api_client.upload_ticket_attachment_by_channel.assert_not_awaited()
