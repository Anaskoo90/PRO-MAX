"""Password Management HTTP routes."""

from __future__ import annotations

from fastapi import Depends

from app.identity.application.password_management import PasswordManagementService
from app.identity.presentation import deps
from app.identity.presentation.schemas import (
    ChangePasswordRequest,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
)
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["password"])


@router.post("/users/me/password/change", status_code=204)
async def change_password(
    request: ChangePasswordRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: PasswordManagementService = Depends(deps.get_password_management_service),
) -> None:
    await service.change_password(
        user_id=claims.subject_user_id,
        current_password=request.current_password,
        new_password=request.new_password,
    )


@router.post("/auth/password/forgot", status_code=204)
async def request_password_reset(
    request: RequestPasswordResetRequest,
    service: PasswordManagementService = Depends(deps.get_password_management_service),
) -> None:
    await service.request_password_reset(org_id=request.org_id, email=request.email)


@router.post("/auth/password/reset", status_code=204)
async def reset_password(
    request: ResetPasswordRequest,
    service: PasswordManagementService = Depends(deps.get_password_management_service),
) -> None:
    await service.reset_password(raw_token=request.token, new_password=request.new_password)
