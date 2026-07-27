"""Email Verification HTTP routes."""

from __future__ import annotations

from fastapi import Depends

from app.identity.application.email_verification import EmailVerificationService
from app.identity.presentation import deps
from app.identity.presentation.schemas import VerifyEmailRequest
from app.platform_core.api.versioning import versioned_router
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["email-verification"])


@router.post("/users/me/email/resend-verification", status_code=204)
async def resend_verification(
    claims: TokenClaims = Depends(deps.get_current_user_claims),
    service: EmailVerificationService = Depends(deps.get_email_verification_service),
) -> None:
    await service.resend_verification(user_id=claims.subject_user_id)


@router.post("/users/me/email/verify", status_code=204)
async def verify_email(
    request: VerifyEmailRequest,
    service: EmailVerificationService = Depends(deps.get_email_verification_service),
) -> None:
    """Deliberately not behind get_current_user_claims — the verification
    link is emailed pre-login and must work from a cold browser session;
    the token itself is the credential."""
    await service.verify_email(raw_token=request.token)
