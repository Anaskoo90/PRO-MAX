"""Shared authorization helper used by DiscordSetupService for the two
web-app-facing (JWT-authenticated) operations. The three bot-facing
operations are deliberately NOT gated here — see bot_authentication.py and
the Discord Setup Wizard design doc's Permission Model section for why
(Discord "Manage Server" + the bot shared secret is this v1's trust
boundary for those, not GuildDesk RBAC)."""

from __future__ import annotations

from app.discord_integration.application.ports import OrgPermissionCheckerPort
from app.discord_integration.domain.exceptions import InsufficientDiscordPermissionError
from app.platform_core.shared_kernel.types import OrgId, UserId


class DiscordAuthorization:
    def __init__(self, *, permission_checker: OrgPermissionCheckerPort) -> None:
        self._permission_checker = permission_checker

    async def assert_can_manage_integration(self, *, org_id: OrgId, user_id: UserId) -> None:
        allowed = await self._permission_checker.has_permission(
            user_id=user_id, org_id=org_id, resource="discord", action="manage_integration"
        )
        if not allowed:
            raise InsufficientDiscordPermissionError()
