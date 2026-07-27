import pytest

from app.identity.application.security import BruteForceGuard, BruteForcePolicy, InMemoryRateLimitStore
from app.identity.domain.exceptions import BruteForceProtectionTriggeredError


@pytest.mark.asyncio
async def test_allows_attempts_within_the_limit() -> None:
    guard = BruteForceGuard(store=InMemoryRateLimitStore(), policy=BruteForcePolicy(max_attempts_per_window=3))
    for _ in range(3):
        await guard.check(ip_address="203.0.113.9")


@pytest.mark.asyncio
async def test_blocks_attempts_beyond_the_limit() -> None:
    guard = BruteForceGuard(store=InMemoryRateLimitStore(), policy=BruteForcePolicy(max_attempts_per_window=3))
    for _ in range(3):
        await guard.check(ip_address="203.0.113.9")

    with pytest.raises(BruteForceProtectionTriggeredError):
        await guard.check(ip_address="203.0.113.9")


@pytest.mark.asyncio
async def test_tracks_each_ip_independently() -> None:
    guard = BruteForceGuard(store=InMemoryRateLimitStore(), policy=BruteForcePolicy(max_attempts_per_window=1))
    await guard.check(ip_address="203.0.113.9")
    await guard.check(ip_address="203.0.113.10")  # different IP, own budget
