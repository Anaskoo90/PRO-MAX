"""The Ticket System's ACL to Discord Integration translates the Discord
context's 'organization not active' error into the ticket context's own, so
nothing above the infrastructure layer ever sees a Discord exception."""

from __future__ import annotations

import pytest
from app.discord_integration.domain.exceptions import GuildOrganizationNotActiveError
from app.platform_core.errors.handlers import _map_status_code
from app.platform_core.shared_kernel.error_codes import ErrorCode
from app.platform_core.shared_kernel.utils import new_uuid7
from app.ticket_system.domain.exceptions import TicketOrganizationNotActiveError
from app.ticket_system.infrastructure.discord_integration_adapter import (
    DiscordIntegrationGuildResolverAdapter,
)

pytestmark = pytest.mark.asyncio


class _Service:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self._result, self._error = result, error

    async def resolve_org_id_by_discord_guild_id(self, *, discord_guild_id: str):
        if self._error is not None:
            raise self._error
        return self._result


async def test_the_resolved_org_id_is_passed_through() -> None:
    org_id = new_uuid7()

    assert await DiscordIntegrationGuildResolverAdapter(_Service(result=org_id)).resolve_org_id(
        discord_guild_id="g"
    ) == org_id


async def test_an_unlinked_guild_is_still_none() -> None:
    assert await DiscordIntegrationGuildResolverAdapter(_Service(result=None)).resolve_org_id(
        discord_guild_id="g"
    ) is None


async def test_an_inactive_organization_is_translated_to_the_ticket_contexts_own_error() -> None:
    adapter = DiscordIntegrationGuildResolverAdapter(_Service(error=GuildOrganizationNotActiveError()))

    with pytest.raises(TicketOrganizationNotActiveError) as excinfo:
        await adapter.resolve_org_id(discord_guild_id="g")

    assert not isinstance(excinfo.value, GuildOrganizationNotActiveError)
    assert excinfo.value.code == ErrorCode.ORGANIZATION_NOT_ACTIVE
    assert _map_status_code(excinfo.value) == 403
    assert excinfo.value.__cause__ is None  # no Discord-context exception chained through


async def test_other_errors_are_not_swallowed() -> None:
    boom = RuntimeError("database down")

    with pytest.raises(RuntimeError):
        await DiscordIntegrationGuildResolverAdapter(_Service(error=boom)).resolve_org_id(discord_guild_id="g")
