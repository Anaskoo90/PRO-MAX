from __future__ import annotations

from app.platform_core.errors.domain_exceptions import BusinessRuleViolationError
from app.platform_core.shared_kernel.error_codes import ErrorCode


class AiPromptTooLargeError(BusinessRuleViolationError):
    def __init__(self, max_characters: int) -> None:
        super().__init__(
            "ai_prompt_too_large",
            f"AI conversation exceeds the {max_characters}-character limit",
        )


class InvalidAiConversationError(BusinessRuleViolationError):
    def __init__(self) -> None:
        super().__init__(
            "invalid_ai_conversation",
            "AI conversation must contain at least one non-empty user message",
        )


class AiRateLimitExceededError(BusinessRuleViolationError):
    code = ErrorCode.RATE_LIMITED

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "ai_rate_limit_exceeded",
            f"AI request limit exceeded; retry after {retry_after_seconds}s",
        )
        self.retry_after_seconds = retry_after_seconds
