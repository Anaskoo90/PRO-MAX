"""Discord Setup Wizard HTTP routes — web-app-facing, JWT-authenticated."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.discord_integration.application.discord_setup import DiscordSetupService
from app.discord_integration.presentation import deps
from app.discord_integration.presentation.schemas import GuildLinkResponse, SetupTokenResponse
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.errors.api_exceptions import ForbiddenError
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["discord-integration"])


def _to_guild_link_response(dto) -> GuildLinkResponse:
    return GuildLinkResponse(
        id=dto.id, org_id=dto.org_id, discord_guild_id=dto.discord_guild_id,
        discord_guild_name=dto.discord_guild_name, status=dto.status, linked_by_user_id=dto.linked_by_user_id,
        linked_at=dto.linked_at, revoked_at=dto.revoked_at,
    )


def _assert_path_matches_claims_org(org_id: str, claims: TokenClaims) -> UUID:
    """Deliberately stricter than organizations_router.py's own org_id
    path handling (which relies on claims.org_id alone) — new code in this
    router checks the two agree, rather than silently trusting the path
    segment. Scoped to this router only; not a change to any existing one."""
    parsed = UUID(org_id)
    if parsed != claims.org_id:
        raise ForbiddenError("Path organization does not match the authenticated user's organization")
    return parsed


@router.post(
    "/organizations/{org_id}/discord/setup-token",
    response_model=DataResponse[SetupTokenResponse],
    status_code=201,
)
async def request_setup_token(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: DiscordSetupService = Depends(deps.get_discord_setup_service),
) -> DataResponse[SetupTokenResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    token = await service.request_setup_token(org_id=parsed_org_id, requested_by_user_id=claims.subject_user_id)
    return DataResponse(
        data=SetupTokenResponse(raw_code=token.raw_code, invite_url=token.invite_url, expires_at=token.expires_at)
    )


@router.get(
    "/organizations/{org_id}/discord/guild-links",
    response_model=DataResponse[list[GuildLinkResponse]],
)
async def list_guild_links(
    org_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: DiscordSetupService = Depends(deps.get_discord_setup_service),
) -> DataResponse[list[GuildLinkResponse]]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    links = await service.list_guild_links(org_id=parsed_org_id, actor_user_id=claims.subject_user_id)
    return DataResponse(data=[_to_guild_link_response(link) for link in links])


@router.delete(
    "/organizations/{org_id}/discord/guild-links/{guild_link_id}",
    status_code=204,
)
async def unlink_guild(
    org_id: str,
    guild_link_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: DiscordSetupService = Depends(deps.get_discord_setup_service),
) -> None:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    await service.unlink_guild(
        org_id=parsed_org_id, guild_link_id=UUID(guild_link_id), actor_user_id=claims.subject_user_id
    )
