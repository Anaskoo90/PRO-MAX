"""Ticket System HTTP routes: create/get/list/close/claim/unclaim/transfer.
Web-app-facing, JWT-authenticated — see ticket_bot_router.py for the
Discord-facing equivalents these share an application service with."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.platform_core.api.pagination import PageParams, page_params
from app.platform_core.api.responses import DataResponse, PagedResponse
from app.platform_core.api.sorting import UnsortableFieldError, parse_sort
from app.platform_core.api.versioning import versioned_router
from app.platform_core.errors.api_exceptions import ForbiddenError
from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError
from app.platform_core.security.token import TokenClaims
from app.platform_core.shared_kernel.dtos import PagedResult
from app.ticket_system.application.ticket_lifecycle import TicketLifecycleService
from app.ticket_system.domain.value_objects import TicketActor
from app.ticket_system.presentation import deps
from app.ticket_system.presentation.schemas import (
    ClaimTicketRequest,
    CloseTicketRequest,
    CreateTicketRequest,
    TicketListItemResponse,
    TicketResponse,
    TransferTicketRequest,
)

router = versioned_router(version="v1", tags=["tickets"])

# The only fields search_for_org's underlying repository query knows how to
# sort on today (see infrastructure/repositories.py's _SORTABLE_COLUMNS) —
# kept in lockstep with that set rather than accepting anything wider.
_TICKET_SORT_FIELDS = {"created_at", "ticket_number", "status"}


def _to_response(dto) -> TicketResponse:
    return TicketResponse(
        id=dto.id, org_id=dto.org_id, discord_guild_id=dto.discord_guild_id, ticket_number=dto.ticket_number,
        discord_channel_id=dto.discord_channel_id, title=dto.title, status=dto.status,
        opener_discord_user_id=dto.opener_discord_user_id, opener_user_id=dto.opener_user_id,
        claimed_by_discord_user_id=dto.claimed_by_discord_user_id, claimed_by_user_id=dto.claimed_by_user_id,
        closed_at=dto.closed_at, closed_by_discord_user_id=dto.closed_by_discord_user_id,
        closed_by_user_id=dto.closed_by_user_id, created_at=dto.created_at,
    )


def _to_list_item(dto) -> TicketListItemResponse:
    return TicketListItemResponse(
        id=dto.id, ticket_number=dto.ticket_number, title=dto.title, status=dto.status,
        discord_channel_id=dto.discord_channel_id, opener_discord_user_id=dto.opener_discord_user_id,
        claimed_by_discord_user_id=dto.claimed_by_discord_user_id, created_at=dto.created_at,
        closed_at=dto.closed_at,
    )


def _assert_path_matches_claims_org(org_id: str, claims: TokenClaims) -> UUID:
    """Same deliberate hardening as discord_integration/presentation/
    setup_router.py's identical helper — checks the path org_id agrees
    with the authenticated user's own org rather than trusting either
    alone."""
    parsed = UUID(org_id)
    if parsed != claims.org_id:
        raise ForbiddenError("Path organization does not match the authenticated user's organization")
    return parsed


@router.post(
    "/organizations/{org_id}/tickets", response_model=DataResponse[TicketResponse], status_code=201,
)
async def create_ticket(
    org_id: str,
    request: CreateTicketRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    opener = TicketActor(
        discord_user_id=request.opener_discord_user_id,
        user_id=None if request.opener_discord_user_id else claims.subject_user_id,
    )
    ticket = await service.create_ticket(
        org_id=parsed_org_id, actor_user_id=claims.subject_user_id, discord_guild_id=request.discord_guild_id,
        discord_channel_id=request.discord_channel_id, title=request.title, opener=opener,
    )
    return DataResponse(data=_to_response(ticket))


@router.get("/organizations/{org_id}/tickets", response_model=PagedResponse[TicketListItemResponse])
async def list_tickets(
    org_id: str,
    page: PageParams = Depends(page_params),
    status: str | None = None,
    claimed_by_discord_user_id: str | None = None,
    sort: str | None = None,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> PagedResponse[TicketListItemResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    try:
        sort_fields = parse_sort(sort, _TICKET_SORT_FIELDS)
    except UnsortableFieldError as exc:
        raise BusinessRuleViolationError("unsortable_field", str(exc)) from exc

    result = await service.search_for_org(
        org_id=parsed_org_id, actor_user_id=claims.subject_user_id, status=status,
        claimed_by_discord_user_id=claimed_by_discord_user_id, sort=sort_fields,
        page=page.page, page_size=page.page_size,
    )
    return PagedResponse.from_paged_result(
        PagedResult(items=[_to_list_item(t) for t in result.items], total=result.total, page=result.page,
                    page_size=result.page_size)
    )


@router.get("/organizations/{org_id}/tickets/{ticket_id}", response_model=DataResponse[TicketResponse])
async def get_ticket(
    org_id: str,
    ticket_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    ticket = await service.get(org_id=parsed_org_id, actor_user_id=claims.subject_user_id, ticket_id=UUID(ticket_id))
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/organizations/{org_id}/tickets/{ticket_id}/close", response_model=DataResponse[TicketResponse],
)
async def close_ticket(
    org_id: str,
    ticket_id: str,
    request: CloseTicketRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    actor = TicketActor(
        discord_user_id=request.closed_by_discord_user_id,
        user_id=None if request.closed_by_discord_user_id else claims.subject_user_id,
    )
    ticket = await service.close_ticket(
        org_id=parsed_org_id, actor_user_id=claims.subject_user_id, ticket_id=UUID(ticket_id), actor=actor,
    )
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/organizations/{org_id}/tickets/{ticket_id}/claim", response_model=DataResponse[TicketResponse],
)
async def claim_ticket(
    org_id: str,
    ticket_id: str,
    request: ClaimTicketRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    claimant = TicketActor(
        discord_user_id=request.claimed_by_discord_user_id,
        user_id=None if request.claimed_by_discord_user_id else claims.subject_user_id,
    )
    ticket = await service.claim_ticket(
        org_id=parsed_org_id, actor_user_id=claims.subject_user_id, ticket_id=UUID(ticket_id), claimant=claimant,
    )
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/organizations/{org_id}/tickets/{ticket_id}/unclaim", response_model=DataResponse[TicketResponse],
)
async def unclaim_ticket(
    org_id: str,
    ticket_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    ticket = await service.unclaim_ticket(
        org_id=parsed_org_id, actor_user_id=claims.subject_user_id, ticket_id=UUID(ticket_id),
    )
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/organizations/{org_id}/tickets/{ticket_id}/transfer", response_model=DataResponse[TicketResponse],
)
async def transfer_ticket(
    org_id: str,
    ticket_id: str,
    request: TransferTicketRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    new_claimant = TicketActor(discord_user_id=request.new_claimant_discord_user_id)
    ticket = await service.transfer_ticket(
        org_id=parsed_org_id, actor_user_id=claims.subject_user_id, ticket_id=UUID(ticket_id),
        new_claimant=new_claimant,
    )
    return DataResponse(data=_to_response(ticket))
