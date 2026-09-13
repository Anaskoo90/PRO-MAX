"""Provider routing and failover for language-model requests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from app.platform_core.ai.llm_provider import (
    LlmCompletionResult,
    LlmMessage,
    LlmProvider,
    LlmProviderError,
)


class AiGatewayUnavailableError(LlmProviderError):
    def __init__(self) -> None:
        super().__init__("No AI provider is configured")


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class RoutedCompletionResult:
    provider: str
    completion: LlmCompletionResult


class AiGateway:
    """Routes requests through a configured primary and optional fallback.

    Only provider/infrastructure failures trigger failover. Invalid caller
    input and authorization errors are handled before this boundary and are
    never retried against another billable provider.
    """

    def __init__(
        self,
        *,
        providers: Mapping[str, LlmProvider],
        primary: ProviderRoute | None,
        fallback: ProviderRoute | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._primary = primary
        self._fallback = fallback

    @property
    def is_configured(self) -> bool:
        return self._primary is not None and self._primary.provider in self._providers

    async def complete(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> RoutedCompletionResult:
        routes = self._routes()
        last_error: LlmProviderError | None = None
        for route in routes:
            provider = self._providers.get(route.provider)
            if provider is None:
                last_error = AiGatewayUnavailableError()
                continue
            try:
                result = await provider.complete(
                    messages=messages,
                    model=route.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=tools,
                )
                return RoutedCompletionResult(
                    provider=route.provider,
                    completion=result,
                )
            except LlmProviderError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise AiGatewayUnavailableError()

    async def stream(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        last_error: LlmProviderError | None = None
        for route in self._routes():
            provider = self._providers.get(route.provider)
            if provider is None:
                last_error = AiGatewayUnavailableError()
                continue
            emitted = False
            try:
                async for chunk in provider.stream(
                    messages=messages,
                    model=route.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ):
                    emitted = True
                    yield chunk
                return
            except LlmProviderError as exc:
                if emitted:
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error
        raise AiGatewayUnavailableError()

    def _routes(self) -> tuple[ProviderRoute, ...]:
        if self._primary is None:
            return ()
        if self._fallback is None or self._fallback == self._primary:
            return (self._primary,)
        return self._primary, self._fallback
