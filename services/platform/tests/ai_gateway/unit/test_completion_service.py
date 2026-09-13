from __future__ import annotations

import pytest
from app.ai_gateway.application.service import AiCompletionService
from app.ai_gateway.domain.exceptions import (
    AiPromptTooLargeError,
    AiRateLimitExceededError,
    InvalidAiConversationError,
)
from app.platform_core.ai.gateway import AiGateway, ProviderRoute
from app.platform_core.ai.llm_provider import LlmCompletionResult, LlmMessage
from app.platform_core.shared_kernel.utils import new_uuid7


class _PermissionChecker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def assert_permission(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _RateLimitStore:
    def __init__(self, count: int = 1) -> None:
        self.count = count
        self.keys: list[str] = []

    async def increment_and_get(self, key: str, *, window_seconds: int) -> int:
        self.keys.append(key)
        assert window_seconds == 60
        return self.count


class _Provider:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return LlmCompletionResult("answer", 3, 2, kwargs["model"], "stop")

    async def stream(self, **kwargs):
        yield "answer"


def _service(*, count: int = 1, max_prompt: int = 1000, max_output: int = 100):
    provider = _Provider()
    permission = _PermissionChecker()
    limiter = _RateLimitStore(count)
    gateway = AiGateway(
        providers={"test": provider},
        primary=ProviderRoute("test", "server-controlled-model"),
    )
    service = AiCompletionService(
        gateway=gateway,
        permission_checker=permission,
        rate_limit_store=limiter,
        requests_per_minute=2,
        max_prompt_characters=max_prompt,
        max_output_tokens=max_output,
    )
    return service, provider, permission, limiter


@pytest.mark.asyncio
async def test_authorized_completion_is_rate_limited_and_caps_output_tokens() -> None:
    service, provider, permission, limiter = _service(max_output=50)
    org_id = new_uuid7()
    user_id = new_uuid7()

    result = await service.complete(
        org_id=org_id,
        user_id=user_id,
        messages=[LlmMessage(role="user", content="Hello")],
        max_tokens=500,
        temperature=0.2,
    )

    assert result.content == "answer"
    assert result.provider == "test"
    assert provider.calls[0]["max_tokens"] == 50
    assert permission.calls[0] == {
        "user_id": user_id,
        "org_id": org_id,
        "resource": "ai",
        "action": "use",
    }
    assert limiter.keys == [f"ai_completion:{org_id}:{user_id}"]


@pytest.mark.asyncio
async def test_prompt_character_limit_is_enforced_before_provider_call() -> None:
    service, provider, _, _ = _service(max_prompt=4)

    with pytest.raises(AiPromptTooLargeError):
        await service.complete(
            org_id=new_uuid7(),
            user_id=new_uuid7(),
            messages=[LlmMessage(role="user", content="12345")],
            max_tokens=10,
            temperature=0,
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_rate_limit_is_enforced_before_provider_call() -> None:
    service, provider, _, _ = _service(count=3)

    with pytest.raises(AiRateLimitExceededError):
        await service.complete(
            org_id=new_uuid7(),
            user_id=new_uuid7(),
            messages=[LlmMessage(role="user", content="Hello")],
            max_tokens=10,
            temperature=0,
        )

    assert provider.calls == []


@pytest.mark.asyncio
async def test_conversation_requires_a_user_message() -> None:
    service, provider, _, limiter = _service()

    with pytest.raises(InvalidAiConversationError):
        await service.complete(
            org_id=new_uuid7(),
            user_id=new_uuid7(),
            messages=[LlmMessage(role="system", content="Only a system prompt")],
            max_tokens=10,
            temperature=0,
        )

    assert provider.calls == []
    assert limiter.keys == []
