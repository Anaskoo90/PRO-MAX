"""Embedding Interface: text-to-vector, feeding VectorMemoryStore and RAG
retrieval — provider-agnostic, same reasoning as LlmProvider."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProviderError(Exception):
    pass


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int: ...
