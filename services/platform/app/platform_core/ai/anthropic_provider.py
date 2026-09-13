"""Anthropic Messages API adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.platform_core.ai.llm_provider import (
    LlmCompletionResult,
    LlmMessage,
    LlmProviderError,
)
from app.platform_core.shared_kernel.constants import TIMEOUT_AI_SECONDS


class AnthropicProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        api_version: str = "2023-06-01",
        timeout_seconds: float = TIMEOUT_AI_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Anthropic API key cannot be empty")
        self._base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={
                "x-api-key": api_key,
                "anthropic-version": api_version,
                "Content-Type": "application/json",
            },
        )

    async def complete(
        self,
        *,
        messages: list[LlmMessage],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmCompletionResult:
        body = self._request_body(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
        )
        try:
            response = await self._client.post(f"{self._base_url}/messages", json=body)
        except httpx.HTTPError as exc:
            raise LlmProviderError("Anthropic provider is unavailable") from exc
        if response.is_error:
            raise LlmProviderError(
                f"Anthropic provider rejected completion with status {response.status_code}"
            )
        try:
            payload = response.json()
            content = "".join(
                str(block.get("text", ""))
                for block in payload["content"]
                if block.get("type") == "text"
            )
            usage = payload.get("usage") or {}
            return LlmCompletionResult(
                content=content,
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                model=str(payload.get("model") or model),
                finish_reason=str(payload.get("stop_reason") or "unknown"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LlmProviderError(
                "Anthropic provider returned an invalid completion response"
            ) from exc

    async def stream(
        self,
        *,
        messages: list[LlmMessage],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        body = self._request_body(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=None,
        )
        body["stream"] = True
        try:
            async with self._client.stream(
                "POST", f"{self._base_url}/messages", json=body
            ) as response:
                if response.is_error:
                    await response.aread()
                    raise LlmProviderError(
                        f"Anthropic provider rejected stream with status "
                        f"{response.status_code}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise LlmProviderError(
                            "Anthropic provider returned an invalid stream event"
                        ) from exc
                    delta = payload.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield str(delta["text"])
        except LlmProviderError:
            raise
        except httpx.HTTPError as exc:
            raise LlmProviderError("Anthropic provider stream failed") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _request_body(
        *,
        messages: list[LlmMessage],
        model: str,
        max_tokens: int,
        temperature: float,
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        system = "\n\n".join(
            message.content for message in messages if message.role == "system"
        )
        conversation = [
            {"role": message.role, "content": message.content}
            for message in messages
            if message.role != "system"
        ]
        if any(message["role"] not in {"user", "assistant"} for message in conversation):
            raise LlmProviderError(
                "Anthropic provider supports user and assistant conversation roles"
            )
        body: dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {"type": "object"}),
                }
                for tool in tools
            ]
        return body
