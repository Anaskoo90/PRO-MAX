"""OpenAI-compatible chat-completion and embedding adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.platform_core.ai.embedding import EmbeddingProviderError
from app.platform_core.ai.llm_provider import (
    LlmCompletionResult,
    LlmMessage,
    LlmProviderError,
)
from app.platform_core.shared_kernel.constants import TIMEOUT_AI_SECONDS


class OpenAICompatibleProvider:
    """Adapter for OpenAI and servers implementing its v1 HTTP contract."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        embedding_model: str = "text-embedding-3-small",
        embedding_dimensions: int = 1536,
        timeout_seconds: float = TIMEOUT_AI_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key cannot be empty")
        if embedding_dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")
        self._base_url = base_url.rstrip("/")
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def dimensions(self) -> int:
        return self._embedding_dimensions

    async def complete(
        self,
        *,
        messages: list[LlmMessage],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmCompletionResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = [self._format_tool(tool) for tool in tools]
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=body,
            )
        except httpx.HTTPError as exc:
            raise LlmProviderError("OpenAI-compatible provider is unavailable") from exc
        if response.is_error:
            raise LlmProviderError(
                f"OpenAI-compatible provider rejected completion with status "
                f"{response.status_code}"
            )
        try:
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"].get("content") or ""
            usage = payload.get("usage") or {}
            return LlmCompletionResult(
                content=str(content),
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                model=str(payload.get("model") or model),
                finish_reason=str(choice.get("finish_reason") or "unknown"),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LlmProviderError(
                "OpenAI-compatible provider returned an invalid completion response"
            ) from exc

    async def stream(
        self,
        *,
        messages: list[LlmMessage],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        body = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=body,
            ) as response:
                if response.is_error:
                    await response.aread()
                    raise LlmProviderError(
                        f"OpenAI-compatible provider rejected stream with status "
                        f"{response.status_code}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if raw == "[DONE]":
                        return
                    try:
                        payload = json.loads(raw)
                        content = payload["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                        raise LlmProviderError(
                            "OpenAI-compatible provider returned an invalid stream event"
                        ) from exc
                    if content:
                        yield str(content)
        except LlmProviderError:
            raise
        except httpx.HTTPError as exc:
            raise LlmProviderError("OpenAI-compatible provider stream failed") from exc

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._embedding_model, "input": texts},
            )
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError("OpenAI embedding provider is unavailable") from exc
        if response.is_error:
            raise EmbeddingProviderError(
                f"OpenAI embedding provider rejected request with status "
                f"{response.status_code}"
            )
        try:
            payload = response.json()
            rows = sorted(payload["data"], key=lambda row: int(row["index"]))
            embeddings = [
                [float(value) for value in row["embedding"]]
                for row in rows
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError(
                "OpenAI embedding provider returned an invalid response"
            ) from exc
        if len(embeddings) != len(texts) or any(
            len(embedding) != self._embedding_dimensions
            for embedding in embeddings
        ):
            raise EmbeddingProviderError(
                "OpenAI embedding provider returned unexpected vector dimensions"
            )
        return embeddings

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _format_tool(tool: dict[str, Any]) -> dict[str, Any]:
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            return tool
        return {"type": "function", "function": tool}
