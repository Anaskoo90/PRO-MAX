"""Authentication + OAuth2/OIDC HTTP routes."""

from __future__ import annotations

from fastapi import Depends

from app.identity.application.authentication import AuthenticationService, OAuth2LoginService
from app.identity.application.dtos import LoginResult
from app.identity.presentation import deps
from app.identity.presentation.schemas import (
    LoginRequest,
    LogoutRequest,
    MfaChallengeResponse,
    OAuth2AuthorizationUrlResponse,
    OAuth2CallbackRequest,
    RefreshTokenRequest,
    SessionResponse,
    TokenResponse,
)
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["authentication"])


def _login_result_response(result: LoginResult) -> TokenResponse | MfaChallengeResponse:
    if result.tokens is not None:
        return TokenResponse(
            access_token=result.tokens.access_token,
            refresh_token=result.tokens.refresh_token,
            token_type=result.tokens.token_type,
            expires_in_seconds=result.tokens.expires_in_seconds,
        )
    assert result.mfa_challenge_user_id is not None
    return MfaChallengeResponse(
        mfa_challenge_user_id=result.mfa_challenge_user_id,
        available_factors=list(result.mfa_available_factors),
    )


@router.post("/auth/login", response_model=None)
async def login(
    request: LoginRequest,
    service: AuthenticationService = Depends(deps.get_authentication_service),
) -> TokenResponse | MfaChallengeResponse:
    result = await service.login(
        org_id=request.org_id,
        email=request.email,
        password=request.password,
        ip_address="0.0.0.0",  # replaced by the real client IP once behind a reverse proxy config
        device_info=None,
        remember_me=request.remember_me,
    )
    return _login_result_response(result)


@router.post("/auth/refresh", response_model=DataResponse[TokenResponse])
async def refresh_token(
    request: RefreshTokenRequest,
    service: AuthenticationService = Depends(deps.get_authentication_service),
) -> DataResponse[TokenResponse]:
    tokens = await service.refresh(raw_refresh_token=request.refresh_token)
    return DataResponse(
        data=TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in_seconds=tokens.expires_in_seconds,
        )
    )


@router.post("/auth/logout", status_code=204)
async def logout(
    request: LogoutRequest,
    service: AuthenticationService = Depends(deps.get_authentication_service),
) -> None:
    await service.logout(raw_refresh_token=request.refresh_token)


@router.get("/auth/sessions", response_model=DataResponse[list[SessionResponse]])
async def list_sessions(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: AuthenticationService = Depends(deps.get_authentication_service),
) -> DataResponse[list[SessionResponse]]:
    sessions = await service.list_sessions(user_id=claims.subject_user_id, current_session_id=None)
    return DataResponse(
        data=[
            SessionResponse(
                id=s.id,
                device_label=s.device_label,
                ip_address=s.ip_address,
                created_at=s.created_at,
                expires_at=s.expires_at,
                is_current=s.is_current,
            )
            for s in sessions
        ]
    )


@router.delete("/auth/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: str,
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: AuthenticationService = Depends(deps.get_authentication_service),
) -> None:
    from uuid import UUID

    await service.revoke_session(user_id=claims.subject_user_id, session_id=UUID(session_id))


@router.get("/auth/oauth2/{provider}/authorize", response_model=DataResponse[OAuth2AuthorizationUrlResponse])
async def oauth2_authorize(
    provider: str,
    service: OAuth2LoginService = Depends(deps.get_oauth2_login_service),
) -> DataResponse[OAuth2AuthorizationUrlResponse]:
    url, state = service.build_authorization_url(provider)
    return DataResponse(data=OAuth2AuthorizationUrlResponse(authorization_url=url, state=state))


@router.post("/auth/oauth2/{provider}/callback", response_model=DataResponse[TokenResponse])
async def oauth2_callback(
    provider: str,
    request: OAuth2CallbackRequest,
    service: OAuth2LoginService = Depends(deps.get_oauth2_login_service),
) -> DataResponse[TokenResponse]:
    tokens = await service.login_with_callback(
        provider_key=provider, code=request.code, org_id=request.org_id, ip_address="0.0.0.0", device_info=None
    )
    return DataResponse(
        data=TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_in_seconds=tokens.expires_in_seconds,
        )
    )
