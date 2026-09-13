from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.ai_gateway.application.service import AiCompletionService
from app.ai_gateway.presentation import deps
from app.ai_gateway.presentation.schemas import (
    AiCompletionRequest,
    AiCompletionResponse,
)
from app.identity.presentation.deps import get_current_user_claims
from app.platform_core.ai.llm_provider import LlmMessage
from app.platform_core.api.responses import DataResponse
from app.platform_core.api.versioning import versioned_router
from app.platform_core.errors.api_exceptions import ForbiddenError
from app.platform_core.security.token import TokenClaims

router = versioned_router(version="v1", tags=["ai"])


@router.post(
    "/organizations/{org_id}/ai/completions",
    response_model=DataResponse[AiCompletionResponse],
)
async def create_ai_completion(
    org_id: UUID,
    request: AiCompletionRequest,
    claims: Annotated[TokenClaims, Depends(get_current_user_claims)],
    service: Annotated[AiCompletionService, Depends(deps.get_ai_completion_service)],
) -> DataResponse[AiCompletionResponse]:
    if org_id != claims.org_id:
        raise ForbiddenError("Organization context does not match the access token")
    result = await service.complete(
        org_id=org_id,
        user_id=claims.subject_user_id,
        messages=[
            LlmMessage(role=message.role, content=message.content)
            for message in request.messages
        ],
        max_tokens=request.max_tokens,
        temperature=request.temperature,
    )
    return DataResponse(
        data=AiCompletionResponse(
            content=result.content,
            provider=result.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            finish_reason=result.finish_reason,
        )
    )
