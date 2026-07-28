"""
Placeholder — interactive ticket views (buttons/modals for claim, close,
etc.) are not implemented yet. This module exists so the views/ package
structure is in place ahead of the tickets cog that will eventually use it.
"""

from __future__ import annotations

import discord


class TicketView(discord.ui.View):
    """Scaffolding only — no items are added yet. cogs/tickets.py will
    attach buttons here once ticket commands are implemented."""

    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(timeout=timeout)
