"""Discord-side authorization helpers — shared by every command that
requires the invoking member to be able to administer the guild itself.
This is one layer of the Setup Wizard's v1 trust boundary (Discord "Manage
Server" plus the backend's bot shared secret); GuildDesk RBAC isn't
checked here since there's no Discord-account-to-GuildDesk-user link yet
(a deliberately deferred future feature)."""

from __future__ import annotations

import discord


def has_manage_guild_permission(interaction: discord.Interaction) -> bool:
    """True if the invoking member can administer this Discord server.
    DM interactions (interaction.guild is None, interaction.user is a
    discord.User rather than a discord.Member) have no guild permissions
    at all, so they're never considered permitted."""
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False
    return interaction.user.guild_permissions.manage_guild


def has_staff_role_permission(interaction: discord.Interaction, staff_discord_role_ids: list[str]) -> bool:
    """True if the invoking member holds at least one of a ticket
    category's configured staff roles, OR can already Manage Server (a
    server admin is implicitly staff for every category — same "escape
    hatch" reasoning org_owner/org_admin get the full GuildDesk permission
    catalog for). Ticket claim/unclaim/transfer/close are gated by this,
    not by GuildDesk RBAC — see ticket_lifecycle.py's module docstring for
    the trust boundary this continues."""
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.manage_guild:
        return True
    if not staff_discord_role_ids:
        return False
    member_role_ids = {str(role.id) for role in interaction.user.roles}
    return bool(member_role_ids.intersection(staff_discord_role_ids))
