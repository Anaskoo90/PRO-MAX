"""Shared authorization helper for Ticket System's web-app-facing
operations — mirrors DiscordAuthorization/BoardAuthorization exactly.
Reuses Identity's already-seeded ticket:create/ticket:read/ticket:update
permissions (present in PERMISSION_CATALOG since before this feature
existed, granted to the member baseline) rather than redefining them."""

from __future__ import annotations

from app.platform_core.shared_kernel.types import OrgId, UserId
from app.ticket_system.application.ports import OrgPermissionCheckerPort
from app.ticket_system.domain.exceptions import InsufficientTicketPermissionError


class TicketAuthorization:
    def __init__(self, *, permission_checker: OrgPermissionCheckerPort) -> None:
        self._permission_checker = permission_checker

    async def assert_permission(self, *, org_id: OrgId, user_id: UserId, action: str) -> None:
        allowed = await self._permission_checker.has_permission(
            user_id=user_id, org_id=org_id, resource="ticket", action=action
        )
        if not allowed:
            raise InsufficientTicketPermissionError(action)
