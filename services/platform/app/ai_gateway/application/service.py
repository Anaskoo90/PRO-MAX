"""Authorized, rate-limited entry point to the platform AI Gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.ai_gateway.domain.exceptions import (
    AiPromptTooLargeError,
    AiRateLimitExceededError,
    InvalidAiConversationError,
)
from app.platform_core.ai.gateway import AiGateway
from app.platform_core.ai.llm_provider import LlmMessage
from app.platform_core.logging.logger import get_logger
from app.platform_core.shared_kernel.types import OrgId, UserId

_logger = get_logger("ai_gateway.completions")


class OrgPermissionCheckerPort(Protocol):
    async def assert_permission(
        self,
        *,
        user_id: UserId,
        org_id: OrgId,
        resource: str,
        action: str,
    ) -> None: ...


class RateLimitStorePort(Protocol):
    async def increment_and_get(self, key: str, *, window_seconds: int) -> int: ...


@dataclass(frozen=True, slots=True)
class AiCompletionDTO:
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


class AiCompletionService:
    def __init__(
        self,
        *,
        gateway: AiGateway,
        permission_checker: OrgPermissionCheckerPort,
        rate_limit_store: RateLimitStorePort,
        requests_per_minute: int,
        max_prompt_characters: int,
        max_output_tokens: int,
    ) -> None:
        self._gateway = gateway
        self._permission_checker = permission_checker
        self._rate_limit_store = rate_limit_store
        self._requests_per_minute = requests_per_minute
        self._max_prompt_characters = max_prompt_characters
        self._max_output_tokens = max_output_tokens

    async def complete(
        self,
        *,
        org_id: OrgId,
        user_id: UserId,
        messages: list[LlmMessage],
        max_tokens: int,
        temperature: float,
    ) -> AiCompletionDTO:
        await self._permission_checker.assert_permission(
            user_id=user_id,
            org_id=org_id,
            resource="ai",
            action="use",
        )
        if not any(
            message.role == "user" and message.content.strip()
            for message in messages
        ):
            raise InvalidAiConversationError()
        character_count = sum(len(message.content) for message in messages)
        if character_count > self._max_prompt_characters:
            raise AiPromptTooLargeError(self._max_prompt_characters)
        count = await self._rate_limit_store.increment_and_get(
            f"ai_completion:{org_id}:{user_id}",
            window_seconds=60,
        )
        if count > self._requests_per_minute:
            raise AiRateLimitExceededError(60)

        routed = await self._gateway.complete(
            messages=messages,
            max_tokens=min(max_tokens, self._max_output_tokens),
            temperature=temperature,
        )
        result = routed.completion
        await _logger.ainfo(
            "ai_completion_succeeded",
            org_id=str(org_id),
            user_id=str(user_id),
            provider=routed.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        return AiCompletionDTO(
            content=result.content,
            provider=routed.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            finish_reason=result.finish_reason,
        )
