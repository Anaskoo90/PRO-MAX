"""
Anti-Corruption Layer: the only file in this bounded context permitted to
import Discord Integration's application types. Wraps
DiscordSetupService.resolve_org_id_by_discord_guild_id (the one small
additive method Discord Integration gained for exactly this purpose) so
nothing above the infrastructure layer here ever imports Discord
Integration directly.

Constructed in composition.py with a reference to DiscordIntegrationModule's
own public discord_setup_service instance — same pattern as
projects/infrastructure/identity_adapter.py.
"""

from __future__ import annotations

from app.discord_integration.application.discord_setup import DiscordSetupService
from app.platform_core.shared_kernel.types import OrgId


class DiscordIntegrationGuildResolverAdapter:
    def __init__(self, discord_setup_service: DiscordSetupService) -> None:
        self._discord_setup_service = discord_setup_service

    async def resolve_org_id(self, *, discord_guild_id: str) -> OrgId | None:
        return await self._discord_setup_service.resolve_org_id_by_discord_guild_id(discord_guild_id=discord_guild_id)
