"""Ticket System HTTP routes — bot-facing, authenticated via the shared
bot service secret (reused as-is from Discord Integration), not JWT. No
GuildDesk RBAC check happens here; the trust boundary is the bot secret
plus, before the bot ever calls these, a Discord "staff role" check on the
relevant category's staff_discord_role_ids."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, File, Form, UploadFile

from app.platform_core.api.pagination import PageParams, page_params
from app.platform_core.api.responses import DataResponse, PagedResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.shared_kernel.dtos import PagedResult
from app.platform_core.storage.upload_contracts import MAX_UPLOAD_BYTES
from app.ticket_system.application.ticket_attachments import TicketAttachmentService
from app.ticket_system.application.ticket_categories import TicketCategoryService
from app.ticket_system.application.ticket_lifecycle import TicketLifecycleService
from app.ticket_system.application.ticket_messages import TicketMessageService
from app.ticket_system.domain.value_objects import TicketActor
from app.ticket_system.presentation import deps
from app.ticket_system.presentation.schemas import (
    ClaimTicketViaBotRequest,
    CloseTicketViaBotRequest,
    CreateTicketCategoryRequest,
    CreateTicketMessageViaBotRequest,
    CreateTicketViaBotRequest,
    TicketAttachmentResponse,
    TicketCategoryResponse,
    TicketMessageResponse,
    TicketResponse,
    TransferTicketViaBotRequest,
)

router = versioned_router(version="v1", tags=["tickets-bot"])


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


def _to_category_response(dto) -> TicketCategoryResponse:
    return TicketCategoryResponse(
        id=dto.id, org_id=dto.org_id, discord_guild_id=dto.discord_guild_id, name=dto.name,
        discord_category_channel_id=dto.discord_category_channel_id,
        staff_discord_role_ids=dto.staff_discord_role_ids, is_active=dto.is_active,
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


@router.get(
    "/discord/tickets/by-channel/{discord_channel_id}",
    response_model=DataResponse[TicketResponse],
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def get_ticket_by_channel(
    discord_channel_id: str,
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    ticket = await service.get_by_discord_channel_id(discord_channel_id=discord_channel_id)
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/discord/tickets",
    response_model=DataResponse[TicketResponse],
    status_code=201,
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def create_ticket_via_bot(
    request: CreateTicketViaBotRequest,
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    ticket = await service.create_ticket_from_bot(
        discord_guild_id=request.discord_guild_id, discord_channel_id=request.discord_channel_id,
        category_id=request.category_id, title=request.title,
        opener=TicketActor(discord_user_id=request.opener_discord_user_id),
    )
    return DataResponse(data=_to_response(ticket))


@router.get(
    "/discord/tickets/{ticket_id}/messages",
    response_model=PagedResponse[TicketMessageResponse],
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def list_ticket_messages_via_bot(
    ticket_id: str,
    page: PageParams = Depends(page_params),
    service: TicketMessageService = Depends(deps.get_ticket_message_service),
) -> PagedResponse[TicketMessageResponse]:
    messages, total = await service.list_messages_from_bot(
        ticket_id=UUID(ticket_id),
        offset=page.offset,
        limit=page.page_size,
    )
    return PagedResponse.from_paged_result(
        PagedResult(
            items=[_to_message_response(message) for message in messages],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )
    )


@router.post(
    "/discord/tickets/{ticket_id}/messages",
    response_model=DataResponse[TicketMessageResponse],
    status_code=201,
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def add_ticket_message_via_bot(
    ticket_id: str,
    request: CreateTicketMessageViaBotRequest,
    service: TicketMessageService = Depends(deps.get_ticket_message_service),
) -> DataResponse[TicketMessageResponse]:
    message = await service.add_message_from_bot(
        ticket_id=UUID(ticket_id),
        body=request.body,
        author_discord_user_id=request.author_discord_user_id,
        discord_message_id=request.discord_message_id,
        is_internal=request.is_internal,
    )
    return DataResponse(data=_to_message_response(message))


@router.post(
    "/discord/tickets/by-channel/{discord_channel_id}/messages",
    response_model=DataResponse[TicketMessageResponse],
    status_code=201,
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def add_ticket_message_by_channel_via_bot(
    discord_channel_id: str,
    request: CreateTicketMessageViaBotRequest,
    service: TicketMessageService = Depends(deps.get_ticket_message_service),
) -> DataResponse[TicketMessageResponse]:
    message = await service.add_message_by_channel_from_bot(
        discord_channel_id=discord_channel_id,
        body=request.body,
        author_discord_user_id=request.author_discord_user_id,
        discord_message_id=request.discord_message_id,
        is_internal=request.is_internal,
    )
    return DataResponse(data=_to_message_response(message))


@router.post(
    "/discord/tickets/by-channel/{discord_channel_id}/attachments",
    response_model=DataResponse[TicketAttachmentResponse],
    status_code=201,
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def upload_ticket_attachment_by_channel_via_bot(
    discord_channel_id: str,
    file: UploadFile = File(...),
    uploaded_by_discord_user_id: str = Form(...),
    discord_attachment_id: str = Form(...),
    service: TicketAttachmentService = Depends(deps.get_ticket_attachment_service),
) -> DataResponse[TicketAttachmentResponse]:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    attachment = await service.upload_from_bot(
        discord_channel_id=discord_channel_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        content=content,
        uploaded_by_discord_user_id=uploaded_by_discord_user_id,
        discord_attachment_id=discord_attachment_id,
    )
    return DataResponse(data=_to_attachment_response(attachment))


@router.post(
    "/discord/tickets/{ticket_id}/claim",
    response_model=DataResponse[TicketResponse],
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def claim_ticket_via_bot(
    ticket_id: str,
    request: ClaimTicketViaBotRequest,
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    ticket = await service.claim_ticket_from_bot(
        ticket_id=UUID(ticket_id), claimant=TicketActor(discord_user_id=request.claimant_discord_user_id),
    )
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/discord/tickets/{ticket_id}/unclaim",
    response_model=DataResponse[TicketResponse],
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def unclaim_ticket_via_bot(
    ticket_id: str,
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    ticket = await service.unclaim_ticket_from_bot(ticket_id=UUID(ticket_id))
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/discord/tickets/{ticket_id}/transfer",
    response_model=DataResponse[TicketResponse],
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def transfer_ticket_via_bot(
    ticket_id: str,
    request: TransferTicketViaBotRequest,
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    ticket = await service.transfer_ticket_from_bot(
        ticket_id=UUID(ticket_id), new_claimant=TicketActor(discord_user_id=request.new_claimant_discord_user_id),
    )
    return DataResponse(data=_to_response(ticket))


@router.post(
    "/discord/tickets/{ticket_id}/close",
    response_model=DataResponse[TicketResponse],
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def close_ticket_via_bot(
    ticket_id: str,
    request: CloseTicketViaBotRequest,
    service: TicketLifecycleService = Depends(deps.get_ticket_lifecycle_service),
) -> DataResponse[TicketResponse]:
    ticket = await service.close_ticket_from_bot(
        ticket_id=UUID(ticket_id), actor=TicketActor(discord_user_id=request.closed_by_discord_user_id),
    )
    return DataResponse(data=_to_response(ticket))


@router.get(
    "/discord/guilds/{discord_guild_id}/ticket-categories",
    response_model=DataResponse[list[TicketCategoryResponse]],
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def list_ticket_categories_via_bot(
    discord_guild_id: str,
    category_service: TicketCategoryService = Depends(deps.get_ticket_category_service),
) -> DataResponse[list[TicketCategoryResponse]]:
    categories = await category_service.list_for_guild_from_bot(discord_guild_id=discord_guild_id)
    return DataResponse(data=[_to_category_response(c) for c in categories])


@router.post(
    "/discord/guilds/{discord_guild_id}/ticket-categories",
    response_model=DataResponse[TicketCategoryResponse],
    status_code=201,
    dependencies=[Depends(deps.require_bot_service_secret)],
)
async def create_ticket_category_via_bot(
    discord_guild_id: str,
    request: CreateTicketCategoryRequest,
    category_service: TicketCategoryService = Depends(deps.get_ticket_category_service),
) -> DataResponse[TicketCategoryResponse]:
    category = await category_service.create_category_from_bot(
        discord_guild_id=discord_guild_id, name=request.name,
        discord_category_channel_id=request.discord_category_channel_id,
        staff_discord_role_ids=request.staff_discord_role_ids,
    )
    return DataResponse(data=_to_category_response(category))
