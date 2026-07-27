"""
Idempotency Support: at-least-once delivery (RabbitMQ's guarantee) means
every consumer must be safe to invoke twice for the same message. This
module provides the shared "have I seen this key before" check, backed by
Redis (fast path) — consumers call check_and_mark before doing real work.
"""

from __future__ import annotations

from typing import Protocol


class IdempotencyStore(Protocol):
    async def check_and_mark(self, key: str, *, ttl_seconds: int) -> bool:
        """Returns True if this is the first time `key` has been seen
        within the TTL window (caller should proceed), False if it's a
        duplicate (caller should skip)."""
        ...


class RedisIdempotencyStore:
    """Uses SET key value NX EX ttl — atomic check-and-set in one round trip."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def check_and_mark(self, key: str, *, ttl_seconds: int = 86400) -> bool:
        result = await self._redis.set(
            f"idempotency:{key}", "1", nx=True, ex=ttl_seconds
        )
        return bool(result)
