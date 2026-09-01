"""Discord Setup Wizard HTTP routes — bot-facing, authenticated via the
shared bot service secret (see bot_authentication.py), not JWT."""

from __future__ import annotations

from fastapi import Depends

from app.discord_integration.application.discord_setup import DiscordSetupService
from app.discord_integration.presentation import deps
from app.discord_integration.presentation.bot_authentication import require_bot_service_secret
from app.discord_integration.presentation.schemas import (
    CompleteSetupRequest,
    GuildLinkResponse,
    GuildStatusResponse,
    UnlinkGuildRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router

router = versioned_router(version="v1", tags=["discord-bot"])


def _to_guild_link_response(dto) -> GuildLinkResponse:
    return GuildLinkResponse(
        id=dto.id, org_id=dto.org_id, discord_guild_id=dto.discord_guild_id,
        discord_guild_name=dto.discord_guild_name, status=dto.status, linked_by_user_id=dto.linked_by_user_id,
        linked_at=dto.linked_at, revoked_at=dto.revoked_at,
    )


@router.post(
    "/discord/setup/complete",
    response_model=DataResponse[GuildLinkResponse],
    status_code=201,
    dependencies=[Depends(require_bot_service_secret)],
)
async def complete_setup(
    request: CompleteSetupRequest,
    service: DiscordSetupService = Depends(deps.get_discord_setup_service),
) -> DataResponse[GuildLinkResponse]:
    link = await service.complete_setup(
        raw_code=request.code, discord_guild_id=request.discord_guild_id,
        discord_guild_name=request.discord_guild_name, discord_user_id=request.discord_user_id,
    )
    return DataResponse(data=_to_guild_link_response(link))


@router.get(
    "/discord/guilds/{discord_guild_id}/status",
    response_model=DataResponse[GuildStatusResponse],
    dependencies=[Depends(require_bot_service_secret)],
)
async def get_guild_status(
    discord_guild_id: str,
    service: DiscordSetupService = Depends(deps.get_discord_setup_service),
) -> DataResponse[GuildStatusResponse]:
    status_dto = await service.get_status_by_discord_guild_id(discord_guild_id=discord_guild_id)
    return DataResponse(
        data=GuildStatusResponse(
            linked=status_dto.linked, org_name=status_dto.org_name,
            discord_guild_name=status_dto.discord_guild_name, linked_at=status_dto.linked_at,
        )
    )


@router.post(
    "/discord/guilds/{discord_guild_id}/unlink",
    status_code=204,
    dependencies=[Depends(require_bot_service_secret)],
)
async def unlink_guild(
    discord_guild_id: str,
    request: UnlinkGuildRequest,
    service: DiscordSetupService = Depends(deps.get_discord_setup_service),
) -> None:
    await service.unlink_guild_by_discord_id(
        discord_guild_id=discord_guild_id, discord_user_id=request.discord_user_id
    )
