"""MFA HTTP routes."""

from __future__ import annotations

from fastapi import Depends

from app.identity.application.dtos import AuthTokens
from app.identity.application.mfa import MfaService
from app.identity.presentation import deps
from app.identity.presentation.schemas import (
    ConfirmTotpEnrollmentRequest,
    RecoveryCodesResponse,
    TokenResponse,
    TotpEnrollmentResponse,
    VerifyMfaChallengeRequest,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["mfa"])


def _tokens_response(tokens: AuthTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in_seconds=tokens.expires_in_seconds,
    )


@router.post("/users/me/mfa/totp/enroll", response_model=DataResponse[TotpEnrollmentResponse])
async def start_totp_enrollment(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: MfaService = Depends(deps.get_mfa_service),
) -> DataResponse[TotpEnrollmentResponse]:
    result = await service.start_totp_enrollment(user_id=claims.subject_user_id)
    return DataResponse(
        data=TotpEnrollmentResponse(
            factor_id=result.factor_id, secret=result.secret, provisioning_uri=result.provisioning_uri
        )
    )


@router.post("/users/me/mfa/totp/confirm", response_model=DataResponse[RecoveryCodesResponse])
async def confirm_totp_enrollment(
    request: ConfirmTotpEnrollmentRequest,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: MfaService = Depends(deps.get_mfa_service),
) -> DataResponse[RecoveryCodesResponse]:
    codes = await service.confirm_totp_enrollment(
        user_id=claims.subject_user_id, factor_id=request.factor_id, code=request.code
    )
    return DataResponse(data=RecoveryCodesResponse(recovery_codes=codes))


@router.post("/users/me/mfa/recovery-codes/regenerate", response_model=DataResponse[RecoveryCodesResponse])
async def regenerate_recovery_codes(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: MfaService = Depends(deps.get_mfa_service),
) -> DataResponse[RecoveryCodesResponse]:
    codes = await service.regenerate_recovery_codes(user_id=claims.subject_user_id)
    return DataResponse(data=RecoveryCodesResponse(recovery_codes=codes))


@router.post("/users/me/mfa/disable", status_code=204)
async def disable_mfa(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: MfaService = Depends(deps.get_mfa_service),
) -> None:
    await service.disable_mfa(user_id=claims.subject_user_id)


@router.post("/auth/mfa/verify", response_model=DataResponse[TokenResponse])
async def verify_mfa_challenge(
    request: VerifyMfaChallengeRequest,
    service: MfaService = Depends(deps.get_mfa_service),
) -> DataResponse[TokenResponse]:
    """Not behind get_current_user_claims — the caller doesn't have a full
    access token yet, only the mfa_challenge_user_id returned by /auth/login."""
    tokens = await service.verify_mfa_challenge(
        user_id=request.user_id,
        code=request.code,
        ip_address="0.0.0.0",
        device_info=None,
        remember_me=request.remember_me,
    )
    return DataResponse(data=_tokens_response(tokens))
