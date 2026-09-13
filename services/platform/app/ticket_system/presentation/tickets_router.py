"""Ticket System HTTP routes: create/get/list/close/claim/unclaim/transfer.
Web-app-facing, JWT-authenticated — see ticket_bot_router.py for the
Discord-facing equivalents these share an application service with."""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import Depends, File, UploadFile
from fastapi.responses import StreamingResponse

from app.platform_core.api.pagination import PageParams, page_params
from app.platform_core.api.responses import DataResponse, PagedResponse
from app.platform_core.api.sorting import UnsortableFieldError, parse_sort
from app.platform_core.api.versioning import versioned_router
from app.platform_core.errors.api_exceptions import ForbiddenError
from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError
from app.platform_core.security.token import TokenClaims
from app.platform_core.shared_kernel.dtos import PagedResult
from app.platform_core.storage.upload_contracts import MAX_UPLOAD_BYTES
from app.ticket_system.application.ticket_attachments import TicketAttachmentService
from app.ticket_system.application.ticket_lifecycle import TicketLifecycleService
from app.ticket_system.application.ticket_messages import TicketMessageService
from app.ticket_system.domain.value_objects import TicketActor
from app.ticket_system.presentation import deps
from app.ticket_system.presentation.schemas import (
    ClaimTicketRequest,
    CloseTicketRequest,
    CreateTicketMessageRequest,
    CreateTicketRequest,
    TicketAttachmentResponse,
    TicketListItemResponse,
    TicketMessageResponse,
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
        id=dto.id, org_id=dto.org_id, category_id=dto.category_id,
        discord_guild_id=dto.discord_guild_id, ticket_number=dto.ticket_number,
        discord_channel_id=dto.discord_channel_id, title=dto.title, status=dto.status,
        opener_discord_user_id=dto.opener_discord_user_id, opener_user_id=dto.opener_user_id,
        claimed_by_discord_user_id=dto.claimed_by_discord_user_id, claimed_by_user_id=dto.claimed_by_user_id,
        closed_at=dto.closed_at, closed_by_discord_user_id=dto.closed_by_discord_user_id,
        closed_by_user_id=dto.closed_by_user_id, created_at=dto.created_at,
    )


def _to_list_item(dto) -> TicketListItemResponse:
    return TicketListItemResponse(
        id=dto.id, category_id=dto.category_id, ticket_number=dto.ticket_number,
        title=dto.title, status=dto.status,
        discord_channel_id=dto.discord_channel_id, opener_discord_user_id=dto.opener_discord_user_id,
        claimed_by_discord_user_id=dto.claimed_by_discord_user_id, created_at=dto.created_at,
        closed_at=dto.closed_at,
    )


def _to_message_response(dto) -> TicketMessageResponse:
    return TicketMessageResponse(
        id=dto.id,
        org_id=dto.org_id,
        ticket_id=dto.ticket_id,
        body=dto.body,
        author_discord_user_id=dto.author_discord_user_id,
        author_user_id=dto.author_user_id,
        discord_message_id=dto.discord_message_id,
        is_internal=dto.is_internal,
        created_at=dto.created_at,
    )


def _to_attachment_response(dto) -> TicketAttachmentResponse:
    return TicketAttachmentResponse(
        id=dto.id,
        org_id=dto.org_id,
        ticket_id=dto.ticket_id,
        filename=dto.filename,
        content_type=dto.content_type,
        size_bytes=dto.size_bytes,
        sha256=dto.sha256,
        uploaded_by_user_id=dto.uploaded_by_user_id,
        uploaded_by_discord_user_id=dto.uploaded_by_discord_user_id,
        discord_attachment_id=dto.discord_attachment_id,
        created_at=dto.created_at,
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
        category_id=request.category_id,
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


@router.get(
    "/organizations/{org_id}/tickets/{ticket_id}/messages",
    response_model=PagedResponse[TicketMessageResponse],
)
async def list_ticket_messages(
    org_id: str,
    ticket_id: str,
    include_internal: bool = False,
    page: PageParams = Depends(page_params),
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketMessageService = Depends(deps.get_ticket_message_service),
) -> PagedResponse[TicketMessageResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    result = await service.list_messages(
        org_id=parsed_org_id,
        actor_user_id=claims.subject_user_id,
        ticket_id=UUID(ticket_id),
        include_internal=include_internal,
        page=page.page,
        page_size=page.page_size,
    )
    return PagedResponse.from_paged_result(
        PagedResult(
            items=[_to_message_response(message) for message in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )
    )


@router.post(
    "/organizations/{org_id}/tickets/{ticket_id}/messages",
    response_model=DataResponse[TicketMessageResponse],
    status_code=201,
)
async def add_ticket_message(
    org_id: str,
    ticket_id: str,
    request: CreateTicketMessageRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketMessageService = Depends(deps.get_ticket_message_service),
) -> DataResponse[TicketMessageResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    message = await service.add_message(
        org_id=parsed_org_id,
        actor_user_id=claims.subject_user_id,
        ticket_id=UUID(ticket_id),
        body=request.body,
        is_internal=request.is_internal,
    )
    return DataResponse(data=_to_message_response(message))


@router.get(
    "/organizations/{org_id}/tickets/{ticket_id}/attachments",
    response_model=DataResponse[list[TicketAttachmentResponse]],
)
async def list_ticket_attachments(
    org_id: str,
    ticket_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketAttachmentService = Depends(deps.get_ticket_attachment_service),
) -> DataResponse[list[TicketAttachmentResponse]]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    attachments = await service.list_for_ticket(
        org_id=parsed_org_id,
        actor_user_id=claims.subject_user_id,
        ticket_id=UUID(ticket_id),
    )
    return DataResponse(
        data=[_to_attachment_response(attachment) for attachment in attachments]
    )


@router.post(
    "/organizations/{org_id}/tickets/{ticket_id}/attachments",
    response_model=DataResponse[TicketAttachmentResponse],
    status_code=201,
)
async def upload_ticket_attachment(
    org_id: str,
    ticket_id: str,
    file: UploadFile = File(...),
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketAttachmentService = Depends(deps.get_ticket_attachment_service),
) -> DataResponse[TicketAttachmentResponse]:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    attachment = await service.upload(
        org_id=parsed_org_id,
        actor_user_id=claims.subject_user_id,
        ticket_id=UUID(ticket_id),
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        content=content,
    )
    return DataResponse(data=_to_attachment_response(attachment))


@router.get(
    "/organizations/{org_id}/tickets/{ticket_id}/attachments/{attachment_id}/content",
    response_class=StreamingResponse,
)
async def download_ticket_attachment(
    org_id: str,
    ticket_id: str,
    attachment_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketAttachmentService = Depends(deps.get_ticket_attachment_service),
) -> StreamingResponse:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    attachment = await service.get_content(
        org_id=parsed_org_id,
        actor_user_id=claims.subject_user_id,
        ticket_id=UUID(ticket_id),
        attachment_id=UUID(attachment_id),
    )
    return StreamingResponse(
        attachment.chunks,
        media_type=attachment.content_type,
        headers={
            "Content-Length": str(attachment.size_bytes),
            "Content-Disposition": (
                "attachment; filename*=UTF-8''" + quote(attachment.filename)
            ),
        },
    )


@router.delete(
    "/organizations/{org_id}/tickets/{ticket_id}/attachments/{attachment_id}",
    status_code=204,
)
async def delete_ticket_attachment(
    org_id: str,
    ticket_id: str,
    attachment_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: TicketAttachmentService = Depends(deps.get_ticket_attachment_service),
) -> None:
    parsed_org_id = _assert_path_matches_claims_org(org_id, claims)
    await service.delete(
        org_id=parsed_org_id,
        actor_user_id=claims.subject_user_id,
        ticket_id=UUID(ticket_id),
        attachment_id=UUID(attachment_id),
    )


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
