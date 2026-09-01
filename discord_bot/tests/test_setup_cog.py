from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from discord_bot.cogs.setup import SetupCog
from discord_bot.services.api_client import DiscordSetupResult, GuildStatusResult, UnlinkResult
from discord_bot.views.setup_views import UnlinkConfirmView


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.api_client = MagicMock()
    bot.api_client.complete_discord_setup = AsyncMock()
    bot.api_client.get_guild_status = AsyncMock()
    bot.api_client.unlink_guild = AsyncMock()
    return bot


def _interaction(*, guild_id: int = 111, guild_name: str = "Acme HQ", user_id: int = 999) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.guild.name = guild_name
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


async def test_guilddesk_setup_rejects_a_user_without_manage_guild() -> None:
    cog = SetupCog(_bot())
    interaction = _interaction()

    with patch("discord_bot.cogs.setup.has_manage_guild_permission", return_value=False):
        await cog.guilddesk_setup.callback(cog, interaction, code="ABCD1234")

    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "Permission required"
    cog.bot.api_client.complete_discord_setup.assert_not_awaited()


async def test_guilddesk_setup_reports_success_with_org_name() -> None:
    bot = _bot()
    bot.api_client.complete_discord_setup.return_value = DiscordSetupResult(ok=True)
    bot.api_client.get_guild_status.return_value = GuildStatusResult(ok=True, linked=True, org_name="Acme Corp")
    cog = SetupCog(bot)
    interaction = _interaction()

    with patch("discord_bot.cogs.setup.has_manage_guild_permission", return_value=True):
        await cog.guilddesk_setup.callback(cog, interaction, code="ABCD1234")

    interaction.response.defer.assert_awaited_once()
    bot.api_client.complete_discord_setup.assert_awaited_once_with(
        code="ABCD1234", discord_guild_id="111", discord_guild_name="Acme HQ", discord_user_id="999",
    )
    interaction.followup.send.assert_awaited_once()
    _, kwargs = interaction.followup.send.call_args
    assert "Acme Corp" in kwargs["embed"].description


async def test_guilddesk_setup_reports_failure_without_querying_status() -> None:
    bot = _bot()
    bot.api_client.complete_discord_setup.return_value = DiscordSetupResult(ok=False, error_message="This setup code is invalid")
    cog = SetupCog(bot)
    interaction = _interaction()

    with patch("discord_bot.cogs.setup.has_manage_guild_permission", return_value=True):
        await cog.guilddesk_setup.callback(cog, interaction, code="WRONG")

    interaction.followup.send.assert_awaited_once()
    _, kwargs = interaction.followup.send.call_args
    assert kwargs["embed"].title == "Setup failed"
    assert kwargs["embed"].description == "This setup code is invalid"
    bot.api_client.get_guild_status.assert_not_awaited()


async def test_guilddesk_status_rejects_use_outside_a_guild() -> None:
    cog = SetupCog(_bot())
    interaction = _interaction()
    interaction.guild = None

    await cog.guilddesk_status.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once_with(
        "This command can only be used in a server.", ephemeral=True
    )
    cog.bot.api_client.get_guild_status.assert_not_awaited()


async def test_guilddesk_status_reports_linked_guild() -> None:
    bot = _bot()
    bot.api_client.get_guild_status.return_value = GuildStatusResult(ok=True, linked=True, org_name="Acme Corp")
    cog = SetupCog(bot)
    interaction = _interaction()

    await cog.guilddesk_status.callback(cog, interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["embed"].title == "Linked"
    assert "Acme Corp" in kwargs["embed"].description


async def test_guilddesk_status_reports_unlinked_guild() -> None:
    bot = _bot()
    bot.api_client.get_guild_status.return_value = GuildStatusResult(ok=True, linked=False)
    cog = SetupCog(bot)
    interaction = _interaction()

    await cog.guilddesk_status.callback(cog, interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["embed"].title == "Not linked"


async def test_guilddesk_status_reports_backend_failure() -> None:
    bot = _bot()
    bot.api_client.get_guild_status.return_value = GuildStatusResult(ok=False, error_message="Could not reach the GuildDesk API")
    cog = SetupCog(bot)
    interaction = _interaction()

    await cog.guilddesk_status.callback(cog, interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["embed"].title == "Status unavailable"


async def test_guilddesk_unlink_rejects_a_user_without_manage_guild() -> None:
    cog = SetupCog(_bot())
    interaction = _interaction()

    with patch("discord_bot.cogs.setup.has_manage_guild_permission", return_value=False):
        await cog.guilddesk_unlink.callback(cog, interaction)

    _, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "Permission required"
    cog.bot.api_client.unlink_guild.assert_not_awaited()


async def test_guilddesk_unlink_shows_a_confirmation_view_when_permitted() -> None:
    cog = SetupCog(_bot())
    interaction = _interaction()

    with patch("discord_bot.cogs.setup.has_manage_guild_permission", return_value=True):
        await cog.guilddesk_unlink.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], UnlinkConfirmView)
    assert kwargs["ephemeral"] is True
