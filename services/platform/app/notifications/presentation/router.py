from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.notifications.application.dtos import NotificationDTO
from app.notifications.application.notification_service import NotificationService
from app.notifications.presentation import deps
from app.notifications.presentation.schemas import (
    NotificationResponse,
    UnreadNotificationCountResponse,
)
from app.platform_core.api.pagination import PageParams, page_params
from app.platform_core.api.responses import DataResponse, PagedResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["notifications"])


def _to_response(dto: NotificationDTO) -> NotificationResponse:
    return NotificationResponse(
        id=dto.id,
        org_id=dto.org_id,
        channel=dto.channel,
        subject=dto.subject,
        body=dto.body,
        metadata=dto.metadata,
        status=dto.status,
        created_at=dto.created_at,
        delivered_at=dto.delivered_at,
        read_at=dto.read_at,
    )


@router.get(
    "/users/me/notifications",
    response_model=PagedResponse[NotificationResponse],
)
async def list_my_notifications(
    unread_only: bool = False,
    page: PageParams = Depends(page_params),
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: NotificationService = Depends(deps.get_notification_service),
) -> PagedResponse[NotificationResponse]:
    result = await service.list_for_user(
        org_id=claims.org_id,
        user_id=claims.subject_user_id,
        unread_only=unread_only,
        offset=page.offset,
        limit=page.limit,
    )
    total_pages = (result.total + page.page_size - 1) // page.page_size
    return PagedResponse(
        data=[_to_response(item) for item in result.items],
        page=page.page,
        page_size=page.page_size,
        total=result.total,
        total_pages=total_pages,
    )


@router.get(
    "/users/me/notifications/unread-count",
    response_model=DataResponse[UnreadNotificationCountResponse],
)
async def get_my_unread_notification_count(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: NotificationService = Depends(deps.get_notification_service),
) -> DataResponse[UnreadNotificationCountResponse]:
    count = await service.count_unread(
        org_id=claims.org_id,
        user_id=claims.subject_user_id,
    )
    return DataResponse(data=UnreadNotificationCountResponse(count=count))


@router.post("/users/me/notifications/read-all", status_code=204)
async def mark_all_my_notifications_read(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: NotificationService = Depends(deps.get_notification_service),
) -> None:
    await service.mark_all_read(
        org_id=claims.org_id,
        user_id=claims.subject_user_id,
    )


@router.post("/users/me/notifications/{notification_id}/read", status_code=204)
async def mark_my_notification_read(
    notification_id: UUID,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: NotificationService = Depends(deps.get_notification_service),
) -> None:
    await service.mark_read(
        org_id=claims.org_id,
        user_id=claims.subject_user_id,
        notification_id=notification_id,
    )
