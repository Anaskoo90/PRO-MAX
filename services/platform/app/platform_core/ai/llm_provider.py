"""
LLM Provider Interface: the abstraction the AI Gateway's provider-adapter
pattern (ADR-012) is built on — also the pattern the Integration Layer
(Amendment v2, ADR-034) later generalized. Kept here as the narrow,
AI-specific contract; the generalized Integration Layer adapter interface
is a separate, broader concern flagged elsewhere as an unresolved
harmonization gap between AI Gateway, Payment Center, and Discord Adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol


@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


@dataclass(frozen=True, slots=True)
class LlmCompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str


class LlmProviderError(Exception):
    pass


class LlmProvider(Protocol):
    async def complete(
        self,
        *,
        messages: list[LlmMessage],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmCompletionResult: ...

    async def stream(
        self,
        *,
        messages: list[LlmMessage],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]: ...
