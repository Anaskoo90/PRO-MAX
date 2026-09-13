from __future__ import annotations

import json

import httpx
import pytest
from app.platform_core.ai.anthropic_provider import AnthropicProvider
from app.platform_core.ai.embedding import EmbeddingProviderError
from app.platform_core.ai.gateway import AiGateway, ProviderRoute
from app.platform_core.ai.llm_provider import (
    LlmCompletionResult,
    LlmMessage,
    LlmProviderError,
)
from app.platform_core.ai.openai_provider import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_openai_completion_formats_tools_and_parses_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["tools"][0] == {
            "type": "function",
            "function": {
                "name": "find_ticket",
                "description": "Find a ticket",
                "parameters": {"type": "object"},
            },
        }
        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "choices": [
                    {"message": {"content": "Hello"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer test-key"},
    )
    provider = OpenAICompatibleProvider(api_key="test-key", client=client)
    result = await provider.complete(
        messages=[LlmMessage(role="user", content="Hi")],
        model="gpt-test",
        tools=[
            {
                "name": "find_ticket",
                "description": "Find a ticket",
                "parameters": {"type": "object"},
            }
        ],
    )

    assert result == LlmCompletionResult(
        content="Hello",
        input_tokens=4,
        output_tokens=2,
        model="gpt-test",
        finish_reason="stop",
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_stream_and_embeddings_follow_provider_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                text=(
                    'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
                    "data: [DONE]\n\n"
                ),
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        embedding_dimensions=2,
        client=client,
    )

    chunks = [
        chunk
        async for chunk in provider.stream(
            messages=[LlmMessage(role="user", content="Hi")], model="gpt-test"
        )
    ]
    embeddings = await provider.embed(["first", "second"])

    assert chunks == ["Hel", "lo"]
    assert embeddings == [[0.1, 0.2], [0.3, 0.4]]
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_rejects_wrong_embedding_dimensions() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [0.1]}]}
            )
        )
    )
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        embedding_dimensions=2,
        client=client,
    )

    with pytest.raises(EmbeddingProviderError, match="dimensions"):
        await provider.embed(["text"])
    await client.aclose()


@pytest.mark.asyncio
async def test_anthropic_completion_and_stream_follow_messages_contract() -> None:
    request_bodies: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        if request_bodies[-1].get("stream"):
            return httpx.Response(
                200,
                text=(
                    'event: content_block_delta\n'
                    'data: {"delta":{"type":"text_delta","text":"Hi"}}\n\n'
                    'event: message_stop\ndata: {"type":"message_stop"}\n\n'
                ),
            )
        return httpx.Response(
            200,
            json={
                "model": "claude-test",
                "content": [{"type": "text", "text": "Done"}],
                "usage": {"input_tokens": 5, "output_tokens": 1},
                "stop_reason": "end_turn",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AnthropicProvider(api_key="test-key", client=client)
    messages = [
        LlmMessage(role="system", content="Be concise"),
        LlmMessage(role="user", content="Hello"),
    ]

    result = await provider.complete(messages=messages, model="claude-test")
    chunks = [
        chunk
        async for chunk in provider.stream(messages=messages, model="claude-test")
    ]

    assert result.content == "Done"
    assert result.input_tokens == 5
    assert request_bodies[0]["system"] == "Be concise"
    assert request_bodies[0]["messages"] == [{"role": "user", "content": "Hello"}]
    assert chunks == ["Hi"]
    await client.aclose()


class _FailingProvider:
    async def complete(self, **kwargs):
        raise LlmProviderError("primary failed")

    async def stream(self, **kwargs):
        raise LlmProviderError("primary failed")
        yield ""  # pragma: no cover


class _SuccessfulProvider:
    async def complete(self, **kwargs):
        return LlmCompletionResult("fallback", 2, 1, kwargs["model"], "stop")

    async def stream(self, **kwargs):
        yield "fallback"


@pytest.mark.asyncio
async def test_gateway_fails_over_to_configured_secondary_provider() -> None:
    gateway = AiGateway(
        providers={"primary": _FailingProvider(), "secondary": _SuccessfulProvider()},
        primary=ProviderRoute("primary", "model-a"),
        fallback=ProviderRoute("secondary", "model-b"),
    )

    result = await gateway.complete(
        messages=[LlmMessage(role="user", content="Hello")]
    )
    chunks = [
        chunk
        async for chunk in gateway.stream(
            messages=[LlmMessage(role="user", content="Hello")]
        )
    ]

    assert result.provider == "secondary"
    assert result.completion.model == "model-b"
    assert chunks == ["fallback"]


@pytest.mark.asyncio
async def test_gateway_without_a_configured_provider_fails_closed() -> None:
    gateway = AiGateway(providers={}, primary=None)

    with pytest.raises(LlmProviderError, match="No AI provider"):
        await gateway.complete(
            messages=[LlmMessage(role="user", content="Hello")]
        )
