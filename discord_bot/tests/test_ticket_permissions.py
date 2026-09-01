from __future__ import annotations

from unittest.mock import MagicMock

import discord

from discord_bot.utils.permissions import has_staff_role_permission


def _interaction(*, guild, user) -> discord.Interaction:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    return interaction


def _member(*, manage_guild: bool, role_ids: list[int]) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.guild_permissions = discord.Permissions(manage_guild=manage_guild)
    roles = []
    for role_id in role_ids:
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        roles.append(role)
    member.roles = roles
    return member


def test_member_with_a_matching_staff_role_is_permitted() -> None:
    member = _member(manage_guild=False, role_ids=[111, 222])
    interaction = _interaction(guild=MagicMock(spec=discord.Guild), user=member)

    assert has_staff_role_permission(interaction, ["222", "333"]) is True


def test_member_without_a_matching_staff_role_is_rejected() -> None:
    member = _member(manage_guild=False, role_ids=[111])
    interaction = _interaction(guild=MagicMock(spec=discord.Guild), user=member)

    assert has_staff_role_permission(interaction, ["222", "333"]) is False


def test_manage_guild_is_always_permitted_regardless_of_staff_roles() -> None:
    member = _member(manage_guild=True, role_ids=[])
    interaction = _interaction(guild=MagicMock(spec=discord.Guild), user=member)

    assert has_staff_role_permission(interaction, ["222"]) is True


def test_no_configured_staff_roles_rejects_a_non_admin_member() -> None:
    member = _member(manage_guild=False, role_ids=[111])
    interaction = _interaction(guild=MagicMock(spec=discord.Guild), user=member)

    assert has_staff_role_permission(interaction, []) is False


def test_dm_interaction_with_no_guild_is_rejected() -> None:
    user = MagicMock(spec=discord.User)
    interaction = _interaction(guild=None, user=user)

    assert has_staff_role_permission(interaction, ["222"]) is False
