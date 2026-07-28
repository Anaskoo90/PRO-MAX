"""Small, reusable Discord embed builders shared across cogs — kept in one
place so every command renders status/error messages with the same look
rather than each cog hand-rolling its own discord.Embed."""

from __future__ import annotations

import discord

_COLOR_SUCCESS = discord.Color.green()
_COLOR_ERROR = discord.Color.red()


def build_status_embed(*, title: str, healthy: bool, description: str | None = None) -> discord.Embed:
    """A pass/fail status embed — used by /ping today, and by any future
    command that just needs to report "this thing is up" or "this thing
    is down" (e.g. a future orders/wallet health check)."""
    return discord.Embed(
        title=title,
        description=description,
        color=_COLOR_SUCCESS if healthy else _COLOR_ERROR,
    )


def build_error_embed(*, title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=_COLOR_ERROR)
