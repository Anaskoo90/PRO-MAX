"""GuildDesk Discord bot — an independent client of the platform's HTTP API.

This package never imports from `app` (the FastAPI backend, services/platform)
— all communication happens over HTTP via services/api_client.py, exactly
like any other external API consumer. Keeping that boundary hard is what
lets the bot be developed, deployed, and versioned independently of the
backend it talks to.
"""

from __future__ import annotations
