from __future__ import annotations

from unittest.mock import MagicMock

import discord

from discord_bot.utils.permissions import has_manage_guild_permission


def _interaction(*, guild, user) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    return interaction


def test_member_with_manage_guild_is_permitted() -> None:
    member = MagicMock(spec=discord.Member)
    member.guild_permissions = discord.Permissions(manage_guild=True)
    interaction = _interaction(guild=MagicMock(spec=discord.Guild), user=member)

    assert has_manage_guild_permission(interaction) is True


def test_member_without_manage_guild_is_rejected() -> None:
    member = MagicMock(spec=discord.Member)
    member.guild_permissions = discord.Permissions(manage_guild=False)
    interaction = _interaction(guild=MagicMock(spec=discord.Guild), user=member)

    assert has_manage_guild_permission(interaction) is False


def test_dm_interaction_with_no_guild_is_rejected() -> None:
    user = MagicMock(spec=discord.User)
    interaction = _interaction(guild=None, user=user)

    assert has_manage_guild_permission(interaction) is False


def test_non_member_user_object_is_rejected_even_with_a_guild_present() -> None:
    """Defensive case: interaction.user should always be a Member inside a
    guild, but a plain discord.User (no guild_permissions) must never be
    treated as permitted just because interaction.guild happens to be set."""
    user = MagicMock(spec=discord.User)
    interaction = _interaction(guild=MagicMock(spec=discord.Guild), user=user)

    assert has_manage_guild_permission(interaction) is False
