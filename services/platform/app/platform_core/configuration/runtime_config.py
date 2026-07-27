"""
Runtime Configuration: values that may change without a redeploy (rate
limit thresholds, circuit-breaker overrides), distinct from Settings, which
is process-start-time and immutable for the process lifetime.
"""

from __future__ import annotations

from typing import Any, Protocol


class RuntimeConfigProvider(Protocol):
    async def get(self, key: str, default: Any = None) -> Any: ...

    async def set(self, key: str, value: Any) -> None: ...


class InMemoryRuntimeConfigProvider:
    """Local-dev / test double. Production implementation is Redis-backed
    (see platform_core.messaging for the Redis client pattern this would
    reuse) so runtime config changes propagate across replicas."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        self._store[key] = value
