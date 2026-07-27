"""
Memory Interface: conversational/session memory for the AI Business
Assistant, backed by Redis for short-term turns and delegating to Embedding
for long-term/semantic recall. The Vector Database vendor is still
undecided (standing gap) — VectorMemoryStore is the seam it plugs into.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.platform_core.ai.llm_provider import LlmMessage


class ConversationMemory(Protocol):
    async def append(self, session_id: str, message: LlmMessage) -> None: ...

    async def recent(self, session_id: str, *, limit: int = 20) -> list[LlmMessage]: ...

    async def clear(self, session_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    text: str
    score: float
    metadata: dict[str, str]


class VectorMemoryStore(Protocol):
    """Long-term/semantic memory. Concrete implementation depends on the
    still-undecided Vector Database vendor — this Protocol is the stable
    seam so AI Foundation code above it doesn't change once that's picked."""

    async def upsert(self, *, key: str, text: str, embedding: list[float]) -> None: ...

    async def search(self, *, query_embedding: list[float], top_k: int = 5) -> list[MemoryRecord]: ...
