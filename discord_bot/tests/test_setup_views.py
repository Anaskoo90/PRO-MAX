from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord

from discord_bot.services.api_client import UnlinkResult
from discord_bot.views.setup_views import UnlinkConfirmView


def _interaction() -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    return interaction


def _api_client(unlink_result: UnlinkResult) -> MagicMock:
    client = MagicMock()
    client.unlink_guild = AsyncMock(return_value=unlink_result)
    return client


async def test_confirm_button_unlinks_and_shows_success_embed() -> None:
    api_client = _api_client(UnlinkResult(ok=True))
    view = UnlinkConfirmView(api_client=api_client, discord_guild_id="111", discord_user_id="999")
    interaction = _interaction()

    await view.confirm.callback(interaction)

    api_client.unlink_guild.assert_awaited_once_with(discord_guild_id="111", discord_user_id="999")
    assert view.confirmed is True
    assert all(item.disabled for item in view.children)
    interaction.response.edit_message.assert_awaited_once()
    _, kwargs = interaction.response.edit_message.call_args
    assert kwargs["embed"].title == "Unlinked"


async def test_confirm_button_shows_error_embed_on_failure() -> None:
    api_client = _api_client(UnlinkResult(ok=False, error_message="Discord guild '111' is not linked to any organization"))
    view = UnlinkConfirmView(api_client=api_client, discord_guild_id="111", discord_user_id="999")
    interaction = _interaction()

    await view.confirm.callback(interaction)

    assert view.confirmed is True
    interaction.response.edit_message.assert_awaited_once()
    _, kwargs = interaction.response.edit_message.call_args
    assert kwargs["embed"].title == "Unlink failed"
    assert "not linked" in kwargs["embed"].description


async def test_cancel_button_does_not_call_the_api() -> None:
    api_client = _api_client(UnlinkResult(ok=True))
    view = UnlinkConfirmView(api_client=api_client, discord_guild_id="111", discord_user_id="999")
    interaction = _interaction()

    await view.cancel.callback(interaction)

    api_client.unlink_guild.assert_not_awaited()
    assert view.confirmed is False
    assert all(item.disabled for item in view.children)
    interaction.response.edit_message.assert_awaited_once()
