"""Ticket Category HTTP routes — web-app-facing, JWT-authenticated. The
bot reads categories through ticket_bot_router.py's
list_ticket_categories_via_bot (same TicketCategoryService instance,
different auth boundary)."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.errors.api_exceptions import ForbiddenError
from app.platform_core.security.token import TokenClaims
from app.ticket_system.application.ticket_categories import TicketCategoryService
from app.ticket_system.presentation import deps
from app.ticket_system.presentation.schemas import CreateTicketCategoryRequest, TicketCategoryResponse

router = versioned_router(version="v1", tags=["ticket-categories"])


def _to_response(dto) -> TicketCategoryResponse:
    return TicketCategoryResponse(
        id=dto.id, org_id=dto.org_id, discord_guild_id=dto.discord_guild_id, name=dto.name,
        discord_category_channel_id=dto.discord_category_channel_id,
        staff_discord_role_ids=dto.staff_discord_role_ids, is_active=dto.is_active,
    )


def _assert_path_matches_claims_org(org_id: str, claims: TokenClaims) -> UUID:
    parsed = UUID(org_id)
    if parsed != claims.org_id:
        raise ForbiddenError("Path organization does not match the authenticated user's organization")
    return parsed


@router.post(
    "/organizations/{org_id}/ticket-categories", response_model=DataResponse[TicketCategoryResponse], status_code=201,
)
async def create_ticket_category(
    org_id: str,
    request: CreateTicketCategoryRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketCategoryService = Depends(deps.get_ticket_category_service),
) -> DataResponse[TicketCategoryResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    category = await service.create_category(
        org_id=parsed_org_id, actor_user_id=claims.subject_user_id, discord_guild_id=request.discord_guild_id,
        name=request.name, discord_category_channel_id=request.discord_category_channel_id,
        staff_discord_role_ids=request.staff_discord_role_ids,
    )
    return DataResponse(data=_to_response(category))


@router.get(
    "/organizations/{org_id}/ticket-categories", response_model=DataResponse[list[TicketCategoryResponse]],
)
async def list_ticket_categories(
    org_id: str,
    discord_guild_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketCategoryService = Depends(deps.get_ticket_category_service),
) -> DataResponse[list[TicketCategoryResponse]]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    categories = await service.list_for_guild(org_id=parsed_org_id, discord_guild_id=discord_guild_id)
    return DataResponse(data=[_to_response(c) for c in categories])


@router.get(
    "/organizations/{org_id}/ticket-categories/{category_id}", response_model=DataResponse[TicketCategoryResponse],
)
async def get_ticket_category(
    org_id: str,
    category_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketCategoryService = Depends(deps.get_ticket_category_service),
) -> DataResponse[TicketCategoryResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    category = await service.get(org_id=parsed_org_id, category_id=UUID(category_id))
    return DataResponse(data=_to_response(category))
