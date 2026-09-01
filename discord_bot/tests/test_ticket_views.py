from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord

from discord_bot.services.api_client import (
    TicketCategoriesResult,
    TicketCategoryData,
    TicketData,
    TicketResult,
)
from discord_bot.views.ticket_views import (
    TicketControlView,
    TicketFormModal,
    TicketPanelView,
    TicketTransferSelectView,
)


def _bot() -> MagicMock:
    bot = MagicMock()
    bot.api_client = MagicMock()
    bot.api_client.list_ticket_categories = AsyncMock(
        return_value=TicketCategoriesResult(ok=True, categories=[])
    )
    bot.api_client.create_ticket = AsyncMock()
    bot.api_client.get_ticket_by_channel = AsyncMock()
    bot.api_client.claim_ticket = AsyncMock()
    bot.api_client.unclaim_ticket = AsyncMock()
    bot.api_client.transfer_ticket = AsyncMock()
    bot.api_client.close_ticket = AsyncMock()
    return bot


def _ticket(status: str = "open", claimed_by: str | None = None) -> TicketData:
    return TicketData(
        id="ticket-1", ticket_number=1, discord_channel_id="222", title="Help", status=status,
        claimed_by_discord_user_id=claimed_by,
    )


def _interaction(*, channel_id: int = 222, guild_id: int = 111, user_id: int = 999) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.channel_id = channel_id
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


async def test_panel_view_builds_one_button_per_category() -> None:
    bot = _bot()
    categories = [
        TicketCategoryData(id="1", name="Billing", discord_category_channel_id="10"),
        TicketCategoryData(id="2", name="Technical", discord_category_channel_id="11"),
    ]

    view = TicketPanelView(bot=bot, categories=categories)

    assert len(view.children) == 2
    assert {item.label for item in view.children} == {"Billing", "Technical"}


async def test_panel_view_caps_at_five_buttons() -> None:
    bot = _bot()
    categories = [TicketCategoryData(id=str(i), name=f"Cat{i}", discord_category_channel_id="10") for i in range(8)]

    view = TicketPanelView(bot=bot, categories=categories)

    assert len(view.children) == 5


async def test_category_button_opens_the_form_modal() -> None:
    bot = _bot()
    view = TicketPanelView(bot=bot, categories=[TicketCategoryData(id="1", name="Billing", discord_category_channel_id="10")])
    button = view.children[0]
    interaction = _interaction()

    await button.callback(interaction)

    interaction.response.send_modal.assert_awaited_once()
    modal = interaction.response.send_modal.call_args[0][0]
    assert isinstance(modal, TicketFormModal)


async def test_form_modal_creates_a_channel_and_ticket_on_submit() -> None:
    bot = _bot()
    bot.api_client.create_ticket.return_value = TicketResult(ok=True, ticket=_ticket())
    category = TicketCategoryData(id="1", name="Billing", discord_category_channel_id="10")
    modal = TicketFormModal(bot=bot, category=category)
    modal.description._value = "My billing issue"

    interaction = _interaction()
    interaction.guild.get_channel.return_value = None
    created_channel = MagicMock(mention="#billing-user")
    created_channel.send = AsyncMock()
    interaction.guild.create_text_channel = AsyncMock(return_value=created_channel)

    await modal.on_submit(interaction)

    interaction.guild.create_text_channel.assert_awaited_once()
    bot.api_client.create_ticket.assert_awaited_once()
    created_channel.send.assert_awaited_once()
    interaction.followup.send.assert_awaited()


async def test_form_modal_shows_a_friendly_error_when_channel_creation_fails() -> None:
    """Regression test: a Discord-side failure creating the ticket channel
    used to propagate uncaught, surfacing Discord's generic "This
    interaction failed" instead of a clean error embed."""
    bot = _bot()
    category = TicketCategoryData(id="1", name="Billing", discord_category_channel_id="10")
    modal = TicketFormModal(bot=bot, category=category)
    modal.description._value = "My billing issue"

    interaction = _interaction()
    interaction.guild.get_channel.return_value = None
    interaction.guild.create_text_channel = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(status=403), "Missing Permissions")
    )

    await modal.on_submit(interaction)

    interaction.followup.send.assert_awaited_once()
    _, kwargs = interaction.followup.send.call_args
    assert kwargs["embed"].title == "Could not open ticket"
    bot.api_client.create_ticket.assert_not_awaited()


async def test_form_modal_deletes_the_channel_if_ticket_creation_fails() -> None:
    bot = _bot()
    bot.api_client.create_ticket.return_value = TicketResult(ok=False, error_message="Something went wrong")
    category = TicketCategoryData(id="1", name="Billing", discord_category_channel_id="10")
    modal = TicketFormModal(bot=bot, category=category)
    modal.description._value = "My billing issue"

    interaction = _interaction()
    interaction.guild.get_channel.return_value = None
    channel = MagicMock()
    channel.delete = AsyncMock()
    interaction.guild.create_text_channel = AsyncMock(return_value=channel)

    await modal.on_submit(interaction)

    channel.delete.assert_awaited_once()


async def test_control_view_claim_rejects_a_non_staff_member() -> None:
    bot = _bot()
    view = TicketControlView(bot=bot)
    interaction = _interaction()

    with patch("discord_bot.views.ticket_views.has_staff_role_permission", return_value=False):
        await view.claim.callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    bot.api_client.get_ticket_by_channel.assert_not_awaited()


async def test_control_view_claim_succeeds_for_a_staff_member() -> None:
    bot = _bot()
    bot.api_client.get_ticket_by_channel.return_value = TicketResult(ok=True, ticket=_ticket())
    bot.api_client.claim_ticket.return_value = TicketResult(ok=True, ticket=_ticket(status="claimed", claimed_by="999"))
    view = TicketControlView(bot=bot)
    interaction = _interaction()

    with patch("discord_bot.views.ticket_views.has_staff_role_permission", return_value=True):
        await view.claim.callback(interaction)

    bot.api_client.claim_ticket.assert_awaited_once_with(ticket_id="ticket-1", claimant_discord_user_id="999")
    interaction.response.send_message.assert_awaited_once()


async def test_control_view_unclaim_succeeds_for_a_staff_member() -> None:
    bot = _bot()
    bot.api_client.get_ticket_by_channel.return_value = TicketResult(ok=True, ticket=_ticket(status="claimed", claimed_by="999"))
    bot.api_client.unclaim_ticket.return_value = TicketResult(ok=True, ticket=_ticket())
    view = TicketControlView(bot=bot)
    interaction = _interaction()

    with patch("discord_bot.views.ticket_views.has_staff_role_permission", return_value=True):
        await view.unclaim.callback(interaction)

    bot.api_client.unclaim_ticket.assert_awaited_once_with(ticket_id="ticket-1")


async def test_control_view_close_succeeds_for_a_staff_member() -> None:
    bot = _bot()
    bot.api_client.get_ticket_by_channel.return_value = TicketResult(ok=True, ticket=_ticket())
    bot.api_client.close_ticket.return_value = TicketResult(ok=True, ticket=_ticket(status="closed"))
    view = TicketControlView(bot=bot)
    interaction = _interaction()

    with patch("discord_bot.views.ticket_views.has_staff_role_permission", return_value=True):
        await view.close.callback(interaction)

    bot.api_client.close_ticket.assert_awaited_once_with(ticket_id="ticket-1", closed_by_discord_user_id="999")


async def test_control_view_transfer_opens_a_user_select() -> None:
    bot = _bot()
    bot.api_client.get_ticket_by_channel.return_value = TicketResult(ok=True, ticket=_ticket(status="claimed", claimed_by="777"))
    view = TicketControlView(bot=bot)
    interaction = _interaction()

    with patch("discord_bot.views.ticket_views.has_staff_role_permission", return_value=True):
        await view.transfer.callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    _, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], TicketTransferSelectView)


async def test_transfer_select_view_calls_transfer_ticket() -> None:
    bot = _bot()
    bot.api_client.transfer_ticket.return_value = TicketResult(ok=True, ticket=_ticket(status="claimed", claimed_by="888"))
    view = TicketTransferSelectView(bot=bot, ticket_id="ticket-1")
    select = view.children[0]
    new_claimant = MagicMock()
    new_claimant.id = 888
    new_claimant.mention = "<@888>"
    select._values = [new_claimant]

    interaction = _interaction()
    await select.callback(interaction)

    bot.api_client.transfer_ticket.assert_awaited_once_with(ticket_id="ticket-1", new_claimant_discord_user_id="888")
    interaction.response.edit_message.assert_awaited_once()
