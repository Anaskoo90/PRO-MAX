"""User Management HTTP routes: registration, profile, avatar, preferences, lifecycle."""

from __future__ import annotations

from fastapi import Depends, File, UploadFile

from app.identity.application.user_management import UserManagementService
from app.identity.presentation import deps
from app.identity.presentation.schemas import (
    RegisterUserRequest,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
    UserProfileResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["users"])


def _to_response(dto) -> UserProfileResponse:
    return UserProfileResponse(
        id=dto.id,
        org_id=dto.org_id,
        email=dto.email,
        display_name=dto.display_name,
        status=dto.status,
        mfa_enabled=dto.mfa_enabled,
        avatar_storage_key=dto.avatar_storage_key,
        preferences=dto.preferences,
    )


@router.post("/users/register", response_model=DataResponse[UserProfileResponse], status_code=201)
async def register(
    request: RegisterUserRequest,
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> DataResponse[UserProfileResponse]:
    profile = await service.register(
        org_id=request.org_id, email=request.email, password=request.password, display_name=request.display_name
    )
    return DataResponse(data=_to_response(profile))


@router.get("/users/me", response_model=DataResponse[UserProfileResponse])
async def get_my_profile(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> DataResponse[UserProfileResponse]:
    profile = await service.get_profile(user_id=claims.subject_user_id)
    return DataResponse(data=_to_response(profile))


@router.patch("/users/me", response_model=DataResponse[UserProfileResponse])
async def update_my_profile(
    request: UpdateProfileRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> DataResponse[UserProfileResponse]:
    profile = await service.update_profile(user_id=claims.subject_user_id, display_name=request.display_name)
    return DataResponse(data=_to_response(profile))


@router.put("/users/me/avatar", response_model=DataResponse[UserProfileResponse])
async def update_my_avatar(
    file: UploadFile = File(...),
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> DataResponse[UserProfileResponse]:
    content = await file.read()
    profile = await service.update_avatar(
        user_id=claims.subject_user_id,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        filename=file.filename or "avatar",
    )
    return DataResponse(data=_to_response(profile))


@router.put("/users/me/preferences", response_model=DataResponse[UserProfileResponse])
async def update_my_preferences(
    request: UpdatePreferencesRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> DataResponse[UserProfileResponse]:
    profile = await service.update_preferences(user_id=claims.subject_user_id, preferences=request.preferences)
    return DataResponse(data=_to_response(profile))


@router.post("/users/me/deactivate", status_code=204)
async def deactivate_my_account(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> None:
    await service.deactivate_account(user_id=claims.subject_user_id)


@router.post("/users/{user_id}/suspend", response_model=DataResponse[UserProfileResponse])
async def suspend_user(
    user_id: str,
    reason: str,
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> DataResponse[UserProfileResponse]:
    """Admin action — authorization (requiring an admin role/permission) is
    an Authorization/RBAC concern layered on top of this route once the
    Roles & Permissions submodule (mentioned in this phase's objective but
    not yet detailed) is implemented; not enforced here."""
    from uuid import UUID

    profile = await service.suspend(user_id=UUID(user_id), reason=reason)
    return DataResponse(data=_to_response(profile))


@router.post("/users/{user_id}/reactivate", response_model=DataResponse[UserProfileResponse])
async def reactivate_user(
    user_id: str,
    service: UserManagementService = Depends(deps.get_user_management_service),
) -> DataResponse[UserProfileResponse]:
    from uuid import UUID

    profile = await service.reactivate(user_id=UUID(user_id))
    return DataResponse(data=_to_response(profile))
